"""Версии документа: правка, публикация, снятие, запасная локаль."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.services.errors import ServiceError
from repibot_core.services.legal import LegalService

pytestmark = pytest.mark.docker


async def test_editing_a_published_document_creates_a_new_version(
    db_session: AsyncSession,
) -> None:
    service = LegalService(db_session)
    await service.save_draft(
        slug="terms", locale="ru", title="Условия", content="первый", author_id=None
    )
    await service.publish(slug="terms", locale="ru")

    await service.save_draft(
        slug="terms", locale="ru", title="Условия", content="второй", author_id=None
    )
    published = await service.publish(slug="terms", locale="ru")

    assert published.version == 2
    assert [item.version for item in await service.versions("terms", "ru")] == [2, 1]


async def test_draft_is_not_published(db_session: AsyncSession) -> None:
    service = LegalService(db_session)
    await service.save_draft(
        slug="privacy", locale="ru", title="Политика", content="черновик", author_id=None
    )

    assert await service.published("privacy", "ru") is None


async def test_withdrawn_document_disappears_from_the_public_list(
    db_session: AsyncSession,
) -> None:
    service = LegalService(db_session)
    await service.save_draft(
        slug="offer", locale="ru", title="Оферта", content="текст", author_id=None
    )
    await service.publish(slug="offer", locale="ru")

    await service.withdraw(slug="offer", locale="ru")

    assert await service.published("offer", "ru") is None
    assert await service.published_list("ru") == []


async def test_publishing_again_returns_a_withdrawn_document(db_session: AsyncSession) -> None:
    """Отдельной кнопки «вернуть» нет: возврат — обычная новая версия."""
    service = LegalService(db_session)
    await service.save_draft(
        slug="offer", locale="ru", title="Оферта", content="текст", author_id=None
    )
    await service.publish(slug="offer", locale="ru")
    await service.withdraw(slug="offer", locale="ru")

    await service.save_draft(
        slug="offer", locale="ru", title="Оферта", content="текст", author_id=None
    )
    restored = await service.publish(slug="offer", locale="ru")

    assert restored.version == 2
    assert (await service.published("offer", "ru")) is not None


async def test_missing_locale_falls_back(db_session: AsyncSession) -> None:
    """Подвал на английском не должен приводить в пустоту, если заведён только русский."""
    service = LegalService(db_session)
    await service.save_draft(
        slug="terms", locale="ru", title="Условия", content="текст", author_id=None
    )
    await service.publish(slug="terms", locale="ru")

    document = await service.published("terms", "en")

    assert document is not None
    assert document.locale == "ru"


async def test_invalid_slug_is_rejected(db_session: AsyncSession) -> None:
    """Косая черта в slug превратила бы имя документа в часть пути."""
    service = LegalService(db_session)

    with pytest.raises(ServiceError):
        await service.save_draft(
            slug="terms/../etc", locale="ru", title="Условия", content="текст", author_id=None
        )


async def test_publishing_without_a_draft_fails(db_session: AsyncSession) -> None:
    service = LegalService(db_session)

    with pytest.raises(ServiceError):
        await service.publish(slug="terms", locale="ru")
