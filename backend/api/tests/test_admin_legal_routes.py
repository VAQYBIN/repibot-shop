"""Юридические документы через админское API."""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.docker

DRAFT = {"title": "Пользовательское соглашение", "content": "## Общие\n\nтекст"}


async def test_support_cannot_touch_legal_documents(
    api_client: AsyncClient, support_headers: dict[str, str]
) -> None:
    """Поддержка не правит условия продажи — то же правило, что с тарифами."""
    whoami = await api_client.get("/api/admin/whoami", headers=support_headers)
    assert whoami.json()["role"] == "support"

    response = await api_client.get("/api/admin/legal", headers=support_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_draft_becomes_published_document(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    saved = await api_client.put("/api/admin/legal/terms/ru", json=DRAFT, headers=admin_headers)
    assert saved.status_code == 200
    assert saved.json()["published_at"] is None

    # До публикации документа для публики не существует.
    assert (await api_client.get("/api/legal/terms")).status_code == 404

    published = await api_client.post("/api/admin/legal/terms/ru/publish", headers=admin_headers)
    assert published.status_code == 200
    assert published.json()["version"] == 1

    public = await api_client.get("/api/legal/terms")
    assert public.status_code == 200
    assert "<h2>Общие</h2>" in public.json()["html"]


async def test_editing_creates_a_second_version(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await api_client.put("/api/admin/legal/terms/ru", json=DRAFT, headers=admin_headers)
    await api_client.post("/api/admin/legal/terms/ru/publish", headers=admin_headers)

    await api_client.put(
        "/api/admin/legal/terms/ru",
        json={"title": "Пользовательское соглашение", "content": "новая редакция"},
        headers=admin_headers,
    )
    await api_client.post("/api/admin/legal/terms/ru/publish", headers=admin_headers)

    versions = await api_client.get("/api/admin/legal/terms/ru/versions", headers=admin_headers)
    assert [item["version"] for item in versions.json()] == [2, 1]

    first = await api_client.get("/api/admin/legal/terms/ru/versions/1", headers=admin_headers)
    assert first.json()["content"] == "## Общие\n\nтекст"


async def test_withdrawn_document_disappears_from_the_public_api(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await api_client.put("/api/admin/legal/offer/ru", json=DRAFT, headers=admin_headers)
    await api_client.post("/api/admin/legal/offer/ru/publish", headers=admin_headers)

    removed = await api_client.delete("/api/admin/legal/offer/ru", headers=admin_headers)
    assert removed.status_code == 204

    assert (await api_client.get("/api/legal/offer")).status_code == 404
    # История при этом цела: снятие не стирает текст.
    versions = await api_client.get("/api/admin/legal/offer/ru/versions", headers=admin_headers)
    assert len(versions.json()) == 1


async def test_bad_slug_is_rejected(api_client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await api_client.put("/api/admin/legal/Терms!/ru", json=DRAFT, headers=admin_headers)

    assert response.status_code in {400, 422}


async def test_import_returns_text_without_saving(
    api_client: AsyncClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Импорт кладёт текст в ответ, а не в базу: сохраняет админ, посмотрев его."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "title": "Политика конфиденциальности",
                    "content": [{"tag": "p", "children": ["Текст политики."]}],
                },
            },
        )

    # Подменяется фабрика клиента в роутере — тем же приёмом, что fake_panel
    # подменяет panel_client: разбор ответа и сборка запроса при этом
    # проверяются настоящие, а в сеть тест не выходит.
    from repibot_api.routers.admin import legal

    monkeypatch.setattr(
        legal,
        "telegraph_http_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = await api_client.post(
        "/api/admin/legal/import",
        json={"url": "https://telegra.ph/Politika-konfidencialnosti-06-01-36"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Политика конфиденциальности"
    assert response.json()["content"] == "Текст политики.\n"
    assert (await api_client.get("/api/admin/legal", headers=admin_headers)).json() == []


async def test_import_rejects_foreign_addresses(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/admin/legal/import",
        json={"url": "http://api:8000/api/admin/plans"},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_source"
