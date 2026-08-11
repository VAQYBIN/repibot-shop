"""Получение подарочных дней лесенки возврата по одноразовому токену."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, current_context, db_session
from repibot_api.errors import api_error_from_service
from repibot_api.schemas import WinbackClaimRequest, WinbackClaimResponse
from repibot_core.services.errors import ServiceError
from repibot_core.services.winback import WinbackService

router = APIRouter(prefix="/api/winback", tags=["winback"])


@router.post("/claim", response_model=WinbackClaimResponse)
async def claim(
    payload: WinbackClaimRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> WinbackClaimResponse:
    """Требует входа намеренно: дни начисляются на аккаунт, и он должен быть свой.

    Токен доказывает право на подарок, но не личность: ссылка из письма могла
    попасть куда угодно вместе с самим письмом.
    """
    try:
        days = await WinbackService(session).claim_days(payload.token, context.principal.user_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    await session.commit()
    return WinbackClaimResponse(days=days)
