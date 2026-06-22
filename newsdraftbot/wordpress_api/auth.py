import base64
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class WordPressAuth(ABC):
    @abstractmethod
    def get_headers(self) -> dict:
        ...

    @abstractmethod
    def refresh(self) -> bool:
        ...


class BasicAuth(WordPressAuth):
    def __init__(self, username: str, app_password: str):
        self.username = username
        self.app_password = app_password

    def get_headers(self) -> dict:
        credentials = f"{self.username}:{self.app_password}"
        token = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {token}"}

    def refresh(self) -> bool:
        return False


class JWTAuth(WordPressAuth):
    def __init__(self, base_url: str, username: str, password: str, token: str = None):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._token = token
        self._token_endpoint = f"{self.base_url}/wp-json/jwt-auth/v1/token"

    def get_headers(self) -> dict:
        if not self._token:
            self._authenticate()
        return {"Authorization": f"Bearer {self._token}"}

    def refresh(self) -> bool:
        try:
            self._authenticate()
            return True
        except Exception as e:
            logger.error(f"JWT refresh failed: {e}")
            return False

    def _authenticate(self):
        import requests
        resp = requests.post(
            self._token_endpoint,
            json={"username": self.username, "password": self.password},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            self._token = data.get("token")
            logger.info("JWT token obtained successfully")
        else:
            raise PermissionError(
                f"JWT authentication failed: {resp.status_code} {resp.text[:200]}"
            )
