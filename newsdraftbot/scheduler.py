import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from config import Config
from database import Article, db

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
_app = None


def init_scheduler(app):
    global _app
    _app = app
    with app.app_context():
        schedule_pending_articles()

    interval_minutes = Config.CHECK_INTERVAL_MINUTES
    scheduler.add_job(
        func=lambda: fetch_and_schedule(app),
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="fetch_articles",
        name="Fetch new articles",
        replace_existing=True,
    )

    scheduler.add_job(
        func=lambda: process_scheduled(app),
        trigger=IntervalTrigger(minutes=1),
        id="process_scheduled",
        name="Process scheduled publications",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started")


def fetch_and_schedule(app):
    with app.app_context():
        from scraper import fetch_and_save_articles
        from tag_generator import generate_tags
        from category_generator import generate_categories, ensure_default_mappings
        from excerpt_generator import generate_excerpt
        from image_processor import process_image
        from wordpress import upload_image, create_post
        from facebook_publisher import share_to_facebook_page

        ensure_default_mappings()
        articles = fetch_and_save_articles()

        for article in articles:
            try:
                tags = generate_tags(article.title, article.content or "")
                article.tags = tags
                categories = generate_categories(article.title, article.content or "")
                article.categories = categories
                excerpt = generate_excerpt(article.content or "")
                article.excerpt = excerpt

                if article.featured_image:
                    local_image_web_path = process_image(article.featured_image, article.id)
                    if local_image_web_path:
                        # Convert relative web path to absolute filesystem path for upload_image
                        import os
                        local_image_abs_path = os.path.join(app.root_path, local_image_web_path.lstrip('/'))
                        wp_image = upload_image(local_image_abs_path)
                        if wp_image:
                            article.wordpress_featured_media_id = wp_image["id"]
                            wp_post = create_post(
                                title=article.title,
                                content=article.content or "",
                                excerpt=article.excerpt or "",
                                tags=article.tags or [],
                                categories=article.categories or [],
                                featured_image_id=article.wordpress_featured_media_id,
                                status="draft",
                            )
                            if wp_post:
                                article.wordpress_post_id = wp_post["id"]
                                article.wordpress_url = wp_post.get("link")
                                article.status = "DRAFT"
                            else:
                                article.status = "FAILED"
                        else:
                            article.status = "FAILED"
                    else:
                        wp_post = create_post(
                            title=article.title,
                            content=article.content or "",
                            excerpt=article.excerpt or "",
                            tags=article.tags or [],
                            categories=article.categories or [],
                            featured_image_id=None,
                            status="draft",
                        )
                        if wp_post:
                            article.wordpress_post_id = wp_post["id"]
                            article.wordpress_url = wp_post.get("link")
                            article.status = "DRAFT"
                        else:
                            article.status = "FAILED"
                else:
                    wp_post = create_post(
                        title=article.title,
                        content=article.content or "",
                        excerpt=article.excerpt or "",
                        tags=article.tags or [],
                        categories=article.categories or [],
                        featured_image_id=None,
                        status="draft",
                    )
                    if wp_post:
                        article.wordpress_post_id = wp_post["id"]
                        article.wordpress_url = wp_post.get("link")
                        article.status = "DRAFT"
                    else:
                        article.status = "FAILED"

                db.session.commit()
                logger.info(f"Processed article: {article.title} -> {article.status}")

            except Exception as e:
                logger.error(f"Failed to process article {article.title}: {e}")
                article.status = "FAILED"
                db.session.commit()


def process_scheduled(app):
    with app.app_context():
        from wordpress import publish_post

        now = datetime.now(timezone.utc)
        scheduled = Article.query.filter(
            Article.status == "SCHEDULED",
            Article.scheduled_time <= now,
        ).all()

        for article in scheduled:
            try:
                if article.wordpress_post_id:
                    result = publish_post(article.wordpress_post_id)
                    if result:
                        article.status = "PUBLISHED"
                        article.wordpress_url = result.get("link")
                        db.session.commit()
                        logger.info(f"Published scheduled article: {article.title}")

                        if Config.AUTO_SHARE_TO_FACEBOOK and article.wordpress_url:
                            fb_result = share_to_facebook_page(article.title, article.wordpress_url)
                            if fb_result.get("success"):
                                article.share_count = (article.share_count or 0) + 1
                                db.session.commit()
                    else:
                        logger.error(f"Failed to publish article: {article.title}")
            except Exception as e:
                logger.error(f"Error publishing scheduled article {article.title}: {e}")


def schedule_pending_articles():
    pending = Article.query.filter(
        Article.status == "SCHEDULED",
        Article.scheduled_time > datetime.now(timezone.utc),
    ).all()

    for article in pending:
        schedule_article_publication(article)


def schedule_article_publication(article):
    if article.scheduled_time:
        scheduler.add_job(
            func=lambda: publish_single_article(article.id),
            trigger=DateTrigger(run_date=article.scheduled_time),
            id=f"publish_{article.id}",
            name=f"Publish: {article.title[:50]}",
            replace_existing=True,
        )
        logger.info(f"Scheduled publication: {article.title} at {article.scheduled_time}")


def publish_single_article(article_id):
    with _app.app_context():
        from wordpress import publish_post

        article = Article.query.get(article_id)
        if article and article.wordpress_post_id:
            result = publish_post(article.wordpress_post_id)
            if result:
                article.status = "PUBLISHED"
                article.wordpress_url = result.get("link")
                db.session.commit()
                logger.info(f"Published: {article.title}")

                if Config.AUTO_SHARE_TO_FACEBOOK and article.wordpress_url:
                    fb_result = share_to_facebook_page(article.title, article.wordpress_url)
                    if fb_result.get("success"):
                        article.share_count = (article.share_count or 0) + 1
                        db.session.commit()


def cancel_scheduled_publication(article_id):
    job_id = f"publish_{article_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Cancelled scheduled publication for article {article_id}")


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
