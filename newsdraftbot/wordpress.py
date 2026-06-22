import base64
import logging
import mimetypes
import os

import requests

from config import Config

logger = logging.getLogger(__name__)

API_TIMEOUT = 60


def get_auth_header():
    credentials = f"{Config.WORDPRESS_USERNAME}:{Config.WORDPRESS_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "User-Agent": "NewsDraftBot/1.0",
        "Accept": "application/json",
    }


def api_url(endpoint=""):
    base = Config.WORDPRESS_API_URL
    if not base:
        return ""
    return f"{base}/{endpoint}".rstrip("/")


def upload_image(image_path):
    if not os.path.exists(image_path):
        logger.error(f"Image not found: {image_path}")
        return None

    if not Config.WORDPRESS_URL:
        logger.error("WordPress URL not configured")
        return None

    headers = get_auth_header()
    filename = os.path.basename(image_path)
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/jpeg"

    with open(image_path, "rb") as img_file:
        try:
            resp = requests.post(
                api_url("media"),
                headers=headers,
                files={"file": (filename, img_file, mime_type)},
                timeout=API_TIMEOUT,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                media_id = data.get("id")
                media_url = data.get("source_url")
                logger.info(f"Image uploaded: ID={media_id}, URL={media_url}")
                return {"id": media_id, "url": media_url}
            else:
                logger.error(f"Image upload failed: {resp.status_code} {resp.text[:500]}")
                return None
        except requests.RequestException as e:
            logger.error(f"Image upload error: {e}")
            return None


def get_or_create_term(name, taxonomy="categories"):
    headers = get_auth_header()

    search_resp = requests.get(
        api_url(taxonomy),
        headers=headers,
        params={"search": name},
        timeout=API_TIMEOUT,
    )

    if search_resp.status_code == 200:
        existing = search_resp.json()
        for term in existing:
            if term.get("name", "").lower() == name.lower():
                logger.info(f"Found existing {taxonomy}: {name} (ID={term['id']})")
                return term["id"]

    create_resp = requests.post(
        api_url(taxonomy),
        headers=headers,
        json={"name": name},
        timeout=API_TIMEOUT,
    )

    if create_resp.status_code in (200, 201):
        data = create_resp.json()
        logger.info(f"Created {taxonomy}: {name} (ID={data['id']})")
        return data["id"]
    else:
        logger.warning(f"Failed to create {taxonomy} '{name}': {create_resp.status_code}")
        return None


def _reporter_prefix(reporter, content):
    return content

def create_post(title, content, excerpt, tags, categories, featured_image_id, status="draft", reporter=None):
    headers = get_auth_header()
    headers["Content-Type"] = "application/json"

    category_ids = []
    for cat in categories:
        cat_id = get_or_create_term(cat, "categories")
        if cat_id:
            category_ids.append(cat_id)

    tag_ids = []
    for tag in tags:
        tag_id = get_or_create_term(tag, "tags")
        if tag_id:
            tag_ids.append(tag_id)

    post_data = {
        "title": title,
        "content": _reporter_prefix(reporter, content),
        "excerpt": excerpt,
        "status": status,
        "categories": category_ids,
        "tags": tag_ids,
    }

    if featured_image_id:
        post_data["featured_media"] = int(featured_image_id)

    meta = {}
    if reporter:
        meta["Reporter Name Text"] = reporter
    if meta:
        post_data["meta_input"] = meta

    try:
        resp = requests.post(
            api_url("posts"),
            headers=headers,
            json=post_data,
            timeout=API_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            logger.info(f"Post created: ID={data['id']}, status={data['status']}")
            return data
        else:
            logger.error(f"Post creation failed: {resp.status_code} {resp.text[:500]}")
            return None
    except requests.RequestException as e:
        logger.error(f"Post creation error: {e}")
        return None


def update_post(post_id, title=None, content=None, excerpt=None, tags=None, categories=None, featured_image_id=None, status=None, reporter=None):
    headers = get_auth_header()
    headers["Content-Type"] = "application/json"

    post_data = {}
    if title:
        post_data["title"] = title
    if content:
        post_data["content"] = _reporter_prefix(reporter, content)
    if excerpt:
        post_data["excerpt"] = excerpt
    if status:
        post_data["status"] = status
    if featured_image_id:
        post_data["featured_media"] = int(featured_image_id)

    meta = {}
    if reporter:
        meta["Reporter Name Text"] = reporter
    if meta:
        post_data["meta_input"] = meta

    if tags is not None:
        tag_ids = []
        for tag in tags:
            tag_id = get_or_create_term(tag, "tags")
            if tag_id:
                tag_ids.append(tag_id)
        post_data["tags"] = tag_ids

    if categories is not None:
        category_ids = []
        for cat in categories:
            cat_id = get_or_create_term(cat, "categories")
            if cat_id:
                category_ids.append(cat_id)
        post_data["categories"] = category_ids

    try:
        resp = requests.post(
            api_url(f"posts/{post_id}"),
            headers=headers,
            json=post_data,
            timeout=API_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            logger.info(f"Post updated: ID={data['id']}, status={data['status']}")
            return data
        else:
            logger.error(f"Post update failed: {resp.status_code} {resp.text[:500]}")
            return None
    except requests.RequestException as e:
        logger.error(f"Post update error: {e}")
        return None


def publish_post(post_id):
    return update_post(post_id, status="publish")
