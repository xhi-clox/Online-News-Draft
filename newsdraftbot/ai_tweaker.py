import json as json_mod
import logging
from datetime import date

from config import Config
from database import AIUsage, db

logger = logging.getLogger(__name__)

DAILY_LIMIT = 1500

DEFAULT_INSTRUCTION = (
    "You are a professional news editor. Tweak the following news article "
    "to improve clarity, flow, and readability while keeping all facts, "
    "names, numbers, and quotes intact. Do not add new information or "
    "opinions. Return only the improved article text, no explanations."
)

FULL_EDIT_INSTRUCTION = (
    "You are a senior editor at a professional Bengali news organization. "
    "Polish this article for publication.\n\n"
    "### Rules\n"
    "- Language: বাংলা (Bengali) throughout\n"
    "- Preserve ALL facts: names, locations, dates, times, quotations, statistics, sequence of events\n"
    "- Do NOT add new information, opinions, or commentary\n"
    "- Fix grammar, spelling, and readability issues\n\n"
    "### Content format\n"
    "- `content` field MUST be valid HTML: `<p>...</p>` for paragraphs, `<strong>...</strong>` for emphasis, `<h3>উপশিরোনাম</h3>` for subheadings\n"
    "- NO markdown, NO triple backticks, NO `\\n` escape sequences in JSON\n\n"
    "### Style\n"
    "- Professional journalistic style with a strong lead paragraph\n"
    "- Keep paragraphs separate — do not merge\n"
    "- Neutral, objective tone throughout\n\n"
    "### Tags\n"
    "- Generate 5–8 SEO-friendly tags in Bengali\n"
    "- High-relevance keywords from the content\n\n"
    "### Categories\n"
    "- **এক্সক্লুসিভ (Exclusive) MUST always be the first category**\n"
    "- Choose 1–2 more categories from the provided available list only\n"
    "- Do NOT invent categories not in the available list\n\n"
    "### Output format (valid JSON only, no markdown fences, no explanation)\n"
    '{"title": "...", "content": "<p>...</p><p>...</p>", "excerpt": "...", '
    '"tags": "tag1, tag2, tag3", "categories": "এক্সক্লুসিভ, cat2", "reporter": "..."}'
)


def get_today_usage():
    today = date.today()
    usage = AIUsage.query.filter_by(date=today).first()
    if not usage:
        usage = AIUsage(date=today, count=0, limit=DAILY_LIMIT)
        db.session.add(usage)
        db.session.commit()
    return usage


def quota_remaining():
    usage = get_today_usage()
    return usage.limit - usage.count


def increment_usage():
    usage = get_today_usage()
    usage.count += 1
    db.session.commit()


def edit_full_article(
    title, content, excerpt, tags, categories, reporter,
    available_categories=None, instruction=None,
):
    api_key = Config.AI_API_KEY
    if not api_key:
        raise ValueError("AI_API_KEY not configured")

    if quota_remaining() <= 0:
        raise ValueError("Daily AI quota exhausted (1500/1500 requests used)")

    from openai import OpenAI

    system_prompt = instruction.strip() if instruction and instruction.strip() else FULL_EDIT_INSTRUCTION
    base_url = Config.AI_BASE_URL.rstrip("/")
    model = Config.AI_MODEL

    tags_str = ", ".join(tags) if tags else ""
    cats_str = ", ".join(categories) if categories else ""
    available_cats_str = ", ".join(available_categories) if available_categories else ""

    client = OpenAI(api_key=api_key, base_url=base_url)
    prompt = (
        f"Current article state:\n\n"
        f"Title: {title}\n\n"
        f"Content:\n{content}\n\n"
        f"Excerpt: {excerpt}\n\n"
        f"Current Tags: {tags_str}\n\n"
        f"Current Categories: {cats_str}\n\n"
        f"Available Categories (pick from these only): {available_cats_str}\n\n"
        f"Reporter: {reporter}\n\n"
        f"Apply your editorial changes in Bengali."
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=4096,
        timeout=60,
    )

    result_text = resp.choices[0].message.content.strip()
    if result_text.startswith("```"):
        lines = result_text.split("\n")
        result_text = "\n".join(lines[1:] if lines[0].startswith("```") else lines)
        if result_text.endswith("```"):
            result_text = result_text[:-3].strip()

    try:
        result = json_mod.loads(result_text)
    except json_mod.JSONDecodeError:
        logger.error(f"AI returned invalid JSON: {result_text[:500]}")
        raise ValueError("AI returned an invalid response format. Try again.")

    increment_usage()
    return result


def tweak_article(title, content, instruction=None):
    api_key = Config.AI_API_KEY
    if not api_key:
        raise ValueError("AI_API_KEY not configured")

    if quota_remaining() <= 0:
        raise ValueError("Daily AI quota exhausted (1500/1500 requests used)")

    from openai import OpenAI

    system_prompt = instruction.strip() if instruction and instruction.strip() else DEFAULT_INSTRUCTION
    base_url = Config.AI_BASE_URL.rstrip("/")
    model = Config.AI_MODEL

    client = OpenAI(api_key=api_key, base_url=base_url)
    prompt = f"Title: {title}\n\nArticle:\n{content}"

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=2048,
        timeout=60,
    )

    increment_usage()
    return resp.choices[0].message.content
