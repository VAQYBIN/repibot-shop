"""Публичное чтение юридических документов."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from repibot_core.services.legal import LegalService

pytestmark = pytest.mark.docker


async def _publish(engine: AsyncEngine, slug: str, locale: str, content: str) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        service = LegalService(session)
        await service.save_draft(
            slug=slug, locale=locale, title="Условия", content=content, author_id=None
        )
        await service.publish(slug=slug, locale=locale)
        await session.commit()


async def test_empty_list_when_nothing_is_published(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/legal")

    assert response.status_code == 200
    assert response.json() == []


async def test_published_document_is_readable(api_client: AsyncClient, engine: AsyncEngine) -> None:
    await _publish(engine, "terms", "ru", "## Раздел\n\nтекст")

    listed = await api_client.get("/api/legal")
    assert [item["slug"] for item in listed.json()] == ["terms"]

    document = await api_client.get("/api/legal/terms")
    assert document.status_code == 200
    body = document.json()
    assert body["title"] == "Условия"
    assert "<h2>Раздел</h2>" in body["html"]
    assert body["locale"] == "ru"


async def test_draft_is_invisible(api_client: AsyncClient, engine: AsyncEngine) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await LegalService(session).save_draft(
            slug="privacy", locale="ru", title="Политика", content="черновик", author_id=None
        )
        await session.commit()

    assert (await api_client.get("/api/legal/privacy")).status_code == 404
    assert (await api_client.get("/api/legal")).json() == []


async def test_unknown_document_is_not_found(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/legal/nothing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
