"""Профиль и сессии текущего пользователя."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import (
    AuthContext,
    current_context,
    db_session,
    get_principals,
    get_redis,
)
from repibot_api.errors import ApiError, api_error_from
from repibot_api.schemas import (
    AcceptedResponse,
    ChangeEmailRequest,
    LinkCodeResponse,
    MeResponse,
    SessionResponse,
    SetPasswordRequest,
    UpdateMeRequest,
)
from repibot_core.domain.identity import LINK_CODE_TTL
from repibot_core.integrations.telegram.bot_api import TIMEOUT_SECONDS as BOT_TIMEOUT_SECONDS
from repibot_core.integrations.telegram.bot_api import BotApi
from repibot_core.ratelimit import LETTER_PER_EMAIL, LINK_CODE_PER_USER, RateLimiter
from repibot_core.services.auth.password import PasswordAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError
from repibot_core.services.principal import PrincipalCache
from repibot_core.services.profile import ProfileService, ProfileView
from repibot_core.services.telegram_link import TelegramLinkService
from repibot_core.settings import get_settings

router = APIRouter(prefix="/api/me", tags=["me"])


def _profile(session: AsyncSession, principals: PrincipalCache) -> ProfileService:
    settings = get_settings()
    auth = AuthService(session, settings, principals)
    return ProfileService(
        session, settings, auth, principals, PasswordAuth(session, settings, auth)
    )


def _to_response(view: ProfileView) -> MeResponse:
    return MeResponse(
        id=view.user_id,
        email=view.email,
        email_verified=view.email_verified,
        telegram_username=view.telegram_username,
        name=view.name,
        language=view.language,  # type: ignore[arg-type]
        role=view.role.value,
        referral_code=view.referral_code,
        has_password=view.has_password,
        has_telegram=view.has_telegram,
        passkey_count=view.passkey_count,
    )


@router.get("", response_model=MeResponse)
async def read_me(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> MeResponse:
    try:
        return _to_response(await _profile(session, principals).view(context.principal.user_id))
    except AuthError as error:
        raise api_error_from(error) from error


@router.patch("", response_model=MeResponse)
async def update_me(
    payload: UpdateMeRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> MeResponse:
    try:
        view = await _profile(session, principals).update(
            context.principal.user_id, name=payload.name, language=payload.language
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return _to_response(view)


@router.post("/password", status_code=204)
async def set_password(
    payload: SetPasswordRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> None:
    try:
        await _profile(session, principals).set_password(
            context.principal.user_id,
            current=payload.current_password,
            new=payload.new_password,
        )
    except AuthError as error:
        raise api_error_from(error) from error


@router.post("/email/change-request", status_code=202, response_model=AcceptedResponse)
async def request_email_change(
    payload: ChangeEmailRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AcceptedResponse:
    result = await RateLimiter(redis).hit(f"letter:email:{payload.email}", LETTER_PER_EMAIL)
    if not result.allowed:
        raise ApiError(
            "слишком часто",
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            {"Retry-After": str(result.retry_after_seconds)},
        )

    try:
        await _profile(session, principals).request_email_change(
            context.principal.user_id, payload.email
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return AcceptedResponse(status="confirmation_sent")


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> list[SessionResponse]:
    items = await _profile(session, principals).list_sessions(
        context.principal.user_id, context.session_id
    )
    return [
        SessionResponse(
            id=item.session_id,
            user_agent=item.user_agent,
            ip=item.ip,
            created_at=item.created_at,
            is_current=item.is_current,
        )
        for item in items
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: UUID,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> None:
    auth = AuthService(session, get_settings(), principals)
    try:
        await auth.revoke_session(context.principal.user_id, session_id)
    except AuthError as error:
        raise api_error_from(error) from error


@router.delete("/sessions", status_code=204)
async def revoke_other_sessions(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> None:
    auth = AuthService(session, get_settings(), principals)
    await auth.revoke_other_sessions(context.principal.user_id, context.session_id)


def bot_http_client() -> httpx.AsyncClient:
    """Точка подмены в тестах: обращения к api.telegram.org там нет."""
    return httpx.AsyncClient(timeout=BOT_TIMEOUT_SECONDS)


def _links(session: AsyncSession, redis: Redis, client: httpx.AsyncClient) -> TelegramLinkService:
    settings = get_settings()
    return TelegramLinkService(session, settings, redis, BotApi(settings, redis, client=client))


@router.post("/telegram/link-code", response_model=LinkCodeResponse)
async def issue_link_code(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> LinkCodeResponse:
    result = await RateLimiter(redis).hit(
        f"link:user:{context.principal.user_id}", LINK_CODE_PER_USER
    )
    if not result.allowed:
        raise ApiError(
            "слишком часто",
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            {"Retry-After": str(result.retry_after_seconds)},
        )

    try:
        # Клиент закрывается сразу: соединение к Bot API нужно один раз в сутки,
        # пока имя бота не выпало из кэша.
        async with bot_http_client() as client:
            offer = await _links(session, redis, client).issue_code(context.principal.user_id)
    except AuthError as error:
        raise api_error_from(error) from error
    return LinkCodeResponse(
        code=offer.code, url=offer.url, expires_in=int(LINK_CODE_TTL.total_seconds())
    )


@router.delete("/telegram", status_code=204)
async def unlink_telegram(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    try:
        # Отвязка обходится без Bot API, но сервис один: клиент отдаётся ему
        # незадействованным и закрывается тут же.
        async with bot_http_client() as client:
            await _links(session, redis, client).unlink(context.principal.user_id)
    except AuthError as error:
        raise api_error_from(error) from error
