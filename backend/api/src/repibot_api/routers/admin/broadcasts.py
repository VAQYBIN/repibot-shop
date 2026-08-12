"""Рассылки: черновик, запуск, отмена и охват сегмента.

Счёт сегмента переезжает сюда вместе с кампаниями, а не остаётся отдельным
предметом: его смотрят ровно перед запуском и ровно затем, чтобы не отправить
письмо не тем. Роль support сюда не допускается — письмо всей базе пишет
владелец.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, client_ip, db_session, require_role
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.schemas import BroadcastResponse, CreateBroadcastRequest, SegmentCountResponse
from repibot_core.db.models import Broadcast, UserRole
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.services.broadcasts import BroadcastService
from repibot_core.services.errors import ServiceError
from repibot_core.services.segments import count_segment

# Без префикса: он стоит на общем роутере пакета.
router = APIRouter()


@router.get("/broadcasts", response_model=list[BroadcastResponse])
async def list_broadcasts(
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> list[BroadcastResponse]:
    """Свежие сверху: администратор ищет ту кампанию, что запустил только что."""
    return [_broadcast_response(item) for item in await BroadcastService(session).list_campaigns()]


@router.post("/broadcasts", response_model=BroadcastResponse, status_code=status.HTTP_201_CREATED)
async def create_broadcast(
    payload: CreateBroadcastRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> BroadcastResponse:
    """Черновик кампании. Отправка начинается отдельным действием."""
    try:
        campaign = await BroadcastService(session).create(
            created_by=context.principal.user_id,
            segment=payload.segment,
            title=payload.title,
            body=payload.body,
        )
    except ServiceError as error:
        raise api_error_from_service(error) from error

    await _record_broadcast(session, "broadcast.create", campaign, context=context, ip=ip)
    await session.commit()
    return _broadcast_response(campaign)


@router.get("/broadcasts/{broadcast_id}", response_model=BroadcastResponse)
async def read_broadcast(
    broadcast_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> BroadcastResponse:
    return _broadcast_response(await _require_broadcast(session, broadcast_id))


@router.post("/broadcasts/{broadcast_id}/start", response_model=BroadcastResponse)
async def start_broadcast(
    broadcast_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> BroadcastResponse:
    """Фиксирует аудиторию и переводит кампанию в работу."""
    try:
        # Сервис открывает транзакцию сам: аудиторию нельзя зафиксировать
        # наполовину. Открытая зависимостью транзакция уронила бы его begin().
        if session.in_transaction():
            await session.commit()
        await BroadcastService(session).start(broadcast_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error

    campaign = await _require_broadcast(session, broadcast_id)
    await _record_broadcast(session, "broadcast.start", campaign, context=context, ip=ip)
    await session.commit()
    return _broadcast_response(campaign)


@router.post("/broadcasts/{broadcast_id}/cancel", response_model=BroadcastResponse)
async def cancel_broadcast(
    broadcast_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> BroadcastResponse:
    """Останавливает идущую кампанию. Уже отправленное не отзывается."""
    try:
        if session.in_transaction():
            await session.commit()
        await BroadcastService(session).cancel(broadcast_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error

    campaign = await _require_broadcast(session, broadcast_id)
    await _record_broadcast(session, "broadcast.cancel", campaign, context=context, ip=ip)
    await session.commit()
    return _broadcast_response(campaign)


@router.get("/segments/{segment}/count", response_model=SegmentCountResponse)
async def count_segment_reach(
    segment: str,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> SegmentCountResponse:
    """Охват до запуска — единственная защита от «отправил не тем»."""
    try:
        return SegmentCountResponse(count=await count_segment(session, segment))
    except KeyError as error:
        # segment_query отвергает неизвестное имя KeyError, а не ServiceError:
        # непойманный, он превратил бы опечатку в имени сегмента в 500.
        raise ApiError(f"неизвестный сегмент: {segment}", 422, "unknown_segment") from error


async def _require_broadcast(session: AsyncSession, broadcast_id: int) -> Broadcast:
    campaign = await session.get(Broadcast, broadcast_id)
    if campaign is None:
        raise ApiError("рассылка не найдена", 404, "not_found")
    return campaign


async def _record_broadcast(
    session: AsyncSession,
    action: str,
    campaign: Broadcast,
    *,
    context: AuthContext,
    ip: str | None,
) -> None:
    """След в журнале: письмо всей базе обязано иметь названного автора."""
    await AuditRepository(session).record(
        action,
        "broadcast",
        actor_id=context.principal.user_id,
        entity_id=str(campaign.id),
        after=_broadcast_snapshot(campaign),
        ip=ip,
    )


def _broadcast_snapshot(campaign: Broadcast) -> dict[str, object]:
    return {
        "segment": campaign.segment,
        "status": campaign.status.value,
        "planned_count": campaign.planned_count,
        "sent_count": campaign.sent_count,
        "failed_count": campaign.failed_count,
    }


def _broadcast_response(campaign: Broadcast) -> BroadcastResponse:
    return BroadcastResponse(
        id=campaign.id,
        segment=campaign.segment,
        title=campaign.title,
        body=campaign.body,
        status=campaign.status.value,
        planned_count=campaign.planned_count,
        sent_count=campaign.sent_count,
        failed_count=campaign.failed_count,
        started_at=campaign.started_at,
        finished_at=campaign.finished_at,
    )
