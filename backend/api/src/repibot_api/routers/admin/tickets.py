"""Обращения: очередь, переписка, ответ и закрытие.

Единственный предмет админки, открытый роли support: поддержка отвечает людям,
а не правит тарифы и не рассылает письма. Гейт стоит на каждом маршруте
отдельно — скрытая кнопка в интерфейсе защитой не является.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, client_ip, db_session, require_role
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.schemas import (
    AdminTicketResponse,
    AdminTicketThreadResponse,
    TicketMessageResponse,
    TicketReplyRequest,
)
from repibot_core.db.models import Ticket, TicketMessage, TicketStatus, UserRole
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.services.errors import ServiceError
from repibot_core.services.support import SupportService
from repibot_core.tasks import wake_outbox

# Без префикса: он стоит на общем роутере пакета.
router = APIRouter()


@router.get("/tickets", response_model=list[AdminTicketResponse])
async def list_tickets(
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
    ticket_status: Annotated[TicketStatus | None, Query(alias="status")] = None,
) -> list[AdminTicketResponse]:
    """Очередь персонала: свежие сверху, отбор по тому, чьего хода ждём."""
    query = select(Ticket).order_by(Ticket.id.desc())
    if ticket_status is not None:
        query = query.where(Ticket.status == ticket_status)
    return [_admin_ticket_response(item) for item in (await session.scalars(query)).all()]


@router.get("/tickets/{ticket_id}", response_model=AdminTicketThreadResponse)
async def read_ticket_thread(
    ticket_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
) -> AdminTicketThreadResponse:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise ApiError("обращение не найдено", 404, "not_found")
    messages = await SupportService(session).thread(ticket_id)
    return AdminTicketThreadResponse(
        ticket=_admin_ticket_response(ticket),
        messages=[_ticket_message_response(message) for message in messages],
    )


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=TicketMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def reply_to_ticket(
    ticket_id: int,
    payload: TicketReplyRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> TicketMessageResponse:
    """Ответ персонала из админки. Копия уходит и в топик супергруппы."""
    try:
        message = await SupportService(session).reply_from_admin(
            ticket_id, payload.body, author_user_id=context.principal.user_id
        )
    except ServiceError as error:
        raise api_error_from_service(error) from error

    await AuditRepository(session).record(
        "ticket.reply",
        "ticket",
        actor_id=context.principal.user_id,
        entity_id=str(ticket_id),
        after={"message_id": message.id},
        ip=ip,
    )
    await session.commit()
    # После коммита: до него ответа в очереди ещё нет, и разбуженный воркер
    # ушёл бы ни с чем. Без пробуждения ответ персонала ждал бы крона до
    # минуты — ровно в тот момент, когда человек читает переписку.
    await wake_outbox()
    return _ticket_message_response(message)


@router.post("/tickets/{ticket_id}/close", status_code=status.HTTP_204_NO_CONTENT)
async def close_ticket(
    ticket_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> None:
    """Закрывает обращение и его топик. Повтор безобиден."""
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise ApiError("обращение не найдено", 404, "not_found")
    if ticket.status is TicketStatus.closed:
        # Повтор ничего не меняет и записи в журнале не заслуживает: она
        # означала бы ещё одно действие персонала, которого не было.
        return

    try:
        await SupportService(session).close(ticket_id, by_staff=True, notify=True)
    except ServiceError as error:
        raise api_error_from_service(error) from error

    await AuditRepository(session).record(
        "ticket.close",
        "ticket",
        actor_id=context.principal.user_id,
        entity_id=str(ticket_id),
        after={"status": TicketStatus.closed.value},
        ip=ip,
    )
    await session.commit()
    await wake_outbox()


def _admin_ticket_response(ticket: Ticket) -> AdminTicketResponse:
    return AdminTicketResponse(
        id=ticket.id,
        status=ticket.status.value,
        subject=ticket.subject,
        created_at=ticket.created_at,
        last_staff_message_at=ticket.last_staff_message_at,
        user_id=ticket.user_id,
        telegram_topic_id=ticket.telegram_topic_id,
        last_user_message_at=ticket.last_user_message_at,
    )


def _ticket_message_response(message: TicketMessage) -> TicketMessageResponse:
    return TicketMessageResponse(
        id=message.id,
        author=message.author_kind.value,
        body=message.body,
        created_at=message.created_at,
    )
