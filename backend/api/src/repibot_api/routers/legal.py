"""Юридические документы для всех.

Читается без входа: человек имеет право посмотреть условия до того, как
заведёт аккаунт. Черновики сюда не попадают никогда.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import db_session
from repibot_api.errors import ApiError
from repibot_api.schemas import LegalDocumentResponse, LegalListItemResponse
from repibot_core.content.markdown import render_markdown
from repibot_core.services.legal import LegalService

router = APIRouter()

# Локаль приходит параметром, а не заголовком: страница на сервере и запрос из
# браузера должны получать одно и то же, а Accept-Language у них разный.
LocaleQuery = Annotated[str, Query(pattern="^(ru|en)$")]


@router.get("/api/legal", response_model=list[LegalListItemResponse])
async def list_legal_documents(
    session: Annotated[AsyncSession, Depends(db_session)],
    locale: LocaleQuery = "ru",
) -> list[LegalListItemResponse]:
    documents = await LegalService(session).published_list(locale)
    return [
        LegalListItemResponse(
            slug=document.slug,
            title=document.title,
            # published_at у опубликованного документа заполнен по построению:
            # published_list отбирает только такие.
            published_at=document.published_at,
        )
        for document in documents
        if document.published_at is not None
    ]


@router.get("/api/legal/{slug}", response_model=LegalDocumentResponse)
async def read_legal_document(
    slug: str,
    session: Annotated[AsyncSession, Depends(db_session)],
    locale: LocaleQuery = "ru",
) -> LegalDocumentResponse:
    document = await LegalService(session).published(slug, locale)
    if document is None or document.published_at is None:
        raise ApiError("документ не найден", 404, "not_found")

    return LegalDocumentResponse(
        slug=document.slug,
        title=document.title,
        html=render_markdown(document.content),
        locale=document.locale,
        version=document.version,
        published_at=document.published_at,
    )
