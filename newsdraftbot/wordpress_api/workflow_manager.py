import logging
from datetime import datetime
from typing import Optional

from wordpress_api.client import WordPressClient, WordPressAPIError
from wordpress_api.post_manager import PostManager
from wordpress_api.media_manager import MediaManager
from wordpress_api.reporter_manager import ReporterManager

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    pass


class WorkflowManager:
    def __init__(
        self,
        client: WordPressClient,
        post_manager: PostManager,
        media_manager: MediaManager,
        reporter_manager: ReporterManager,
    ):
        self.client = client
        self.post_manager = post_manager
        self.media_manager = media_manager
        self.reporter_manager = reporter_manager

    def save_draft(
        self,
        title: str,
        content: str = "",
        excerpt: str = "",
        categories: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        featured_media_id: Optional[int] = None,
        author_id: Optional[int] = None,
        reporter_name: Optional[str] = None,
        existing_post_id: Optional[int] = None,
    ) -> dict:
        if existing_post_id:
            result = self.post_manager.update(
                post_id=existing_post_id,
                title=title,
                content=content,
                excerpt=excerpt,
                categories=categories,
                tags=tags,
                featured_media_id=featured_media_id,
                author_id=author_id,
                reporter_name=reporter_name,
                status="draft",
            )
            if not result:
                raise WorkflowError("Failed to update draft")
            return result

        result = self.post_manager.create(
            title=title,
            content=content,
            excerpt=excerpt,
            categories=categories,
            tags=tags,
            featured_media_id=featured_media_id,
            author_id=author_id,
            reporter_name=reporter_name,
            status="draft",
        )
        if not result:
            raise WorkflowError("Failed to create draft")
        return result

    def publish(
        self,
        title: str,
        content: str = "",
        excerpt: str = "",
        categories: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        featured_media_id: Optional[int] = None,
        author_id: Optional[int] = None,
        reporter_name: Optional[str] = None,
        existing_post_id: Optional[int] = None,
    ) -> dict:
        if existing_post_id:
            result = self.post_manager.update(
                post_id=existing_post_id,
                title=title,
                content=content,
                excerpt=excerpt,
                categories=categories,
                tags=tags,
                featured_media_id=featured_media_id,
                author_id=author_id,
                reporter_name=reporter_name,
                status="publish",
            )
            if not result:
                raise WorkflowError("Failed to publish post")
            return result

        result = self.post_manager.create(
            title=title,
            content=content,
            excerpt=excerpt,
            categories=categories,
            tags=tags,
            featured_media_id=featured_media_id,
            author_id=author_id,
            reporter_name=reporter_name,
            status="publish",
        )
        if not result:
            raise WorkflowError("Failed to publish post")
        return result

    def schedule(
        self,
        title: str,
        content: str = "",
        excerpt: str = "",
        categories: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        featured_media_id: Optional[int] = None,
        author_id: Optional[int] = None,
        reporter_name: Optional[str] = None,
        scheduled_date: Optional[str] = None,
        existing_post_id: Optional[int] = None,
    ) -> dict:
        if not scheduled_date:
            raise WorkflowError("Scheduled date is required")

        if existing_post_id:
            result = self.post_manager.update(
                post_id=existing_post_id,
                title=title,
                content=content,
                excerpt=excerpt,
                categories=categories,
                tags=tags,
                featured_media_id=featured_media_id,
                author_id=author_id,
                reporter_name=reporter_name,
                status="future",
                schedule_date=scheduled_date,
            )
            if not result:
                raise WorkflowError("Failed to schedule post")
            return result

        result = self.post_manager.create(
            title=title,
            content=content,
            excerpt=excerpt,
            categories=categories,
            tags=tags,
            featured_media_id=featured_media_id,
            author_id=author_id,
            reporter_name=reporter_name,
            status="future",
            schedule_date=scheduled_date,
        )
        if not result:
            raise WorkflowError("Failed to schedule post")
        return result

    def upload_featured_image(self, file_path: str) -> Optional[dict]:
        result = self.media_manager.upload(file_path)
        if not result:
            raise WorkflowError("Failed to upload featured image")
        return result
