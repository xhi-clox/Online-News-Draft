import logging
import os
from pathlib import Path

import requests
from PIL import Image

from config import Config

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

WATERMARK_POSITIONS = {
    "top_left": (0.05, 0.05),
    "top_right": (0.75, 0.05),
    "bottom_left": (0.05, 0.75),
    "bottom_right": (0.75, 0.75),
    "center": (0.35, 0.40),
}


def download_image(url, output_path):
    logger.info(f"Downloading image: {url}")
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=30, stream=True)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"Image saved to: {output_path}")
        return output_path
    except requests.RequestException as e:
        logger.error(f"Failed to download image {url}: {e}")
        return None


def resize_image(image_path, max_width=800):
    try:
        img = Image.open(image_path)
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
            img.save(image_path, quality=100, optimize=True)
            logger.info(f"Image resized to {max_width}x{new_height}")
        return img
    except Exception as e:
        logger.error(f"Failed to resize image {image_path}: {e}")
        return None


def add_watermark(image_path, logo_path=None, position=None):
    if logo_path is None:
        logo_path = Config.LOGO_PATH

    if not os.path.exists(logo_path):
        logger.warning(f"Logo not found at {logo_path}, skipping watermark")
        return image_path

    try:
        img = Image.open(image_path).convert("RGBA")
        logo = Image.open(logo_path).convert("RGBA")

        bbox = logo.getbbox()
        if bbox:
            logo = logo.crop(bbox)

        if position == "custom":
            target_width = Config.LOGO_WIDTH
            target_height = Config.LOGO_HEIGHT
            x = Config.LOGO_X
            y = Config.LOGO_Y
        elif position == "bottom_left":
            target_width = int(img.width * 0.45)
            ratio = target_width / logo.width
            target_height = int(logo.height * ratio)
            x = int(img.width * 0.05)
            y = img.height - target_height - int(img.height * 0.08)
        else:
            target_width = int(img.width * 0.18)
            ratio = target_width / logo.width
            target_height = int(logo.height * ratio)
            margin = 10
            
            if position == "top_left":
                x = margin
                y = margin
            elif position == "top_right":
                x = img.width - target_width - margin
                y = margin
            elif position == "bottom_right":
                x = img.width - target_width - margin
                y = img.height - target_height - margin
            elif position == "center":
                x = (img.width - target_width) // 2
                y = (img.height - target_height) // 2
            else:
                x = margin
                y = img.height - target_height - margin

        logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)
        img.paste(logo, (x, y), logo)
        img = img.convert("RGB")
        img.save(image_path, quality=100, optimize=True)
        logger.info(f"Watermark applied: logo={logo.width}x{logo.height} at ({x},{y}), img={img.width}x{img.height}")
        return image_path

    except Exception as e:
        logger.error(f"Failed to add watermark: {e}")
        return image_path


def process_image(image_source, article_id, index=0):
    """
    Downloads, resizes, and watermarks an image.
    image_source can be a URL or a local path.
    """
    if not image_source:
        return None

    ext = ".jpg"
    filename = f"article_{article_id}_{index}{ext}"
    output_path = os.path.join("static", "uploads", filename)
    
    # If the image is already a local watermarked file in static/uploads, just return its relative path
    if "static/uploads" in image_source and os.path.exists(image_source):
        # Extract relative path if it's absolute
        if os.path.isabs(image_source):
            try:
                rel = os.path.relpath(image_source, os.getcwd())
                return f"/{rel.replace('\\', '/')}"
            except:
                pass
        return image_source if image_source.startswith('/') else f"/{image_source}"

    local_path = None
    if image_source.startswith(('http://', 'https://')):
        local_path = download_image(image_source, output_path)
    else:
        # It's a local file (e.g. from Gmail or absolute path)
        import shutil
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        try:
            shutil.copy2(image_source, output_path)
            local_path = output_path
        except Exception as e:
            logger.error(f"Failed to copy local image {image_source}: {e}")
            return None

    if local_path:
        # Preserving ratio happens automatically in resize_image and PIL
        resize_image(local_path, max_width=Config.MAX_IMAGE_WIDTH)
        add_watermark(local_path, position=Config.WATERMARK_POSITION)
        # Return the relative web path for frontend and database consistency
        return f"/static/uploads/{filename}"
    return None
