"""Отписка от маркетинга по ссылке из письма.

Отдельный файл, а не `me.py`: там каждый маршрут требует авторизации, и
единственное исключение среди них терялось бы. Человек, открывший ссылку из
письма, в аккаунт не входит — иначе отписка требовала бы вспомнить пароль,
а вспомнить его проще кнопкой «спам».
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import db_session
from repibot_api.errors import api_error_from_service
from repibot_api.schemas import UnsubscribeRequest
from repibot_core.services.errors import ServiceError
from repibot_core.services.unsubscribe import UnsubscribeService

router = APIRouter(prefix="/api", tags=["me"])


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    payload: UnsubscribeRequest, session: Annotated[AsyncSession, Depends(db_session)]
) -> None:
    """Операцию авторизует сам токен: он не открывает ничего, кроме отписки."""
    try:
        await UnsubscribeService(session).apply(payload.token)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    await session.commit()
