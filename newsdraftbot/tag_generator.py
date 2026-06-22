import logging
import re
from collections import Counter

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "dare",
    "ought", "used", "this", "that", "these", "those", "i", "you", "he",
    "she", "it", "we", "they", "me", "him", "her", "us", "them", "my",
    "your", "his", "its", "our", "their", "mine", "yours", "hers", "its",
    "ours", "theirs", "what", "which", "who", "whom", "whose", "when",
    "where", "why", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "because", "as", "until",
    "while", "about", "between", "through", "during", "before", "after",
    "above", "below", "up", "down", "out", "off", "over", "under", "again",
    "further", "then", "once", "here", "there", "when", "where", "why",
    "how", "also", "into", "upon", "get", "got", "new", "says", "said",
    "like", "make", "made", "year", "years", "time", "way", "day", "days",
    "one", "two", "first", "last", "back", "even", "still", "much",
}

PRIORITY_PATTERNS = [
    (r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", 3),
    (r"\b[A-Z]{2,}\b", 2),
    (r"\b[a-z]{4,}\b", 1),
]


def extract_keywords_from_text(text, weight=1):
    if not text:
        return []
    words = re.findall(r"\b[\w]{3,}\b", text.lower())
    return [w for w in words if w not in STOPWORDS]


def extract_entities(text):
    if not text:
        return []
    return re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)


def generate_tags(title, content):
    candidates = Counter()

    if title:
        candidates[title.strip()] += 10

    title_keywords = extract_keywords_from_text(title)
    for kw in title_keywords:
        candidates[kw] += 3

    heading_matches = re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", content, re.IGNORECASE | re.DOTALL)
    for heading in heading_matches:
        heading_clean = re.sub(r"<[^>]+>", "", heading)
        keywords = extract_keywords_from_text(heading_clean)
        for kw in keywords:
            candidates[kw] += 2

    body_text = re.sub(r"<[^>]+>", " ", content)
    keywords = extract_keywords_from_text(body_text)
    for kw in keywords:
        candidates[kw] += 1

    title_entities = extract_entities(title)
    for entity in title_entities:
        candidates[entity.lower()] += 5

    body_entities = extract_entities(body_text)
    for entity in body_entities:
        candidates[entity.lower()] += 2

    stopwords_lower = {w.lower() for w in STOPWORDS}
    filtered = {
        word: score
        for word, score in candidates.items()
        if word.lower() not in stopwords_lower and len(word) >= 3
    }

    sorted_tags = sorted(filtered.items(), key=lambda x: (-x[1], x[0]))
    top_tags = [tag.capitalize() for tag, _ in sorted_tags[:10]]

    return top_tags
