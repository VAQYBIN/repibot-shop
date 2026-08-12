"""Ограничения таблицы юридических документов."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import LegalDocument

pytestmark = pytest.mark.docker


async def test_second_draft_for_the_same_pair_is_rejected(db_session: AsyncSession) -> None:
    """Черновик у пары slug+locale ровно один: иначе непонятно, какой открывать."""
    db_session.add(
        LegalDocument(slug="terms", locale="ru", title="Условия", content="текст", version=1)
    )
    await db_session.flush()

    db_session.add(
        LegalDocument(slug="terms", locale="ru", title="Условия", content="другой", version=2)
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_published_versions_may_coexist(db_session: AsyncSession) -> None:
    """История версий — смысл таблицы: опубликованные строки не конфликтуют."""
    now = datetime.now(UTC)
    for version in (1, 2):
        db_session.add(
            LegalDocument(
                slug="terms",
                locale="ru",
                title="Условия",
                content=f"версия {version}",
                version=version,
                published_at=now,
            )
        )
    await db_session.flush()
