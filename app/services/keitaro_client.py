import httpx

from app.config import settings


class KeitaroError(Exception):
    """Ошибка при обращении к Keitaro Admin API."""


class KeitaroClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 15.0):
        root = (base_url or settings.keitaro_url).rstrip("/")
        self._client = httpx.Client(
            base_url=f"{root}/admin_api/v1",
            headers={"Api-Key": api_key or settings.keitaro_api_key},
            timeout=timeout,
        )

    def _request(self, method: str, path: str, **kwargs):
        resp = self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise KeitaroError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def list_campaigns(self) -> list[dict]:
        return self._request("GET", "/campaigns")

    def close(self) -> None:
        self._client.close()