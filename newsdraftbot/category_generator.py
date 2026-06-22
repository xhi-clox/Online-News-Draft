import logging
import re

from database import CategoryMapping, db

logger = logging.getLogger(__name__)

DEFAULT_MAPPINGS = {
    "politics": "Politics",
    "election": "Politics",
    "government": "Politics",
    "president": "Politics",
    "congress": "Politics",
    "senate": "Politics",
    "football": "Sports",
    "cricket": "Sports",
    "soccer": "Sports",
    "basketball": "Sports",
    "tennis": "Sports",
    "baseball": "Sports",
    "ai": "Technology",
    "software": "Technology",
    "tech": "Technology",
    "digital": "Technology",
    "computer": "Technology",
    "cyber": "Technology",
    "app": "Technology",
    "stock": "Business",
    "market": "Business",
    "economy": "Business",
    "finance": "Business",
    "bank": "Business",
    "trade": "Business",
    "health": "Health",
    "medical": "Health",
    "hospital": "Health",
    "disease": "Health",
    "vaccine": "Health",
    "science": "Science",
    "research": "Science",
    "space": "Science",
    "climate": "Environment",
    "weather": "Environment",
    "energy": "Environment",
    "education": "Education",
    "school": "Education",
    "university": "Education",
    "movie": "Entertainment",
    "music": "Entertainment",
    "film": "Entertainment",
    "celebrity": "Entertainment",
    "sport": "Sports",
}


def ensure_default_mappings():
    for keyword, category in DEFAULT_MAPPINGS.items():
        existing = CategoryMapping.query.filter_by(keyword=keyword).first()
        if not existing:
            mapping = CategoryMapping(keyword=keyword, category=category)
            db.session.add(mapping)
    db.session.commit()


def get_custom_mappings():
    mappings = CategoryMapping.query.all()
    return {m.keyword: m.category for m in mappings}


def add_mapping(keyword, category):
    existing = CategoryMapping.query.filter_by(keyword=keyword.lower().strip()).first()
    if existing:
        existing.category = category.strip()
    else:
        mapping = CategoryMapping(keyword=keyword.lower().strip(), category=category.strip())
        db.session.add(mapping)
    db.session.commit()


def delete_mapping(mapping_id):
    mapping = CategoryMapping.query.get(mapping_id)
    if mapping:
        db.session.delete(mapping)
        db.session.commit()


DEFAULT_CATEGORIES = ["এক্সক্লুসিভ", "জাতীয়", "খবর"]


def generate_categories(title, content, custom_mappings=None):
    if custom_mappings is None:
        custom_mappings = get_custom_mappings()

    text = f"{title} {content}".lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)

    matched_categories = []
    for keyword, category in sorted(custom_mappings.items(), key=lambda x: -len(x[0])):
        if keyword.lower() in text:
            if category not in matched_categories:
                matched_categories.append(category)

    if not matched_categories:
        matched_categories.append("Uncategorized")

    for cat in reversed(DEFAULT_CATEGORIES):
        if cat not in matched_categories:
            matched_categories.insert(0, cat)

    return matched_categories
