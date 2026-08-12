"""Юридические документы: черновик, публикация, история версий.

Опубликованная строка не меняется по содержимому. Правка создаёт новую
версию, и потому на вопрос «какой текст действовал в марте» есть ровно один
ответ — ради него версии в таблице и заведены.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import LegalDocument
from repibot_core.db.repositories.legal import LegalRepository
from repibot_core.services.errors import ServiceError

SLUG_PATTERN = re.compile(r"^[a-z0-9-]{2,64}$")

# Порядок перебора запасных локалей. Русская первая: развёртывание в первую
# очередь русскоязычное, а пустая правовая ссылка хуже ссылки на другом языке.
FALLBACK_ORDER = ("ru", "en")


@dataclass(frozen=True, slots=True)
class LegalDocumentView:
    slug: str
    locale: str
    title: str
    content: str
    version: int
    published_at: datetime | None
    withdrawn_at: datetime | None


@dataclass(frozen=True, slots=True)
class LegalVersionView:
    version: int
    published_at: datetime | None
    withdrawn_at: datetime | None
    created_at: datetime
    created_by_id: int | None


class LegalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._documents = LegalRepository(session)

    async def published_list(self, locale: str) -> list[LegalDocumentView]:
        """По одному документу на slug: нужной локали или запасной."""
        seen = {slug for slug, _ in await self._documents.all_slugs()}
        found = [await self.published(slug, locale) for slug in sorted(seen)]
        return [document for document in found if document is not None]

    async def published(self, slug: str, locale: str) -> LegalDocumentView | None:
        for candidate in (locale, *FALLBACK_ORDER):
            document = await self._documents.latest_published(slug, candidate)
            if document is not None and document.withdrawn_at is None:
                return _view(document)
        return None

    async def current(self, slug: str, locale: str) -> LegalDocumentView | None:
        document = await self._documents.latest(slug, locale)
        return None if document is None else _view(document)

    async def save_draft(
        self, *, slug: str, locale: str, title: str, content: str, author_id: int | None
    ) -> LegalDocumentView:
        _check_slug(slug)
        _check_locale(locale)

        draft = await self._documents.draft(slug, locale)
        if draft is not None:
            draft.title = title
            draft.content = content
            await self._session.flush()
            return _view(draft)

        latest = await self._documents.latest(slug, locale)
        document = LegalDocument(
            slug=slug,
            locale=locale,
            title=title,
            content=content,
            version=1 if latest is None else latest.version + 1,
            created_by_id=author_id,
        )
        self._documents.add(document)
        await self._session.flush()
        return _view(document)

    async def publish(self, *, slug: str, locale: str) -> LegalDocumentView:
        draft = await self._documents.draft(slug, locale)
        if draft is None:
            msg = "публиковать нечего: черновика нет"
            raise ServiceError(msg, "draft_not_found")

        draft.published_at = datetime.now(UTC)
        await self._session.flush()
        return _view(draft)

    async def withdraw(self, *, slug: str, locale: str) -> None:
        """Снимает с публикации, не трогая текст.

        Отметка ставится на последнюю опубликованную версию: публичное чтение
        смотрит именно на неё, а история при этом остаётся целой.
        """
        document = await self._documents.latest_published(slug, locale)
        if document is None:
            msg = "снимать нечего: документ не опубликован"
            raise ServiceError(msg, "not_found")

        document.withdrawn_at = datetime.now(UTC)
        await self._session.flush()

    async def versions(self, slug: str, locale: str) -> list[LegalVersionView]:
        return [
            LegalVersionView(
                version=document.version,
                published_at=document.published_at,
                withdrawn_at=document.withdrawn_at,
                created_at=document.created_at,
                created_by_id=document.created_by_id,
            )
            for document in await self._documents.versions(slug, locale)
        ]

    async def version(self, slug: str, locale: str, version: int) -> LegalDocumentView | None:
        document = await self._documents.version(slug, locale, version)
        return None if document is None else _view(document)

    async def known_slugs(self) -> list[tuple[str, str]]:
        return sorted(await self._documents.all_slugs())


def _check_slug(slug: str) -> None:
    if SLUG_PATTERN.match(slug) is None:
        msg = "имя документа состоит из строчных букв, цифр и дефиса"
        raise ServiceError(msg, "validation_error")


def _check_locale(locale: str) -> None:
    if locale not in FALLBACK_ORDER:
        msg = "поддерживаются только локали ru и en"
        raise ServiceError(msg, "validation_error")


def _view(document: LegalDocument) -> LegalDocumentView:
    return LegalDocumentView(
        slug=document.slug,
        locale=document.locale,
        title=document.title,
        content=document.content,
        version=document.version,
        published_at=document.published_at,
        withdrawn_at=document.withdrawn_at,
    )
