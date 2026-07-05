import os
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON

db = SQLAlchemy()


class Article(db.Model):
    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    slug = db.Column(db.String(500), nullable=True)
    source_url = db.Column(db.String(1000), unique=True, nullable=False)
    content = db.Column(db.Text, nullable=True)
    excerpt = db.Column(db.Text, nullable=True)
    tags = db.Column(JSON, nullable=True)
    categories = db.Column(JSON, nullable=True)
    featured_image = db.Column(db.String(1000), nullable=True)
    reporter = db.Column(db.String(200), nullable=True)
    wordpress_post_id = db.Column(db.Integer, nullable=True)
    wordpress_featured_media_id = db.Column(db.Integer, nullable=True)
    wordpress_url = db.Column(db.String(1000), nullable=True)
    wordpress_author_id = db.Column(db.Integer, nullable=True)
    wordpress_category_ids = db.Column(JSON, nullable=True)
    wordpress_tag_ids = db.Column(JSON, nullable=True)
    share_count = db.Column(db.Integer, default=0)
    images = db.Column(JSON, nullable=True)  # Store list of image URLs/paths
    status = db.Column(
        db.String(20),
        nullable=False,
        default="NEW",
        index=True,
    )
    scheduled_time = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "slug": self.slug,
            "source_url": self.source_url,
            "content": self.content,
            "excerpt": self.excerpt,
            "tags": self.tags or [],
            "categories": self.categories or [],
            "featured_image": self.featured_image,
            "reporter": self.reporter,
            "wordpress_post_id": self.wordpress_post_id,
            "wordpress_featured_media_id": self.wordpress_featured_media_id,
            "wordpress_url": self.wordpress_url,
            "wordpress_author_id": self.wordpress_author_id,
            "wordpress_category_ids": self.wordpress_category_ids or [],
            "wordpress_tag_ids": self.wordpress_tag_ids or [],
            "share_count": self.share_count,
            "images": self.images or [],
            "status": self.status,
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Article {self.id}: {self.title[:50]}>"


def init_db(app):
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "database"), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp"), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads"), exist_ok=True)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _migrate()


def _migrate():
    import sqlalchemy as sa
    inspector = sa.inspect(db.engine)
    articles_cols = [c["name"] for c in inspector.get_columns("articles")]
    if "reporter" not in articles_cols:
        db.session.execute(sa.text("ALTER TABLE articles ADD COLUMN reporter VARCHAR(200)"))
        db.session.commit()
    if "wordpress_url" not in articles_cols:
        db.session.execute(sa.text("ALTER TABLE articles ADD COLUMN wordpress_url VARCHAR(1000)"))
        db.session.commit()
    if "wordpress_featured_media_id" not in articles_cols:
        db.session.execute(sa.text("ALTER TABLE articles ADD COLUMN wordpress_featured_media_id INTEGER"))
        db.session.commit()
    if "share_count" not in articles_cols:
        db.session.execute(sa.text("ALTER TABLE articles ADD COLUMN share_count INTEGER DEFAULT 0"))
        db.session.commit()
    if "images" not in articles_cols:
        db.session.execute(sa.text("ALTER TABLE articles ADD COLUMN images JSON"))
        db.session.commit()
    if "wordpress_author_id" not in articles_cols:
        db.session.execute(sa.text("ALTER TABLE articles ADD COLUMN wordpress_author_id INTEGER"))
        db.session.commit()
    if "wordpress_category_ids" not in articles_cols:
        db.session.execute(sa.text("ALTER TABLE articles ADD COLUMN wordpress_category_ids JSON"))
        db.session.commit()
    if "wordpress_tag_ids" not in articles_cols:
        db.session.execute(sa.text("ALTER TABLE articles ADD COLUMN wordpress_tag_ids JSON"))
        db.session.commit()
    if not inspector.has_table("reporters"):
        Reporter.__table__.create(db.engine)
    if not inspector.has_table("saved_prompts"):
        SavedPrompt.__table__.create(db.engine)
    if not inspector.has_table("ai_usage"):
        AIUsage.__table__.create(db.engine)


class CategoryMapping(db.Model):
    __tablename__ = "category_mappings"

    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(100), nullable=False, unique=True)
    category = db.Column(db.String(100), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "keyword": self.keyword,
            "category": self.category,
        }


class Reporter(db.Model):
    __tablename__ = "reporters"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class SavedPrompt(db.Model):
    __tablename__ = "saved_prompts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    prompt_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "prompt_text": self.prompt_text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AIUsage(db.Model):
    __tablename__ = "ai_usage"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    count = db.Column(db.Integer, default=0)
    limit = db.Column(db.Integer, default=1500)

    def to_dict(self):
        return {
            "date": self.date.isoformat() if self.date else None,
            "count": self.count,
            "limit": self.limit,
            "remaining": self.limit - self.count,
        }
