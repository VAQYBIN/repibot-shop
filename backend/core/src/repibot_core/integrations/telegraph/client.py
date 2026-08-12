"""Разовая загрузка страницы Telegra.ph.

Адрес принимается только с их домена. Это не придирчивость: эндпоинт,
который по просьбе пользователя ходит на произвольный URL, позволяет
простукивать внутреннюю сеть снаружи — включая наши же служебные адреса.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from repibot_core.integrations.telegraph.nodes import nodes_to_markdown

API_URL = "https://api.telegra.ph/getPage"
ALLOWED_HOSTS = frozenset({"telegra.ph", "api.telegra.ph"})
TIMEOUT_SECONDS = 5.0


class TelegraphError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class TelegraphPage:
    title: str
    content: str


class TelegraphClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)

    async def fetch(self, url: str) -> TelegraphPage:
        path = _path_of(url)

        try:
            response = await self._client.get(
                API_URL, params={"path": path, "return_content": "true"}
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            msg = "Telegra.ph не ответил"
            raise TelegraphError("import_failed", msg) from error

        if not payload.get("ok"):
            msg = "страница не найдена"
            raise TelegraphError("not_found", msg)

        result = payload.get("result", {})
        content = result.get("content")
        return TelegraphPage(
            title=str(result.get("title", "")),
            content=nodes_to_markdown(content if isinstance(content, list) else []),
        )


def _path_of(url: str) -> str:
    """Путь страницы в адресе Telegra.ph.

    Хост сравнивается целиком, а не поиском подстроки: `telegra.ph.evil.com`
    содержит нужные символы и не имеет к сервису никакого отношения.
    """
    try:
        parsed = urlparse(url)
    except ValueError as error:
        msg = "это не адрес"
        raise TelegraphError("invalid_source", msg) from error

    if parsed.scheme not in {"http", "https"} or parsed.hostname not in ALLOWED_HOSTS:
        msg = "принимаются только ссылки на telegra.ph"
        raise TelegraphError("invalid_source", msg)

    path = parsed.path.strip("/")
    if not path:
        msg = "в ссылке нет страницы"
        raise TelegraphError("invalid_source", msg)
    return path
