import logging
from typing import Optional

from wordpress_api.client import WordPressClient, WordPressAPIError

logger = logging.getLogger(__name__)


class AuthorManager:
    def __init__(self, client: WordPressClient):
        self.client = client
        self._cache: Optional[list[dict]] = None

    def get_all(self) -> list[dict]:
        if self._cache is not None:
            return self._cache
        self._cache = self.client.get_all_paginated("users")
        return self._cache

    def get_by_id(self, author_id: int) -> Optional[dict]:
        try:
            return self.client.get(f"users/{author_id}")
        except WordPressAPIError:
            return None

    def get_current_user(self) -> dict:
        return self.client.get("users/me")

    def clear_cache(self):
        self._cache = None
