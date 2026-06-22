import logging
import requests
from config import Config

logger = logging.getLogger(__name__)

def share_to_facebook_page(title, link):
    """
    Share an article to a Facebook Page automatically using Graph API.
    Returns dict with success status and message.
    """
    fb_page_id = Config.FB_PAGE_ID.strip() if Config.FB_PAGE_ID else ""
    fb_token = Config.FB_PAGE_ACCESS_TOKEN.strip() if Config.FB_PAGE_ACCESS_TOKEN else ""

    if not fb_page_id or not fb_token:
        logger.warning("Facebook automation skipped: FB_PAGE_ID or FB_PAGE_ACCESS_TOKEN not configured")
        return {"success": False, "message": "Facebook Page ID or Access Token not configured"}

    url = f"https://graph.facebook.com/v18.0/{fb_page_id}/feed"

    payload = {
        "message": title,
        "link": link,
        "access_token": fb_token,
    }

    headers = {
        "User-Agent": "NewsDraftBot/1.0",
    }

    try:
        response = requests.post(url, data=payload, headers=headers, timeout=30)
        result = response.json()

        if response.status_code == 200 and "id" in result:
            logger.info(f"Successfully shared to Facebook Page: {result['id']}")
            return {"success": True, "id": result["id"]}
        else:
            error_msg = result.get("error", {}).get("message", "Unknown error")
            logger.error(f"Facebook share failed: {error_msg}")
            return {"success": False, "message": error_msg}
    except Exception as e:
        logger.error(f"Error during Facebook automated share: {e}")
        return {"success": False, "message": str(e)}
