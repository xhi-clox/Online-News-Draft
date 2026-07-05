import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    WORDPRESS_URL = os.getenv("WORDPRESS_URL", "").rstrip("/")
    WORDPRESS_USERNAME = os.getenv("WORDPRESS_USERNAME", "")
    WORDPRESS_APP_PASSWORD = os.getenv("WORDPRESS_APP_PASSWORD", "")
    NEWS_SOURCE_URL = os.getenv("NEWS_SOURCE_URL", "")
    CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
    LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "logos", "logo.png")
    SECRET_KEY = os.getenv("SECRET_KEY", "newsdraftbot-secret-key-change-in-production")
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "news.db")
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    } if DATABASE_URL else {}
    MAX_IMAGE_WIDTH = 1920
    WATERMARK_POSITION = os.getenv("WATERMARK_POSITION", "bottom_right")
    LOGO_WIDTH = int(os.getenv("LOGO_WIDTH", "300"))
    LOGO_HEIGHT = int(os.getenv("LOGO_HEIGHT", "52"))
    LOGO_X = int(os.getenv("LOGO_X", "70"))
    LOGO_Y = int(os.getenv("LOGO_Y", "450"))
    WORDPRESS_API_URL = f"{WORDPRESS_URL}/wp-json/wp/v2" if WORDPRESS_URL else ""

    # Facebook Automation
    FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")
    FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
    AUTO_SHARE_TO_FACEBOOK = os.getenv("AUTO_SHARE_TO_FACEBOOK", "false").lower() == "true"
    REPORTER_NAME = os.getenv("REPORTER_NAME", "")
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    AI_BASE_URL = os.getenv("AI_BASE_URL", "https://opencode.ai/zen/v1")
    AI_MODEL = os.getenv("AI_MODEL", "deepseek-v4-flash-free")
