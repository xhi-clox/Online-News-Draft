import logging
from typing import Optional

from wordpress_api.client import WordPressClient, WordPressAPIError

logger = logging.getLogger(__name__)


class ReporterManager:
    def __init__(self, client: WordPressClient):
        self.client = client
        self._acf_available: Optional[bool] = None

    def check_acf_available(self) -> bool:
        if self._acf_available is not None:
            return self._acf_available
        try:
            root = self.client.get("")
            if isinstance(root, dict):
                namespaces = root.get("namespaces", [])
                self._acf_available = "acf/v3" in namespaces
                if self._acf_available:
                    logger.info("ACF plugin detected on WordPress site")
                else:
                    logger.info("ACF plugin not detected, using post meta")
            else:
                self._acf_available = False
        except WordPressAPIError as e:
            logger.warning(f"Could not detect ACF: {e}")
            self._acf_available = False
        return self._acf_available

    REPORTER_META_KEY = "reporter_name"
    REPORTER_ACF_FIELD = "reporter_name"

    def build_reporter_data(self, wordpress_author_id: Optional[int], reporter_name: Optional[str]) -> dict:
        fields = {}
        use_acf = self.check_acf_available()

        if wordpress_author_id:
            fields["author"] = int(wordpress_author_id)

        if not reporter_name:
            return fields

        if use_acf:
            fields["acf"] = {self.REPORTER_ACF_FIELD: reporter_name}
            logger.info(f"Using ACF field '{self.REPORTER_ACF_FIELD}' for reporter: {reporter_name}")
        else:
            fields["meta_input"] = {self.REPORTER_META_KEY: reporter_name}
            logger.info(f"Using post meta key '{self.REPORTER_META_KEY}' for reporter: {reporter_name}")

        logger.debug(f"Reporter data built (ACF={use_acf}): author={wordpress_author_id}, reporter={reporter_name}")
        return fields

    def extract_reporter_from_post(self, post: dict) -> dict:
        result = {"author_id": None, "reporter_name": None}
        if not post:
            return result
        result["author_id"] = post.get("author")
        acf = post.get("acf") or {}
        if acf and acf.get(self.REPORTER_ACF_FIELD):
            result["reporter_name"] = acf[self.REPORTER_ACF_FIELD]
        else:
            meta = post.get("meta") or {}
            result["reporter_name"] = meta.get(self.REPORTER_META_KEY)
        return result
