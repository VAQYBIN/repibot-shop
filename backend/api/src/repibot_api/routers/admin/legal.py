"""Юридические документы: правка, публикация, история.

Роль support сюда не допускается по той же причине, что и к тарифам: условия
продажи — не предмет работы поддержки. Публикация и снятие пишутся в журнал
действий: это ровно те события, о которых потом спрашивают.
"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, db_session, require_role
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.schemas import (
    AdminLegalDocumentResponse,
    AdminLegalListItemResponse,
    LegalDraftRequest,
    LegalImportRequest,
    LegalImportResponse,
    LegalVersionResponse,
)
from repibot_core.content.markdown import render_markdown
from repibot_core.db.models import UserRole
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.integrations.telegraph.client import (
    TIMEOUT_SECONDS,
    TelegraphClient,
    TelegraphError,
)
from repibot_core.services.errors import ServiceError
from repibot_core.services.legal import LegalDocumentView, LegalService

router = APIRouter()

# Ограничения на месте параметров пути: имя документа попадает в адрес, и
# проверять его после того, как оно уже стало частью маршрута, поздно.
SlugPath = Annotated[str, Path(pattern="^[a-z0-9-]{2,64}$")]
LocalePath = Annotated[str, Path(pattern="^(ru|en)$")]

AdminOnly = Annotated[AuthContext, Depends(require_role(UserRole.admin))]


def telegraph_http_client() -> httpx.AsyncClient:
    """Соединение на одну загрузку страницы.

    Отдельная фабрика — чтобы тест подменил транспорт так же, как fake_panel
    подменяет клиента панели: маршрут, разбор ответа и перевод ошибок при этом
    проверяются настоящие, а в сеть тест не выходит.
    """
    return httpx.AsyncClient(timeout=TIMEOUT_SECONDS)


@router.get("/legal", response_model=list[AdminLegalListItemResponse])
async def list_legal(
    session: Annotated[AsyncSession, Depends(db_session)],
    _: AdminOnly,
) -> list[AdminLegalListItemResponse]:
    service = LegalService(session)
    items: list[AdminLegalListItemResponse] = []
    for slug, locale in await service.known_slugs():
        versions = await service.versions(slug, locale)
        published = next((item for item in versions if item.published_at is not None), None)
        current = await service.current(slug, locale)
        items.append(
            AdminLegalListItemResponse(
                slug=slug,
                locale=locale,
                title="" if current is None else current.title,
                published_version=None if published is None else published.version,
                published_at=None if published is None else published.published_at,
                withdrawn=published is not None and published.withdrawn_at is not None,
                has_draft=any(item.published_at is None for item in versions),
            )
        )
    return items


@router.get("/legal/{slug}/{locale}", response_model=AdminLegalDocumentResponse)
async def read_legal(
    slug: SlugPath,
    locale: LocalePath,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: AdminOnly,
) -> AdminLegalDocumentResponse:
    document = await LegalService(session).current(slug, locale)
    if document is None:
        raise ApiError("документ не найден", 404, "not_found")
    return _response(document)


@router.get("/legal/{slug}/{locale}/versions", response_model=list[LegalVersionResponse])
async def list_versions(
    slug: SlugPath,
    locale: LocalePath,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: AdminOnly,
) -> list[LegalVersionResponse]:
    return [
        LegalVersionResponse(
            version=item.version,
            published_at=item.published_at,
            withdrawn_at=item.withdrawn_at,
            created_at=item.created_at,
        )
        for item in await LegalService(session).versions(slug, locale)
    ]


@router.get("/legal/{slug}/{locale}/versions/{version}", response_model=AdminLegalDocumentResponse)
async def read_version(
    slug: SlugPath,
    locale: LocalePath,
    version: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: AdminOnly,
) -> AdminLegalDocumentResponse:
    document = await LegalService(session).version(slug, locale, version)
    if document is None:
        raise ApiError("версия не найдена", 404, "not_found")
    return _response(document)


@router.put("/legal/{slug}/{locale}", response_model=AdminLegalDocumentResponse)
async def save_draft(
    slug: SlugPath,
    locale: LocalePath,
    payload: LegalDraftRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: AdminOnly,
) -> AdminLegalDocumentResponse:
    try:
        document = await LegalService(session).save_draft(
            slug=slug,
            locale=locale,
            title=payload.title,
            content=payload.content,
            author_id=context.principal.user_id,
        )
        await session.commit()
    except ServiceError as error:
        raise api_error_from_service(error) from error
    return _response(document)


@router.post("/legal/{slug}/{locale}/publish", response_model=AdminLegalDocumentResponse)
async def publish(
    slug: SlugPath,
    locale: LocalePath,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: AdminOnly,
) -> AdminLegalDocumentResponse:
    try:
        document = await LegalService(session).publish(slug=slug, locale=locale)
        await AuditRepository(session).record(
            "legal.publish",
            "legal_document",
            actor_id=context.principal.user_id,
            entity_id=f"{slug}:{locale}",
            after={"version": document.version},
        )
        await session.commit()
    except ServiceError as error:
        raise api_error_from_service(error) from error
    return _response(document)


@router.delete("/legal/{slug}/{locale}", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw(
    slug: SlugPath,
    locale: LocalePath,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: AdminOnly,
) -> None:
    try:
        await LegalService(session).withdraw(slug=slug, locale=locale)
        await AuditRepository(session).record(
            "legal.withdraw",
            "legal_document",
            actor_id=context.principal.user_id,
            entity_id=f"{slug}:{locale}",
        )
        await session.commit()
    except ServiceError as error:
        raise api_error_from_service(error) from error


@router.post("/legal/import", response_model=LegalImportResponse)
async def import_from_telegraph(
    payload: LegalImportRequest,
    _: AdminOnly,
) -> LegalImportResponse:
    """Забирает текст к себе. Ничего не сохраняет — это делает админ, посмотрев результат."""
    # Соединением владеет обработчик: `TelegraphClient` закрывать за собой не
    # умеет, и созданный им самим клиент пережил бы запрос — на каждую загрузку
    # копился бы ещё один незакрытый пул. Пояснение комментарием, а не строкой
    # документации: она уехала бы в описание маршрута в схеме OpenAPI.
    try:
        async with telegraph_http_client() as http:
            page = await TelegraphClient(http).fetch(payload.url)
    except TelegraphError as error:
        status_code = {"invalid_source": 400, "not_found": 404}.get(error.code, 502)
        raise ApiError(str(error), status_code, error.code) from error
    return LegalImportResponse(title=page.title, content=page.content)


def _response(document: LegalDocumentView) -> AdminLegalDocumentResponse:
    return AdminLegalDocumentResponse(
        slug=document.slug,
        locale=document.locale,
        title=document.title,
        content=document.content,
        html=render_markdown(document.content),
        version=document.version,
        published_at=document.published_at,
    )
