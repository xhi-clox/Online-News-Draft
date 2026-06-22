import logging
from typing import Optional

from wordpress_api.client import WordPressClient, WordPressAPIError
from wordpress_api.category_manager import CategoryManager
from wordpress_api.tag_manager import TagManager
from wordpress_api.reporter_manager import ReporterManager

logger = logging.getLogger(__name__)


class PostValidationError(ValueError):
    pass


class PostManager:
    def __init__(
        self,
        client: WordPressClient,
        category_manager: CategoryManager = None,
        tag_manager: TagManager = None,
        reporter_manager: ReporterManager = None,
    ):
        self.client = client
        self.categories = category_manager or CategoryManager(client)
        self.tags = tag_manager or TagManager(client)
        self.reporter_manager = reporter_manager or ReporterManager(client)

    def create(
        self,
        title: str,
        content: str = "",
        excerpt: str = "",
        status: str = "draft",
        categories: list[str] = None,
        tags: list[str] = None,
        featured_media_id: int = None,
        author_id: int = None,
        reporter_name: str = None,
        schedule_date: str = None,
    ) -> Optional[dict]:
        post_data = self._build_post_data(
            title=title,
            content=content,
            excerpt=excerpt,
            status=status,
            categories=categories,
            tags=tags,
            featured_media_id=featured_media_id,
            author_id=author_id,
            reporter_name=reporter_name,
            schedule_date=schedule_date,
        )

        try:
            result = self.client.post("posts", json_data=post_data)
            logger.info(
                f"Post created: ID={result.get('id')}, status={result.get('status')}"
            )
            return result
        except WordPressAPIError as e:
            logger.error(f"Post creation failed: {e}")
            raise

    def update(
        self,
        post_id: int,
        title: str = None,
        content: str = None,
        excerpt: str = None,
        status: str = None,
        categories: list[str] = None,
        tags: list[str] = None,
        featured_media_id: int = None,
        author_id: int = None,
        reporter_name: str = None,
        schedule_date: str = None,
    ) -> Optional[dict]:
        post_data = self._build_post_data(
            title=title,
            content=content,
            excerpt=excerpt,
            status=status,
            categories=categories,
            tags=tags,
            featured_media_id=featured_media_id,
            author_id=author_id,
            reporter_name=reporter_name,
            schedule_date=schedule_date,
        )
        if not post_data:
            logger.warning("No data provided for post update")
            return None

        try:
            result = self.client.post(f"posts/{post_id}", json_data=post_data)
            logger.info(
                f"Post updated: ID={result.get('id')}, status={result.get('status')}"
            )
            return result
        except WordPressAPIError as e:
            logger.error(f"Post update failed for ID {post_id}: {e}")
            raise

    def get(self, post_id: int) -> Optional[dict]:
        try:
            return self.client.get(f"posts/{post_id}")
        except WordPressAPIError:
            return None

    def publish(self, post_id: int) -> Optional[dict]:
        return self.update(post_id, status="publish")

    def delete(self, post_id: int) -> bool:
        try:
            self.client.delete(f"posts/{post_id}")
            logger.info(f"Post deleted: ID={post_id}")
            return True
        except WordPressAPIError as e:
            logger.error(f"Failed to delete post {post_id}: {e}")
            return False

    def validate_author(self, author_id: int) -> bool:
        try:
            user = self.client.get(f"users/{author_id}")
            return user is not None
        except WordPressAPIError:
            return False

    def validate_categories(self, category_ids: list[int]) -> list[dict]:
        valid = []
        for cid in category_ids:
            try:
                cat = self.client.get(f"categories/{cid}")
                if cat:
                    valid.append(cat)
            except WordPressAPIError:
                logger.warning(f"Category ID {cid} not found on WordPress")
        return valid

    REPORTER_HTML_TEMPLATE = '<div class="newsdraft-reporter" style="font-size:0.95rem;color:#555;margin:0 0 8px 0;font-style:italic;">প্রতিবেদক: {name}</div>'

    def _build_post_data(
        self,
        title: str = None,
        content: str = None,
        excerpt: str = None,
        status: str = None,
        categories: list[str] = None,
        tags: list[str] = None,
        featured_media_id: int = None,
        author_id: int = None,
        reporter_name: str = None,
        schedule_date: str = None,
    ) -> dict:
        post_data = {}

        if title is not None:
            post_data["title"] = title
        if content is not None:
            if reporter_name:
                content = self._inject_reporter_into_content(content, reporter_name)
            post_data["content"] = content
        if excerpt is not None:
            post_data["excerpt"] = excerpt
        if status is not None:
            post_data["status"] = status
        if featured_media_id is not None:
            post_data["featured_media"] = int(featured_media_id)
        if schedule_date is not None:
            post_data["date"] = schedule_date

        if categories is not None:
            post_data["categories"] = self.categories.resolve_ids(categories)
        if tags is not None:
            post_data["tags"] = self.tags.resolve_ids(tags)

        reporter_fields = self.reporter_manager.build_reporter_data(
            wordpress_author_id=author_id,
            reporter_name=reporter_name,
        )
        post_data.update(reporter_fields)

        if author_id is not None and "author" not in post_data:
            post_data["author"] = int(author_id)

        return post_data

    def _inject_reporter_into_content(self, content: str, reporter_name: str) -> str:
        reporter_html = self.REPORTER_HTML_TEMPLATE.format(name=reporter_name)
        if reporter_html not in content:
            content = reporter_html + content
        return content
