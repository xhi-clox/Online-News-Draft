import logging
from typing import Optional

from wordpress_api.client import WordPressClient, WordPressAPIError

logger = logging.getLogger(__name__)


class TagManager:
    def __init__(self, client: WordPressClient):
        self.client = client

    def get_all(self) -> list[dict]:
        return self.client.get_all_paginated("tags")

    def search(self, name: str) -> list[dict]:
        results = self.client.get("tags", params={"search": name, "per_page": 20})
        return [r for r in results if r.get("name", "").lower() == name.lower()]

    def get_by_id(self, tag_id: int) -> Optional[dict]:
        try:
            return self.client.get(f"tags/{tag_id}")
        except WordPressAPIError:
            return None

    def create(self, name: str) -> dict:
        result = self.client.post("tags", json_data={"name": name})
        logger.info(f"Created tag: {name} (ID={result.get('id')})")
        return result

    def get_or_create(self, name: str) -> Optional[int]:
        try:
            results = self.client.get("tags", params={"search": name, "per_page": 5})
            for tag in results:
                if tag.get("name", "").lower() == name.lower():
                    logger.info(f"Found tag: {name} (ID={tag['id']})")
                    return tag["id"]
        except WordPressAPIError as e:
            logger.warning(f"Tag search failed for '{name}', will try creating: {e}")

        try:
            created = self.create(name)
            return created.get("id")
        except WordPressAPIError as e:
            logger.error(f"Failed to create tag '{name}': {e}")
            return None

    def resolve_ids(self, tag_names: list[str]) -> list[int]:
        ids = []
        for name in tag_names:
            tag_id = self.get_or_create(name.strip())
            if tag_id:
                ids.append(tag_id)
        return ids
