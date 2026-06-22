import logging
import re

logger = logging.getLogger(__name__)


def clean_html(html_content):
    if not html_content:
        return ""
    clean = re.sub(r"<[^>]+>", " ", html_content)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def generate_excerpt(html_content, min_length=150, max_length=250):
    text = clean_html(html_content)
    if not text:
        return ""

    if len(text) <= max_length:
        return text

    truncated = text[:max_length]
    last_space = truncated.rfind(" ")
    if last_space > min_length:
        truncated = truncated[:last_space]

    sentence_end = max(
        truncated.rfind(". "), truncated.rfind("! "), truncated.rfind("? ")
    )
    if sentence_end > min_length:
        truncated = truncated[: sentence_end + 1]

    return truncated.strip()
