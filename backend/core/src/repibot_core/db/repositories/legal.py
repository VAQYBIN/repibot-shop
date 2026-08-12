"""Доступ к юридическим документам."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import LegalDocument


class LegalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def draft(self, slug: str, locale: str) -> LegalDocument | None:
        statement = select(LegalDocument).where(
            LegalDocument.slug == slug,
            LegalDocument.locale == locale,
            LegalDocument.published_at.is_(None),
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def latest(self, slug: str, locale: str) -> LegalDocument | None:
        """Последняя версия пары, включая черновик."""
        statement = (
            select(LegalDocument)
            .where(LegalDocument.slug == slug, LegalDocument.locale == locale)
            .order_by(LegalDocument.version.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def latest_published(self, slug: str, locale: str) -> LegalDocument | None:
        statement = (
            select(LegalDocument)
            .where(
                LegalDocument.slug == slug,
                LegalDocument.locale == locale,
                LegalDocument.published_at.is_not(None),
            )
            .order_by(LegalDocument.version.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def locales_with_publication(self, slug: str) -> list[str]:
        statement = (
            select(LegalDocument.locale)
            .where(LegalDocument.slug == slug, LegalDocument.published_at.is_not(None))
            .distinct()
        )
        return list((await self._session.execute(statement)).scalars())

    async def all_slugs(self) -> list[tuple[str, str]]:
        statement = select(LegalDocument.slug, LegalDocument.locale).distinct()
        return [(slug, locale) for slug, locale in (await self._session.execute(statement)).all()]

    async def versions(self, slug: str, locale: str) -> list[LegalDocument]:
        statement = (
            select(LegalDocument)
            .where(LegalDocument.slug == slug, LegalDocument.locale == locale)
            .order_by(LegalDocument.version.desc())
        )
        return list((await self._session.execute(statement)).scalars())

    async def version(self, slug: str, locale: str, version: int) -> LegalDocument | None:
        statement = select(LegalDocument).where(
            LegalDocument.slug == slug,
            LegalDocument.locale == locale,
            LegalDocument.version == version,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    def add(self, document: LegalDocument) -> None:
        self._session.add(document)
