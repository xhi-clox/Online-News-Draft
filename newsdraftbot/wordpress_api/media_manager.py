import logging
import mimetypes
import os
from typing import Optional

from wordpress_api.client import WordPressClient, WordPressAPIError

logger = logging.getLogger(__name__)


class MediaManager:
    def __init__(self, client: WordPressClient):
        self.client = client

    def upload(self, file_path: str) -> Optional[dict]:
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None

        filename = os.path.basename(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "image/jpeg"

        with open(file_path, "rb") as f:
            try:
                result = self.client.post(
                    "media",
                    files={"file": (filename, f, mime_type)},
                )
                media_id = result.get("id")
                media_url = result.get("source_url")
                logger.info(f"Image uploaded: ID={media_id}, URL={media_url}")
                return {"id": media_id, "url": media_url}
            except WordPressAPIError as e:
                logger.error(f"Image upload failed: {e}")
                return None

    def get(self, media_id: int) -> Optional[dict]:
        try:
            return self.client.get(f"media/{media_id}")
        except WordPressAPIError:
            return None

    def delete(self, media_id: int) -> bool:
        try:
            self.client.delete(f"media/{media_id}")
            logger.info(f"Media deleted: ID={media_id}")
            return True
        except WordPressAPIError as e:
            logger.error(f"Failed to delete media {media_id}: {e}")
            return False
