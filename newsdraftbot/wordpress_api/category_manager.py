import logging
from typing import Optional

from wordpress_api.client import WordPressClient, WordPressAPIError

logger = logging.getLogger(__name__)


class CategoryManager:
    def __init__(self, client: WordPressClient):
        self.client = client

    def get_all(self) -> list[dict]:
        return self.client.get_all_paginated("categories")

    def search(self, name: str) -> list[dict]:
        results = self.client.get("categories", params={"search": name, "per_page": 20})
        return [r for r in results if r.get("name", "").lower() == name.lower()]

    def get_by_id(self, category_id: int) -> Optional[dict]:
        try:
            return self.client.get(f"categories/{category_id}")
        except WordPressAPIError:
            return None

    def create(self, name: str, parent_id: int = None) -> dict:
        data = {"name": name}
        if parent_id:
            data["parent"] = parent_id
        result = self.client.post("categories", json_data=data)
        logger.info(f"Created category: {name} (ID={result.get('id')})")
        return result

    def get_or_create(self, name: str) -> Optional[int]:
        try:
            results = self.client.get("categories", params={"search": name, "per_page": 5})
            for cat in results:
                if cat.get("name", "").lower() == name.lower():
                    logger.info(f"Found category: {name} (ID={cat['id']})")
                    return cat["id"]
        except WordPressAPIError as e:
            logger.warning(f"Category search failed for '{name}', will try creating: {e}")

        try:
            created = self.create(name)
            return created.get("id")
        except WordPressAPIError as e:
            logger.error(f"Failed to create category '{name}': {e}")
            return None

    def resolve_ids(self, category_names: list[str]) -> list[int]:
        ids = []
        for name in category_names:
            cat_id = self.get_or_create(name.strip())
            if cat_id:
                ids.append(cat_id)
        return ids
