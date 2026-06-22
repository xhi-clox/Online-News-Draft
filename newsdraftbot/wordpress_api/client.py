import json
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

from wordpress_api.auth import WordPressAuth, BasicAuth, JWTAuth

logger = logging.getLogger(__name__)

API_TIMEOUT = 60
MAX_RETRIES = 2


class WordPressAPIError(Exception):
    def __init__(self, message: str, status_code: int = None, response_data: dict = None):
        self.status_code = status_code
        self.response_data = response_data or {}
        super().__init__(message)


class WordPressAuthError(WordPressAPIError):
    pass


class WordPressNotFoundError(WordPressAPIError):
    pass


class WordPressRateLimitError(WordPressAPIError):
    pass


class WordPressClient:
    def __init__(self, base_url: str, auth: WordPressAuth):
        self.base_url = base_url.rstrip("/")
        self.api_root = f"{self.base_url}/wp-json/wp/v2"
        self.auth = auth
        self._request_log: list[dict] = []

    @classmethod
    def from_config(cls, config) -> "WordPressClient":
        url = config.WORDPRESS_URL
        username = config.WORDPRESS_USERNAME
        app_password = config.WORDPRESS_APP_PASSWORD

        if not url:
            raise WordPressAPIError("WordPress URL not configured")

        auth = BasicAuth(username, app_password)
        return cls(url, auth)

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        json_data: dict = None,
        files: dict = None,
        headers_extra: dict = None,
    ) -> requests.Response:
        url = f"{self.api_root}/{endpoint.lstrip('/')}"
        headers = {
            "User-Agent": "NewsDraftBot/1.0",
            "Accept": "application/json",
        }
        headers.update(self.auth.get_headers())
        if headers_extra:
            headers.update(headers_extra)

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": method.upper(),
            "url": url,
            "params": params,
        }

        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                    files=files,
                    timeout=API_TIMEOUT,
                )

                log_entry["status_code"] = resp.status_code
                log_entry["response_preview"] = resp.text[:500]
                self._request_log.append(log_entry)

                logger.debug(
                    f"WP API {method.upper()} {url} -> {resp.status_code} "
                    f"(attempt {attempt + 1})"
                )

                if resp.status_code == 401:
                    if attempt < MAX_RETRIES - 1 and self.auth.refresh():
                        headers = self.auth.get_headers()
                        if headers_extra:
                            headers.update(headers_extra)
                        continue
                    raise WordPressAuthError(
                        "Authentication failed. Check your credentials.",
                        status_code=401,
                        response_data=self._safe_json(resp),
                    )

                if resp.status_code == 403:
                    raise WordPressAuthError(
                        "Access denied. You don't have permission.",
                        status_code=403,
                        response_data=self._safe_json(resp),
                    )

                if resp.status_code == 404:
                    raise WordPressNotFoundError(
                        f"Resource not found: {endpoint}",
                        status_code=404,
                    )

                if resp.status_code == 429:
                    raise WordPressRateLimitError(
                        "WordPress API rate limit exceeded. Try again later.",
                        status_code=429,
                    )

                if not resp.ok:
                    error_detail = self._safe_json(resp)
                    wp_message = error_detail.get("message", resp.text[:200])
                    raise WordPressAPIError(
                        f"WordPress API error ({resp.status_code}): {wp_message}",
                        status_code=resp.status_code,
                        response_data=error_detail,
                    )

                return resp

            except (requests.ConnectionError, requests.Timeout) as e:
                logger.warning(f"Request attempt {attempt + 1} failed: {e}")
                if attempt == MAX_RETRIES - 1:
                    raise WordPressAPIError(f"Connection failed after {MAX_RETRIES} attempts: {e}")

    def _safe_json(self, resp: requests.Response) -> dict:
        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError):
            return {}

    def get(self, endpoint: str, params: dict = None) -> list | dict:
        resp = self._request("GET", endpoint, params=params)
        return resp.json()

    def get_all_paginated(self, endpoint: str, params: dict = None) -> list[dict]:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        params.setdefault("page", 1)
        params.setdefault("hide_empty", False)

        all_items = []
        page = 1

        while True:
            params["page"] = page
            try:
                resp = self._request("GET", endpoint, params=params)
                items = resp.json()
                if not items:
                    break
                all_items.extend(items)
                total_pages = int(resp.headers.get("X-WP-TotalPages", 0))
                if page >= total_pages:
                    break
                page += 1
            except WordPressNotFoundError:
                break

        return all_items

    def post(self, endpoint: str, json_data: dict = None, files: dict = None) -> dict:
        headers_extra = {}
        if json_data and not files:
            headers_extra["Content-Type"] = "application/json"
        resp = self._request("POST", endpoint, json_data=json_data, files=files, headers_extra=headers_extra)
        return resp.json()

    def put(self, endpoint: str, json_data: dict = None) -> dict:
        headers_extra = {"Content-Type": "application/json"}
        resp = self._request("PUT", endpoint, json_data=json_data, headers_extra=headers_extra)
        return resp.json()

    def delete(self, endpoint: str) -> dict:
        resp = self._request("DELETE", endpoint)
        return self._safe_json(resp)
