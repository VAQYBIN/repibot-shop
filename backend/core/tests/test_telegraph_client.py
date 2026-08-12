"""Загрузка страницы Telegra.ph.

Сеть не используется: транспорт httpx подменяется заглушкой, поэтому тест
проверяет наше поведение, а не доступность чужого сервиса.
"""

from __future__ import annotations

import httpx
import pytest

from repibot_core.integrations.telegraph.client import (
    TelegraphClient,
    TelegraphError,
)

PAGE_RESPONSE = {
    "ok": True,
    "result": {
        "title": "Пользовательское соглашение",
        "content": [
            {"tag": "h3", "children": ["Общие положения"]},
            {"tag": "p", "children": ["Текст соглашения."]},
        ],
    },
}


def _client(handler: object) -> TelegraphClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return TelegraphClient(httpx.AsyncClient(transport=transport))


async def test_page_is_fetched_and_converted() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json=PAGE_RESPONSE)

    page = await _client(handler).fetch("https://telegra.ph/Polzovatelskoe-soglashenie-06-01-28")

    assert page.title == "Пользовательское соглашение"
    assert page.content == "## Общие положения\n\nТекст соглашения.\n"
    assert "api.telegra.ph/getPage" in requested[0]
    assert "Polzovatelskoe-soglashenie-06-01-28" in requested[0]
    assert "return_content=true" in requested[0]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/terms",
        "https://telegra.ph.evil.com/page",
        "http://127.0.0.1:8000/api/admin/plans",
        "не адрес вовсе",
    ],
)
async def test_foreign_addresses_are_rejected(url: str) -> None:
    """Эндпоинт, ходящий по произвольному адресу, простукивает внутреннюю сеть снаружи."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover — не вызывается
        raise AssertionError("запрос не должен уходить")

    with pytest.raises(TelegraphError) as error:
        await _client(handler).fetch(url)

    assert error.value.code == "invalid_source"


async def test_missing_page_is_reported_as_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "error": "PAGE_NOT_FOUND"})

    with pytest.raises(TelegraphError) as error:
        await _client(handler).fetch("https://telegra.ph/Nothing-01-01")

    assert error.value.code == "not_found"


async def test_unavailable_service_is_reported_separately() -> None:
    """Их недоступность — не наша ошибка ввода: админ должен видеть разницу."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("нет связи")

    with pytest.raises(TelegraphError) as error:
        await _client(handler).fetch("https://telegra.ph/Something-01-01")

    assert error.value.code == "import_failed"
