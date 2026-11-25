import httpx

from app.config import settings


class KeitaroError(Exception):
    """Ошибка при обращении к Keitaro Admin API."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class KeitaroClient:
    """Клиент для общения с Keitaro через HTTP API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 15.0,
    ):
        """
        Создаёт HTTP-клиент для подключения к Keitaro.

        Если адрес или API-ключ не переданы, берёт их из настроек приложения.
        timeout — максимальное время ожидания ответа в секундах.
        """
        root = (base_url or settings.keitaro_url).rstrip("/")

        # Создаём HTTP-клиент с общим адресом API и ключом авторизации.
        self._client = httpx.Client(
            base_url=f"{root}/admin_api/v1",
            headers={"Api-Key": api_key or settings.keitaro_api_key},
            timeout=timeout,
        )

    def _request(self, method: str, path: str, **kwargs):
        """
        Отправляет HTTP-запрос в Keitaro.

        method — HTTP-метод (GET, POST и т. д.).
        path — путь API, например /campaigns.
        kwargs — дополнительные параметры запроса.

        Если Keitaro возвращает ошибку, вызывает KeitaroError.
        При успешном ответе возвращает данные в формате Python.
        """
        resp = self._client.request(method, path, **kwargs)

        # Проверяем, не вернул ли сервер ошибку.
        if resp.status_code >= 400:
            raise KeitaroError(
                f"{method} {path} -> {resp.status_code}: {resp.text[:300]}",
                status_code=resp.status_code,
            )

        # Преобразуем JSON-ответ сервера в Python-объект.
        return resp.json()

    def list_campaigns(self) -> list[dict]:
        """
        Получает список всех доступных рекламных кампаний Keitaro.
        Возвращает список словарей с данными кампаний.
        """
        return self._request("GET", "/campaigns")

    def get(self, path: str, **params):
        """
        Получает данные из Keitaro методом GET.

        path — путь API, например /domains или /offers.
        params — дополнительные параметры URL-запроса.
        """
        return self._request("GET", path, params=params or None)

    def post(self, path: str, json: dict | None = None):
        """
        Отправляет данные в Keitaro методом POST.

        path — путь API, например /campaigns.
        json — словарь с данными, которые нужно передать серверу.
        """
        return self._request("POST", path, json=json)

    def put(self, path: str, json: dict | None = None):
        return self._request("PUT", path, json=json)

    def delete(self, path: str):
        """Отправляет DELETE-запрос в Keitaro для удаления объекта."""
        return self._request("DELETE", path)

    def close(self) -> None:
        """Закрывает HTTP-клиент и освобождает сетевые ресурсы."""
        self._client.close()
