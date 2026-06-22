import os
import logging
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request, send_file

from config import Config
from database import Article, CategoryMapping, Reporter, SavedPrompt, AIUsage, db, init_db

app = Flask(__name__)
app.config.from_object(Config)


@app.template_filter("dt")
def format_datetime(value, fmt="%Y-%m-%d %H:%M"):
    if value is None:
        return ""
    if isinstance(value, str):
        return value[: len(fmt)]
    return value.strftime(fmt)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

init_db(app)

wp_client = None
category_manager = None
author_manager = None
tag_manager = None
media_manager = None
post_manager = None
reporter_manager = None
workflow_manager = None


def _init_wp_managers():
    global wp_client, category_manager, author_manager, tag_manager, media_manager, post_manager, reporter_manager, workflow_manager
    try:
        wp_client = WordPressClient.from_config(Config)
        category_manager = CategoryManager(wp_client)
        author_manager = AuthorManager(wp_client)
        tag_manager = TagManager(wp_client)
        media_manager = MediaManager(wp_client)
        reporter_manager = ReporterManager(wp_client)
        post_manager = PostManager(wp_client, category_manager, tag_manager, reporter_manager)
        workflow_manager = WorkflowManager(wp_client, post_manager, media_manager, reporter_manager)
        logger.info("WordPress API managers initialized")
    except WordPressAPIError as e:
        logger.warning(f"WordPress not configured: {e}")


from category_generator import ensure_default_mappings, get_custom_mappings, add_mapping, delete_mapping, generate_categories
from excerpt_generator import generate_excerpt
from image_processor import process_image
from scraper import fetch_and_save_articles
from tag_generator import generate_tags
from wordpress import create_post, publish_post, update_post, upload_image
from wordpress_api import (
    WordPressClient,
    WordPressAPIError,
    WordPressAuthError,
    CategoryManager,
    AuthorManager,
    TagManager,
    MediaManager,
    PostManager,
    ReporterManager,
    WorkflowManager,
    WorkflowError,
)
from facebook_publisher import share_to_facebook_page
from gmail_service import get_gmail_service, fetch_emails, get_message_details, download_attachment
import ai_tweaker

with app.app_context():
    ensure_default_mappings()
    _init_wp_managers()


def get_stats():
    total = Article.query.count()
    drafts = Article.query.filter_by(status="DRAFT").count()
    scheduled = Article.query.filter_by(status="SCHEDULED").count()
    published = Article.query.filter_by(status="PUBLISHED").count()
    failed = Article.query.filter_by(status="FAILED").count()
    new_count = Article.query.filter_by(status="NEW").count()
    return {
        "total": total,
        "drafts": drafts,
        "scheduled": scheduled,
        "published": published,
        "failed": failed,
        "new": new_count,
    }


@app.route("/")
def dashboard():
    stats = get_stats()
    recent_articles = (
        Article.query.order_by(Article.created_at.desc()).limit(10).all()
    )
    return render_template(
        "dashboard.html", stats=stats, articles=recent_articles
    )


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/articles")
def article_list():
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    per_page = 20

    query = Article.query.order_by(Article.created_at.desc())
    if status:
        query = query.filter_by(status=status.upper())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "dashboard.html",
        stats=get_stats(),
        articles=pagination.items,
        pagination=pagination,
        active_filter=status,
        show_all=True,
    )


@app.route("/articles/<int:article_id>")
def article_detail(article_id):
    article = Article.query.get_or_404(article_id)
    reporters = Reporter.query.order_by(Reporter.name).all()
    
    local_image_path = os.path.join(app.root_path, 'static', 'uploads', f'article_{article.id}.jpg')
    has_local_image = os.path.exists(local_image_path)
    
    return render_template(
        "article.html",
        article=article,
        reporters=reporters,
        has_local_image=has_local_image,
        config=Config,
    )


@app.route("/articles/<int:article_id>/ai-tweak", methods=["POST"])
def ai_tweak_article(article_id):
    article = Article.query.get_or_404(article_id)
    data = request.get_json() or {}
    instruction = data.get("instruction", "")
    try:
        tweaked = ai_tweaker.tweak_article(article.title, article.content or "", instruction)
        remaining = ai_tweaker.quota_remaining()
        return jsonify({"success": True, "content": tweaked, "remaining": remaining})
    except Exception as e:
        logger.error(f"AI tweak error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/articles/<int:article_id>/ai-edit-all", methods=["POST"])
def ai_edit_all(article_id):
    article = Article.query.get_or_404(article_id)
    data = request.get_json() or {}
    instruction = data.get("instruction", "")

    available_categories = None
    if category_manager:
        try:
            wp_cats = category_manager.get_all()
            available_categories = [c["name"] for c in wp_cats]
        except Exception:
            pass

    try:
        result = ai_tweaker.edit_full_article(
            title=article.title,
            content=article.content or "",
            excerpt=article.excerpt or "",
            tags=article.tags or [],
            categories=article.categories or [],
            reporter=article.reporter or "",
            available_categories=available_categories,
            instruction=instruction,
        )
        remaining = ai_tweaker.quota_remaining()

        tags_list = []
        if result.get("tags"):
            tags_list = [t.strip() for t in result["tags"].split(",") if t.strip()]
        cats_list = []
        if result.get("categories"):
            cats_list = [c.strip() for c in result["categories"].split(",") if c.strip()]

        exclusive_cat = "এক্সক্লুসিভ"
        if exclusive_cat not in cats_list:
            cats_list.insert(0, exclusive_cat)

        return jsonify({
            "success": True,
            "title": result.get("title", article.title),
            "content": result.get("content", article.content or ""),
            "excerpt": result.get("excerpt", article.excerpt or ""),
            "tags": tags_list,
            "categories": cats_list,
            "reporter": result.get("reporter", article.reporter or ""),
            "remaining": remaining,
        })
    except Exception as e:
        logger.error(f"AI full edit error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/saved-prompts", methods=["GET"])
def list_saved_prompts():
    prompts = SavedPrompt.query.order_by(SavedPrompt.created_at.desc()).all()
    return jsonify([p.to_dict() for p in prompts])


@app.route("/api/saved-prompts", methods=["POST"])
def save_prompt():
    data = request.get_json()
    name = data.get("name", "").strip()
    prompt_text = data.get("prompt_text", "").strip()
    if not name or not prompt_text:
        return jsonify({"success": False, "message": "Name and prompt text required"}), 400
    p = SavedPrompt(name=name, prompt_text=prompt_text)
    db.session.add(p)
    db.session.commit()
    return jsonify({"success": True, "prompt": p.to_dict()}), 201


@app.route("/api/saved-prompts/<int:prompt_id>", methods=["DELETE"])
def delete_saved_prompt(prompt_id):
    p = SavedPrompt.query.get_or_404(prompt_id)
    db.session.delete(p)
    db.session.commit()
    return jsonify({"success": True, "message": "Prompt deleted"})


@app.route("/api/ai-quota")
def ai_quota():
    remaining = ai_tweaker.quota_remaining()
    usage = ai_tweaker.get_today_usage()
    return jsonify({
        "used": usage.count,
        "limit": usage.limit,
        "remaining": remaining,
    })


@app.route("/articles/<int:article_id>/publish", methods=["POST"])
def publish_article(article_id):
    article = Article.query.get_or_404(article_id)
    if not post_manager:
        return jsonify({"success": False, "message": "WordPress not configured"}), 400
    try:
        if article.featured_image and not article.wordpress_featured_media_id:
            local_image_web_path = process_image(article.featured_image, article.id)
            if local_image_web_path:
                local_image_abs_path = os.path.join(app.root_path, local_image_web_path.lstrip('/'))
                wp_image = media_manager.upload(local_image_abs_path) if media_manager else upload_image(local_image_abs_path)
                if wp_image:
                    if isinstance(wp_image, dict):
                        article.wordpress_featured_media_id = wp_image.get("id") if "id" in wp_image else wp_image.get("id")
                    else:
                        article.wordpress_featured_media_id = wp_image["id"]
                    db.session.commit()

        if article.wordpress_post_id:
            result = post_manager.update(
                post_id=article.wordpress_post_id,
                title=article.title,
                content=article.content or "",
                excerpt=article.excerpt or "",
                tags=article.tags or [],
                categories=article.categories or [],
                featured_media_id=article.wordpress_featured_media_id,
                author_id=article.wordpress_author_id,
                reporter_name=article.reporter,
                status="publish",
            )
        else:
            result = post_manager.create(
                title=article.title,
                content=article.content or "",
                excerpt=article.excerpt or "",
                tags=article.tags or [],
                categories=article.categories or [],
                featured_media_id=article.wordpress_featured_media_id,
                author_id=article.wordpress_author_id,
                reporter_name=article.reporter,
                status="publish",
            )

        if result:
            article.wordpress_post_id = result["id"]
            article.wordpress_url = result.get("link")
            article.status = "PUBLISHED"
            db.session.commit()

            fb_share = None
            if Config.AUTO_SHARE_TO_FACEBOOK and article.wordpress_url:
                fb_share = share_to_facebook_page(article.title, article.wordpress_url)
                if fb_share.get("success"):
                    article.share_count = (article.share_count or 0) + 1
                    db.session.commit()

            msg = "Article published"
            if fb_share:
                msg += " | Facebook: " + ("shared" if fb_share["success"] else "failed - " + fb_share.get("message", ""))

            return jsonify({"success": True, "message": msg})

        return jsonify({"success": False, "message": "Failed to publish article"}), 500
    except WordPressAuthError as e:
        logger.error(f"Auth error during publish: {e}")
        return jsonify({"success": False, "message": "WordPress authentication failed. Please check your credentials."}), 401
    except WordPressAPIError as e:
        logger.error(f"WP API error during publish: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"Publish error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/articles/<int:article_id>/schedule", methods=["POST"])
def schedule_article(article_id):
    article = Article.query.get_or_404(article_id)
    data = request.get_json()
    scheduled_str = data.get("scheduled_time")

    if not scheduled_str:
        return jsonify({"success": False, "message": "Scheduled time required"}), 400

    try:
        scheduled_time = datetime.fromisoformat(scheduled_str)
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)

        article.scheduled_time = scheduled_time
        article.status = "SCHEDULED"
        db.session.commit()

        from scheduler import schedule_article_publication
        schedule_article_publication(article)

        return jsonify({"success": True, "message": "Article scheduled"})
    except ValueError:
        return jsonify({"success": False, "message": "Invalid date format"}), 400


@app.route("/articles/<int:article_id>/cancel-schedule", methods=["POST"])
def cancel_schedule(article_id):
    article = Article.query.get_or_404(article_id)
    article.scheduled_time = None
    article.status = "DRAFT"
    db.session.commit()

    from scheduler import cancel_scheduled_publication
    cancel_scheduled_publication(article_id)

    return jsonify({"success": True, "message": "Schedule cancelled"})


@app.route("/articles/<int:article_id>/delete", methods=["POST"])
def delete_article(article_id):
    article = Article.query.get_or_404(article_id)
    db.session.delete(article)
    db.session.commit()
    return jsonify({"success": True, "message": "Article deleted"})


@app.route("/articles/<int:article_id>/increment-share", methods=["POST"])
def increment_share(article_id):
    article = Article.query.get_or_404(article_id)
    article.share_count = (article.share_count or 0) + 1
    db.session.commit()
    return jsonify({"success": True, "share_count": article.share_count})


@app.route("/articles/batch-delete", methods=["POST"])
def batch_delete_articles():
    data = request.get_json()
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"success": False, "message": "No IDs provided"}), 400
    deleted = Article.query.filter(Article.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"success": True, "deleted": deleted, "message": f"{deleted} article(s) deleted"})


@app.route("/articles/<int:article_id>/update", methods=["POST"])
def update_article(article_id):
    article = Article.query.get_or_404(article_id)
    data = request.get_json()
    if "title" in data:
        article.title = data["title"]
    if "content" in data:
        article.content = data["content"].replace('\r\n', '\n') if data["content"] else data["content"]
    if "excerpt" in data:
        article.excerpt = data["excerpt"]
    if "tags" in data:
        article.tags = data["tags"]
    if "categories" in data:
        article.categories = data["categories"]
    if "reporter" in data:
        article.reporter = data["reporter"]
    if "wordpress_author_id" in data:
        article.wordpress_author_id = data["wordpress_author_id"]
    if "wordpress_featured_media_id" in data:
        article.wordpress_featured_media_id = data["wordpress_featured_media_id"]
    db.session.commit()
    return jsonify({"success": True, "message": "Article updated"})


@app.route("/api/reporters", methods=["GET"])
def list_reporters():
    reporters = Reporter.query.order_by(Reporter.name).all()
    return jsonify([r.to_dict() for r in reporters])


@app.route("/api/reporters", methods=["POST"])
def add_reporter():
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "message": "Name required"}), 400
    existing = Reporter.query.filter_by(name=name).first()
    if existing:
        return jsonify({"success": True, "reporter": existing.to_dict()})
    reporter = Reporter(name=name)
    db.session.add(reporter)
    db.session.commit()
    return jsonify({"success": True, "reporter": reporter.to_dict()}), 201


@app.route("/articles/<int:article_id>/wp-save", methods=["POST"])
def wp_save_article(article_id):
    article = Article.query.get_or_404(article_id)
    if not post_manager:
        return jsonify({"success": False, "message": "WordPress not configured"}), 400
    data = request.get_json() or {}
    status = data.get("status", "draft")
    try:
        if article.wordpress_post_id:
            result = post_manager.update(
                post_id=article.wordpress_post_id,
                title=data.get("title", article.title),
                content=data.get("content", article.content or ""),
                excerpt=data.get("excerpt", article.excerpt or ""),
                tags=data.get("tags", article.tags or []),
                categories=data.get("categories", article.categories or []),
                featured_media_id=data.get("featured_media_id", article.wordpress_featured_media_id),
                author_id=data.get("author_id", article.wordpress_author_id),
                reporter_name=data.get("reporter", article.reporter),
                status=status,
            )
        else:
            result = post_manager.create(
                title=data.get("title", article.title),
                content=data.get("content", article.content or ""),
                excerpt=data.get("excerpt", article.excerpt or ""),
                tags=data.get("tags", article.tags or []),
                categories=data.get("categories", article.categories or []),
                featured_media_id=data.get("featured_media_id", article.wordpress_featured_media_id),
                author_id=data.get("author_id", article.wordpress_author_id),
                reporter_name=data.get("reporter", article.reporter),
                status=status,
                schedule_date=data.get("schedule_date"),
            )

        if result:
            article.wordpress_post_id = result["id"]
            article.wordpress_url = result.get("link")
            article.status = result.get("status", "DRAFT").upper()
            db.session.commit()
            return jsonify({
                "success": True,
                "message": f"Post saved as {result.get('status', 'draft')}",
                "wordpress_post_id": result["id"],
                "wordpress_url": result.get("link"),
                "status": result.get("status"),
            })

        return jsonify({"success": False, "message": "Failed to save to WordPress"}), 500
    except WordPressAuthError as e:
        logger.error(f"Auth error during WP save: {e}")
        return jsonify({"success": False, "message": "WordPress authentication failed. Check credentials."}), 401
    except WordPressAPIError as e:
        logger.error(f"WP API error during save: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"WP save error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/suggest-tags", methods=["POST"])
def suggest_tags():
    data = request.get_json()
    title = data.get("title", "")
    content = data.get("content", "")
    tags = generate_tags(title, content)
    return jsonify({"tags": tags})


@app.route("/api/categories", methods=["GET"])
def fetch_wp_categories():
    if not category_manager:
        return jsonify({"categories": [], "error": "WordPress not configured"}), 400
    try:
        cats = category_manager.get_all()
        return jsonify({"categories": [{"id": c["id"], "name": c["name"], "slug": c["slug"]} for c in cats]})
    except Exception as e:
        logger.error(f"Category fetch error: {e}")
        return jsonify({"categories": [], "error": str(e)}), 500


@app.route("/api/wp/authors", methods=["GET"])
def api_wp_authors():
    if not author_manager:
        return jsonify({"authors": [], "error": "WordPress not configured"}), 400
    try:
        authors = author_manager.get_all()
        return jsonify({
            "authors": [{"id": a["id"], "name": a["name"], "slug": a.get("slug", "")} for a in authors]
        })
    except Exception as e:
        logger.error(f"Author fetch error: {e}")
        return jsonify({"authors": [], "error": str(e)}), 500


@app.route("/api/wp/tags", methods=["GET"])
def api_wp_tags():
    if not tag_manager:
        return jsonify({"tags": [], "error": "WordPress not configured"}), 400
    try:
        tags = tag_manager.get_all()
        return jsonify({
            "tags": [{"id": t["id"], "name": t["name"], "slug": t.get("slug", "")} for t in tags]
        })
    except Exception as e:
        logger.error(f"Tag fetch error (WP server issue): {e}")
        return jsonify({"tags": [], "error": "WordPress tag endpoint unavailable. Tags selected from the editor will still be sent on publish."})


@app.route("/api/wp/tags/create", methods=["POST"])
def api_wp_create_tag():
    if not tag_manager:
        return jsonify({"success": False, "message": "WordPress not configured"}), 400
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "message": "Tag name required"}), 400
    try:
        tag_id = tag_manager.get_or_create(name)
        if tag_id:
            return jsonify({"success": True, "tag": {"id": tag_id, "name": name}})
        return jsonify({"success": False, "message": "Failed to create tag"}), 500
    except Exception as e:
        logger.error(f"Tag creation error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/wp/categories/create", methods=["POST"])
def api_wp_create_category():
    if not category_manager:
        return jsonify({"success": False, "message": "WordPress not configured"}), 400
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "message": "Category name required"}), 400
    try:
        cat_id = category_manager.get_or_create(name)
        if cat_id:
            return jsonify({"success": True, "category": {"id": cat_id, "name": name}})
        return jsonify({"success": False, "message": "Failed to create category"}), 500
    except Exception as e:
        logger.error(f"Category creation error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/wp/media/upload", methods=["POST"])
def api_wp_upload_media():
    if not media_manager:
        return jsonify({"success": False, "message": "WordPress not configured"}), 400
    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file provided"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "message": "Empty filename"}), 400

    temp_dir = os.path.join(app.root_path, "static", "uploads")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"upload_{os.urandom(4).hex()}_{file.filename}")
    try:
        file.save(temp_path)
        result = media_manager.upload(temp_path)
        if result:
            return jsonify({"success": True, "media": result})
        return jsonify({"success": False, "message": "Upload to WordPress failed"}), 500
    except Exception as e:
        logger.error(f"Media upload error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.route("/articles/<int:article_id>/wp-publish", methods=["POST"])
def wp_publish_article(article_id):
    article = Article.query.get_or_404(article_id)
    if not workflow_manager:
        return jsonify({"success": False, "message": "WordPress not configured"}), 400
    data = request.get_json() or {}
    action = data.get("action", "draft")
    try:
        status_map = {
            "draft": "draft",
            "publish": "publish",
            "schedule": "future",
            "update_draft": "draft",
            "update_publish": "publish",
            "update_schedule": "future",
        }
        wp_status = status_map.get(action, "draft")
        schedule_date = data.get("schedule_date") if action in ("schedule", "update_schedule") else None

        reporter_name = data.get("reporter", article.reporter)
        wordpress_author_id = data.get("wordpress_author_id", article.wordpress_author_id)

        title = data.get("title", article.title)
        content = data.get("content", article.content or "")
        excerpt = data.get("excerpt", article.excerpt or "")
        tags = data.get("tags", article.tags or [])
        categories = data.get("categories", article.categories or [])
        featured_media_id = data.get("featured_media_id", article.wordpress_featured_media_id)

        logger.info(f"Publishing article {article_id}: action={action}, tags={tags}, categories={categories}, reporter='{reporter_name}', author_id={wordpress_author_id}")

        if article.featured_image and not featured_media_id:
            local_image_web_path = process_image(article.featured_image, article.id)
            if local_image_web_path:
                local_image_abs_path = os.path.join(app.root_path, local_image_web_path.lstrip('/'))
                wp_image = workflow_manager.upload_featured_image(local_image_abs_path)
                if wp_image:
                    featured_media_id = wp_image["id"]
                    article.wordpress_featured_media_id = featured_media_id
                    db.session.commit()

        is_update = bool(article.wordpress_post_id)
        if action in ("update_draft", "update_publish", "update_schedule"):
            is_update = True

        if is_update:
            result = workflow_manager.save_draft(
                title=title,
                content=content,
                excerpt=excerpt,
                categories=categories,
                tags=tags,
                featured_media_id=featured_media_id,
                author_id=wordpress_author_id,
                reporter_name=reporter_name,
                existing_post_id=article.wordpress_post_id,
            )
            if wp_status == "publish":
                result = workflow_manager.publish(
                    title=title,
                    content=content,
                    excerpt=excerpt,
                    categories=categories,
                    tags=tags,
                    featured_media_id=featured_media_id,
                    author_id=wordpress_author_id,
                    reporter_name=reporter_name,
                    existing_post_id=article.wordpress_post_id,
                )
            elif wp_status == "future":
                result = workflow_manager.schedule(
                    title=title,
                    content=content,
                    excerpt=excerpt,
                    categories=categories,
                    tags=tags,
                    featured_media_id=featured_media_id,
                    author_id=wordpress_author_id,
                    reporter_name=reporter_name,
                    scheduled_date=schedule_date,
                    existing_post_id=article.wordpress_post_id,
                )
        else:
            if wp_status == "draft":
                result = workflow_manager.save_draft(
                    title=title, content=content, excerpt=excerpt,
                    categories=categories, tags=tags,
                    featured_media_id=featured_media_id,
                    author_id=wordpress_author_id, reporter_name=reporter_name,
                )
            elif wp_status == "publish":
                result = workflow_manager.publish(
                    title=title, content=content, excerpt=excerpt,
                    categories=categories, tags=tags,
                    featured_media_id=featured_media_id,
                    author_id=wordpress_author_id, reporter_name=reporter_name,
                )
            elif wp_status == "future":
                result = workflow_manager.schedule(
                    title=title, content=content, excerpt=excerpt,
                    categories=categories, tags=tags,
                    featured_media_id=featured_media_id,
                    author_id=wordpress_author_id, reporter_name=reporter_name,
                    scheduled_date=schedule_date,
                )
            else:
                result = workflow_manager.save_draft(
                    title=title, content=content, excerpt=excerpt,
                    categories=categories, tags=tags,
                    featured_media_id=featured_media_id,
                    author_id=wordpress_author_id, reporter_name=reporter_name,
                )

        if result:
            article.wordpress_post_id = result["id"]
            article.wordpress_url = result.get("link")
            article.title = title
            article.content = content
            article.excerpt = excerpt
            article.tags = tags
            article.categories = categories
            article.reporter = reporter_name
            article.wordpress_author_id = wordpress_author_id

            wp_status_upper = result.get("status", "draft").upper()
            if wp_status_upper == "FUTURE":
                article.status = "SCHEDULED"
                if schedule_date:
                    try:
                        article.scheduled_time = datetime.fromisoformat(schedule_date.replace("Z", "+00:00"))
                    except ValueError:
                        pass
            elif wp_status_upper == "PUBLISH":
                article.status = "PUBLISHED"
            else:
                article.status = "DRAFT"

            db.session.commit()

            fb_share = None
            if article.status == "PUBLISHED" and Config.AUTO_SHARE_TO_FACEBOOK and article.wordpress_url:
                fb_share = share_to_facebook_page(article.title, article.wordpress_url)
                if fb_share.get("success"):
                    article.share_count = (article.share_count or 0) + 1
                    db.session.commit()

            msg = f"Post {result.get('status', 'saved')} successfully"
            if fb_share:
                msg += " | Facebook: " + ("shared" if fb_share["success"] else "failed - " + fb_share.get("message", ""))

            return jsonify({
                "success": True,
                "message": msg,
                "wordpress_post_id": result["id"],
                "wordpress_url": result.get("link"),
                "status": result.get("status"),
                "facebook_share": fb_share,
            })

        return jsonify({"success": False, "message": "Failed to process post"}), 500

    except WordPressAuthError as e:
        logger.error(f"Auth error: {e}")
        return jsonify({"success": False, "message": "WordPress authentication failed. Check your credentials."}), 401
    except WordPressAPIError as e:
        logger.error(f"WP API error: {e}")
        error_msg = str(e)
        if "invalid_taxonomy" in error_msg.lower():
            error_msg = "Invalid category or tag. Please ensure categories exist on WordPress."
        elif "author_not_found" in error_msg.lower() or "invalid_author" in error_msg.lower():
            error_msg = "Selected author not found. Please choose a different author."
        return jsonify({"success": False, "message": error_msg}), 500
    except WorkflowError as e:
        logger.error(f"Workflow error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"Publish workflow error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/wp/tags/search", methods=["GET"])
def api_wp_tags_search():
    if not tag_manager:
        return jsonify({"tags": [], "error": "WordPress not configured"}), 400
    query = request.args.get("q", "").strip()
    try:
        if query:
            tags = tag_manager.search(query)
        else:
            tags = tag_manager.get_all()
        return jsonify({
            "tags": [{"id": t["id"], "name": t["name"], "slug": t.get("slug", "")} for t in tags]
        })
    except Exception as e:
        logger.error(f"Tag search error: {e}")
        return jsonify({"tags": [], "error": str(e)}), 500


@app.route("/api/wp/categories/search", methods=["GET"])
def api_wp_categories_search():
    if not category_manager:
        return jsonify({"categories": [], "error": "WordPress not configured"}), 400
    query = request.args.get("q", "").strip()
    try:
        if query:
            cats = category_manager.search(query)
        else:
            cats = category_manager.get_all()
        return jsonify({
            "categories": [{"id": c["id"], "name": c["name"], "slug": c.get("slug", "")} for c in cats]
        })
    except Exception as e:
        logger.error(f"Category search error: {e}")
        return jsonify({"categories": [], "error": str(e)}), 500


@app.route("/api/wp/acf-status", methods=["GET"])
def api_wp_acf_status():
    if not reporter_manager:
        return jsonify({"acf_available": False})
    try:
        acf = reporter_manager.check_acf_available()
        return jsonify({"acf_available": acf})
    except Exception:
        return jsonify({"acf_available": False})


@app.route("/api/wp/validate", methods=["GET"])
def api_wp_validate():
    if not wp_client:
        return jsonify({"valid": False, "message": "WordPress not configured"}), 400
    try:
        response = wp_client.get("")
        if response:
            return jsonify({"valid": True, "message": "Connection successful"})
        return jsonify({"valid": False, "message": "Unexpected response"}), 500
    except WordPressAuthError:
        return jsonify({"valid": False, "message": "Authentication failed. Check credentials."}), 401
    except WordPressAPIError as e:
        return jsonify({"valid": False, "message": str(e)}), 500


@app.route("/articles/<int:article_id>/process", methods=["POST"])
def process_article(article_id):
    article = Article.query.get_or_404(article_id)
    if not post_manager:
        return jsonify({"success": False, "message": "WordPress not configured"}), 400
    try:
        tags = generate_tags(article.title, article.content or "")
        article.tags = tags
        categories = generate_categories(article.title, article.content or "")
        article.categories = categories
        excerpt = generate_excerpt(article.content or "")
        article.excerpt = excerpt
        db.session.commit()

        wp_image = None
        if article.featured_image:
            local_image = process_image(article.featured_image, article.id)
            if local_image:
                wp_image = media_manager.upload(local_image) if media_manager else upload_image(local_image)

        wp_image_id = None
        if wp_image:
            if isinstance(wp_image, dict):
                wp_image_id = wp_image.get("id") if "id" in wp_image else wp_image.get("id")
            else:
                wp_image_id = wp_image["id"]
            article.wordpress_featured_media_id = wp_image_id
            db.session.commit()

        result = post_manager.create(
            title=article.title,
            content=article.content or "",
            excerpt=article.excerpt or "",
            tags=article.tags or [],
            categories=article.categories or [],
            featured_media_id=wp_image_id,
            author_id=article.wordpress_author_id,
            reporter_name=article.reporter,
            status="draft",
        )
        if result:
            article.wordpress_post_id = result["id"]
            article.wordpress_url = result.get("link")
            article.status = "DRAFT"
            db.session.commit()
            return jsonify({"success": True, "message": "Article processed and saved as draft"})
        else:
            article.status = "FAILED"
            db.session.commit()
            return jsonify({"success": False, "message": "Failed to create WordPress post"}), 500
    except WordPressAuthError as e:
        article.status = "FAILED"
        db.session.commit()
        return jsonify({"success": False, "message": "WordPress authentication failed. Check credentials."}), 401
    except WordPressAPIError as e:
        article.status = "FAILED"
        db.session.commit()
        return jsonify({"success": False, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"Process error: {e}")
        article.status = "FAILED"
        db.session.commit()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/fetch", methods=["POST"])
def fetch_articles():
    try:
        articles = fetch_and_save_articles()
        return jsonify({
            "success": True,
            "message": f"Fetched {len(articles)} new articles",
            "count": len(articles),
        })
    except Exception as e:
        logger.error(f"Fetch error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/process-all", methods=["POST"])
def process_all():
    new_articles = Article.query.filter_by(status="NEW").all()
    processed = 0
    errors = 0

    for article in new_articles:
        try:
            tags = generate_tags(article.title, article.content or "")
            article.tags = tags
            categories = generate_categories(article.title, article.content or "")
            article.categories = categories
            excerpt = generate_excerpt(article.content or "")
            article.excerpt = excerpt

            wp_image = None
            if article.featured_image:
                local_image = process_image(article.featured_image, article.id)
                if local_image:
                    wp_image = upload_image(local_image)

            wp_image_id = wp_image["id"] if wp_image else None
            result = create_post(
                title=article.title,
                content=article.content or "",
                excerpt=article.excerpt or "",
                tags=article.tags or [],
                categories=article.categories or [],
                featured_image_id=wp_image_id,
                status="draft",
                reporter=article.reporter,
            )
            if result:
                article.wordpress_post_id = result["id"]
                article.wordpress_url = result.get("link")
                article.status = "DRAFT"
                processed += 1
            else:
                article.status = "FAILED"
                errors += 1
            db.session.commit()
        except Exception as e:
            logger.error(f"Process all error for {article.title}: {e}")
            article.status = "FAILED"
            db.session.commit()
            errors += 1

    return jsonify({
        "success": True,
        "message": f"Processed {processed} articles, {errors} errors",
        "processed": processed,
        "errors": errors,
    })


@app.route("/settings")
def settings():
    mappings = CategoryMapping.query.all()
    stats = get_stats()
    return render_template(
        "settings.html", mappings=mappings, stats=stats, config=Config
    )


@app.route("/settings/mappings", methods=["GET"])
def get_mappings():
    mappings = CategoryMapping.query.all()
    return jsonify([m.to_dict() for m in mappings])


@app.route("/settings/mappings/add", methods=["POST"])
def add_mapping_route():
    data = request.get_json()
    keyword = data.get("keyword", "").strip().lower()
    category = data.get("category", "").strip()
    if not keyword or not category:
        return jsonify({"success": False, "message": "Keyword and category required"}), 400
    add_mapping(keyword, category)
    return jsonify({"success": True, "message": "Mapping added"})


@app.route("/settings/mappings/delete/<int:mapping_id>", methods=["POST"])
def delete_mapping_route(mapping_id):
    delete_mapping(mapping_id)
    return jsonify({"success": True, "message": "Mapping deleted"})


def update_dotenv(updates):
    import os
    dotenv_path = os.path.join(app.root_path, ".env")
    
    # Read existing content
    lines = []
    if os.path.exists(dotenv_path):
        with open(dotenv_path, "r") as f:
            lines = f.readlines()
            
    new_lines = []
    written_keys = set()
    
    # Update existing lines
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
            
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                written_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
            
    # Add new keys
    for key, val in updates.items():
        if key not in written_keys:
            new_lines.append(f"{key}={val}\n")
            
    with open(dotenv_path, "w") as f:
        f.writelines(new_lines)
        
    # Update Config object in memory
    for key, val in updates.items():
        if hasattr(Config, key):
            # Try to cast to int if it looks like one, or bool
            if val.lower() == "true":
                setattr(Config, key, True)
            elif val.lower() == "false":
                setattr(Config, key, False)
            elif val.isdigit():
                setattr(Config, key, int(val))
            else:
                setattr(Config, key, val)


@app.route("/settings/update-config", methods=["POST"])
def update_config():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
        
    try:
        update_dotenv(data)
        return jsonify({"success": True, "message": "Settings updated successfully"})
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/settings/update-logo-position", methods=["POST"])
def update_logo_position():
    data = request.get_json()
    position = data.get("position", "custom")
    valid_positions = ["custom", "top_left", "top_right", "bottom_left", "bottom_right", "center"]
    if position not in valid_positions:
        return jsonify({"success": False, "message": "Invalid position"}), 400

    updates = {"WATERMARK_POSITION": position}
    if position == "custom":
        updates["LOGO_WIDTH"] = str(data.get("logo_width", 300))
        updates["LOGO_HEIGHT"] = str(data.get("logo_height", 52))
        updates["LOGO_X"] = str(data.get("logo_x", 70))
        updates["LOGO_Y"] = str(data.get("logo_y", 450))

    try:
        update_dotenv(updates)
        return jsonify({"success": True, "message": "Logo settings saved"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/settings/download-featured")
def download_featured():
    import shutil
    import os
    from image_processor import add_watermark
    
    # Use absolute path relative to this file
    basedir = os.path.dirname(os.path.abspath(__file__))
    source_img = os.path.join(basedir, 'static', 'logos', '1.jpg')
    
    if not os.path.exists(source_img):
        logger.error(f"Source image not found at: {source_img}")
        # Return 404 with a clear message - if errorhandler catches it, it will show JSON
        # but at least the log will have the path
        return jsonify({"success": False, "message": f"Source image 1.jpg not found at {source_img}"}), 404
        
    temp_dir = os.path.join(basedir, 'static', 'uploads')
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, 'download_featured_temp.jpg')
    
    try:
        # Copy to temp path so we don't watermark the original 1.jpg
        shutil.copy2(source_img, temp_path)
        
        # Apply watermark using current config
        add_watermark(temp_path, position=Config.WATERMARK_POSITION)
        
        return send_file(temp_path, as_attachment=True, download_name="featured_image.jpg")
    except Exception as e:
        logger.error(f"Download featured error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/schedule")
def schedule_page():
    scheduled_articles = Article.query.filter(
        Article.status == "SCHEDULED"
    ).order_by(Article.scheduled_time.asc()).all()
    stats = get_stats()
    return render_template(
        "schedule.html", articles=scheduled_articles, stats=stats
    )


@app.route("/gmail/fetch", methods=["POST"])
def fetch_gmail_news():
    try:
        service = get_gmail_service()
        if not service:
            return jsonify({"success": False, "message": "Gmail service connection failed. Try deleting token.json and re-authenticating via the Gmail setup."}), 500
            
        messages = fetch_emails(service)
        if not messages:
            return jsonify({"success": True, "message": "No unread emails found in inbox. Make sure unread emails are in your Primary inbox tab (not Social/Promotions) and try marking them unread again.", "articles": []})
            
        articles_saved = []
        
        for msg in messages:
            try:
                details = get_message_details(service, msg['id'])
                if not details:
                    continue
                    
                # Create a new article record
                title_text = details['subject'] or "(No Subject)"
                article = Article(
                    title=title_text,
                    tags=[title_text],
                    categories=["এক্সক্লুসিভ", "জাতীয়", "খবর"],
                    content=details['body'] or "",
                    source_url=f"gmail://{msg['id']}",
                    status="NEW",
                )
                db.session.add(article)
                db.session.flush() # Get the ID
                
                # Download and process attachments
                processed_images = []
                for i, att in enumerate(details['attachments']):
                    if att.get('mimeType', '').startswith('image/'):
                        temp_filename = f"att_{msg['id']}_{i}"
                        # Try to guess extension
                        if 'filename' in att and '.' in att['filename']:
                            temp_filename += os.path.splitext(att['filename'])[1]
                        else:
                            temp_filename += ".jpg"
                            
                        temp_path = os.path.join("temp", temp_filename)
                        os.makedirs("temp", exist_ok=True)
                        
                        downloaded = download_attachment(service, msg['id'], att['attachmentId'], temp_path)
                        if downloaded:
                            try:
                                web_path = process_image(downloaded, article.id, i)
                                if web_path:
                                    processed_images.append(web_path)
                            except Exception as img_e:
                                logger.error(f"Image processing error for attachment {att['attachmentId']}: {img_e}")
                            finally:
                                if os.path.exists(downloaded):
                                    os.remove(downloaded)
                
                article.images = processed_images
                if processed_images:
                    article.featured_image = processed_images[0]
                    
                db.session.commit()
                articles_saved.append(article.to_dict())
                
                # Mark as read
                try:
                    service.users().messages().batchModify(
                        userId='me',
                        body={'ids': [msg['id']], 'removeLabelIds': ['UNREAD']}
                    ).execute()
                except Exception as mod_e:
                    logger.warning(f"Could not mark message {msg['id']} as read: {mod_e}")
                    
            except Exception as msg_e:
                logger.error(f"Error processing Gmail message {msg['id']}: {msg_e}")
                db.session.rollback()
                continue

        return jsonify({
            "success": True, 
            "message": f"Fetched {len(articles_saved)} news items from Gmail",
            "articles": articles_saved
        })
    except Exception as e:
        logger.error(f"Critical Gmail fetch error: {e}")
        return jsonify({"success": False, "message": f"Gmail fetch error: {str(e)}"}), 500


@app.route("/articles/<int:article_id>/set-featured-image", methods=["POST"])
def set_featured_image(article_id):
    article = Article.query.get_or_404(article_id)
    data = request.get_json()
    image_url = data.get("image_url")
    if not image_url:
        return jsonify({"success": False, "message": "Image URL required"}), 400
    
    article.featured_image = image_url
    db.session.commit()
    return jsonify({"success": True, "message": "Featured image updated"})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


def main():
    from scheduler import init_scheduler, scheduler
    init_scheduler(app)

    try:
        app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
