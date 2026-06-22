import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

from config import Config
from database import Article, db

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:200]


def discover_article_urls():
    """
    Discover article URLs from the news source.
    First tries RSS feed, then falls back to scraping the homepage.
    Returns a list of (url, title) tuples.
    """
    source_url = Config.NEWS_SOURCE_URL
    if not source_url:
        logger.error("NEWS_SOURCE_URL not configured")
        return []

    # Try common RSS feed locations first
    rss_paths = ["/feed/latest-rss.xml", "/feed", "/rss", "/feed.xml"]
    for path in rss_paths:
        feed_url = urljoin(source_url, path)
        entries = fetch_rss_feed(feed_url)
        if entries:
            logger.info(f"Found RSS feed at {feed_url} with {len(entries)} entries")
            return [(e.get("link", ""), e.get("title", "")) for e in entries if e.get("link")]

    # Fallback: scrape homepage for article links
    logger.info("No RSS feed found, scraping homepage for article links")
    return scrape_homepage_for_links(source_url)


def fetch_rss_feed(url):
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            logger.warning(f"RSS parse error: {feed.bozo_exception}")
            return []
        return feed.entries
    except requests.RequestException as e:
        logger.error(f"Failed to fetch RSS feed {url}: {e}")
        return []


def scrape_homepage_for_links(url):
    """Scrape homepage to find article links."""
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch homepage {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.find_all("a", href=True)

    article_urls = []
    seen = set()
    domain = url.rstrip("/")

    for a in links:
        href = a["href"]
        link_text = a.get_text(strip=True)

        # Resolve relative URLs
        if href.startswith("/"):
            full_url = urljoin(domain, href)
        elif href.startswith(domain):
            full_url = href
        else:
            continue

        # Skip non-article paths
        path = full_url.replace(domain, "")
        if not path or path == "/":
            continue

        # Skip category/listing pages (links with shallow paths)
        path_parts = path.strip("/").split("/")
        if len(path_parts) < 2:
            continue

        # Must have meaningful link text (not just icons/ads)
        if len(link_text) < 10:
            continue

        if full_url not in seen:
            seen.add(full_url)
            article_urls.append((full_url, link_text))

    logger.info(f"Found {len(article_urls)} article links on homepage")
    return article_urls


def scrape_article_page(url):
    """Visit article page and extract title, featured image, and clean body content."""
    logger.info(f"Scraping article: {url}")
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch article {url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # --- Extract title ---
    title = ""
    headline_block = soup.find("div", class_="headline_content_block")
    if headline_block:
        title = headline_block.get_text(strip=True)
    if not title:
        headline_section = soup.find("div", class_="headline_section")
        if headline_section:
            title = headline_section.get_text(strip=True)
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "")

    if not title:
        logger.warning(f"No title found for {url}")
        return None

    # --- Extract featured image (prefer body image over og:image to avoid watermarks) ---
    featured_image = None
    img_section = soup.find("div", class_="dtl_img_section")
    if img_section:
        img = img_section.find("img")
        if img and img.get("src"):
            featured_image = urljoin(url, img["src"])

    if not featured_image:
        content_area = soup.find("div", class_="dtl_section")
        if content_area:
            img = content_area.find("img")
            if img and img.get("src"):
                featured_image = urljoin(url, img["src"])

    if not featured_image:
        og_img = soup.find("meta", property="og:image")
        if og_img:
            featured_image = og_img.get("content", "")

    # --- Extract clean body content (no images, excluded text stripped) ---
    body_html = extract_clean_body(soup, url)

    if not body_html:
        logger.warning(f"No body content found for {url}")
        return None

    body_html = strip_excluded_text(body_html, url)

    return {
        "title": title,
        "slug": slugify(title),
        "source_url": url,
        "content": body_html,
        "excerpt": None,
        "featured_image": featured_image,
        "published": datetime.now(timezone.utc),
    }


EXCLUDED_PATTERNS = [
    "বাংলাদেশ জার্নাল",
    "সূত্র",
]


def extract_clean_body(soup, base_url):
    """Extract article body paragraphs, removing ads, related posts, images, and other clutter."""
    article_wrapper = None
    dtl_section = soup.find("div", class_="dtl_section")
    if dtl_section:
        article_wrapper = dtl_section.find_parent("div", class_="col-md-12")

    if not article_wrapper:
        for sel in ["article", "main", ".post-content", ".entry-content", ".col-md-12"]:
            container = soup.select_one(sel)
            if container and len(container.get_text(strip=True)) > 500:
                article_wrapper = container
                break

    if not article_wrapper:
        return None

    wrapper = BeautifulSoup(str(article_wrapper), "html.parser")

    for tag in wrapper(["script", "style", "iframe", "noscript", "ins"]):
        tag.decompose()

    for selector in [
        ".headline_content_block",
        ".div_line",
        ".tab_bar_block",
        ".list_display_block",
        ".dtl_more_news_block",
        ".related-more-news",
        ".socialShare",
        ".share_section",
        ".sharethis-inline-share-buttons",
        ".rpt_and_share_block",
        ".rpt_info_section",
        ".dtl_img_section",
        ".dtl_img_caption",
        ".fb-comments",
        ".fb-like",
        ".fb-save",
        ".fb-send",
        ".fb-share-button",
        ".print_icon",
        ".printdiv",
        ".hit_counter",
        ".spacebar",
        ".back_top",
        ".copyrightInfo",
        ".sub-news",
        "[class*=ad]",
        "[id*=ad]",
    ]:
        for el in wrapper.select(selector):
            el.decompose()

    for row in wrapper.find_all("div", class_="dtl_pg_row"):
        links = row.find_all("a", href=True)
        has_multiple_articles = sum(1 for a in links if a.get("href", "").count("/") >= 3) > 2
        if has_multiple_articles and len(row.get_text(strip=True)) > 100:
            row.decompose()
            continue
        if not row.get_text(strip=True):
            row.decompose()
            continue

    for tag in wrapper.find_all("img"):
        tag.decompose()

    paragraphs = []
    for p in wrapper.find_all("p"):
        text = p.get_text(strip=True)
        if text:
            paragraphs.append(f"<p>{text}</p>")

    if not paragraphs or len("".join(paragraphs)) < 100:
        return None

    return "\n".join(paragraphs)


def strip_excluded_text(html, base_url):
    """Remove footer lines and short standalone exclusion words from body HTML."""
    soup = BeautifulSoup(html, "html.parser")

    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if not text:
            p.decompose()
            continue
        if any(pattern in text for pattern in EXCLUDED_PATTERNS):
            p.decompose()
            continue

    parts = []
    for p in soup.find_all("p"):
        parts.append(str(p))
    return "".join(parts)


def check_duplicate(source_url):
    return Article.query.filter_by(source_url=source_url).first() is not None


def fetch_and_save_articles():
    article_links = discover_article_urls()
    if not article_links:
        logger.warning("No article links discovered")
        return []

    articles_saved = []

    for url, link_title in article_links:
        try:
            if check_duplicate(url):
                logger.info(f"Duplicate skipped: {url}")
                continue

            article_data = scrape_article_page(url)
            if not article_data:
                continue

            article = Article(
                title=article_data["title"],
                slug=article_data["slug"],
                source_url=article_data["source_url"],
                content=article_data["content"],
                tags=[article_data["title"]],
                categories=["এক্সক্লুসিভ", "জাতীয়", "খবর"],
                featured_image=article_data.get("featured_image"),
                status="NEW",
            )
            db.session.add(article)
            db.session.commit()
            articles_saved.append(article)
            logger.info(f"Saved: {article.title}")

        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            db.session.rollback()

    return articles_saved
