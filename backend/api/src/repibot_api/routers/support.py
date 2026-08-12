"""Обращения в поддержку: список, переписка и ответы со стороны человека.

Маршруты живут отдельно от админских: там разговор ведёт персонал и разрешён
любой тикет, здесь — только свой. Общий роутер рано или поздно потерял бы эту
разницу в одном необязательном параметре.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, current_context, db_session, get_redis
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.schemas import (
    OpenTicketRequest,
    TicketMessageResponse,
    TicketReplyRequest,
    TicketResponse,
    TicketThreadResponse,
)
from repibot_core.db.models import Ticket, TicketMessage
from repibot_core.ratelimit import TICKET_MESSAGE_PER_USER, RateLimiter
from repibot_core.services.errors import ServiceError
from repibot_core.services.support import SupportService
from repibot_core.tasks import wake_outbox

router = APIRouter(prefix="/api/support", tags=["support"])


def _ticket(ticket: Ticket) -> TicketResponse:
    return TicketResponse(
        id=ticket.id,
        status=ticket.status.value,
        subject=ticket.subject,
        created_at=ticket.created_at,
        last_staff_message_at=ticket.last_staff_message_at,
    )


def _message(message: TicketMessage) -> TicketMessageResponse:
    return TicketMessageResponse(
        id=message.id,
        author=message.author_kind.value,
        body=message.body,
        created_at=message.created_at,
    )


async def _guard_rate(redis: Redis, user_id: int) -> None:
    """Пауза между сообщениями одного человека.

    Ключ общий для нового обращения и ответа: скрипту всё равно, чем набивать
    супергруппу — топиками или репликами в них.
    """
    result = await RateLimiter(redis).hit(f"ticket:{user_id}", TICKET_MESSAGE_PER_USER)
    if not result.allowed:
        raise ApiError(
            "слишком часто",
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            {"Retry-After": str(result.retry_after_seconds)},
        )


async def _own_ticket(session: AsyncSession, ticket_id: int, user_id: int) -> Ticket:
    """Обращение, которое принадлежит спрашивающему.

    Проверка владельца стоит здесь, а не в сервисе: чтение переписки и закрытие
    обращения его не спрашивают, и без этой строки перебором номеров читалась бы
    чужая переписка. Чужой номер отвечает тем же 404, что и несуществующий:
    иначе разница ответов сама сообщает, что обращение с таким номером есть.
    """
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.user_id != user_id:
        raise ApiError("обращение не найдено", status.HTTP_404_NOT_FOUND, "not_found")
    return ticket


@router.get("/tickets", response_model=list[TicketResponse])
async def list_tickets(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> list[TicketResponse]:
    """Список читается и при выключенной поддержке.

    Супергруппу могли убрать уже после разговора, а переписка — это ещё и
    доказательство того, что было обещано.
    """
    tickets = await SupportService(session).list_for_user(context.principal.user_id)
    return [_ticket(ticket) for ticket in tickets]


@router.post("/tickets", status_code=status.HTTP_201_CREATED, response_model=TicketResponse)
async def open_ticket(
    payload: OpenTicketRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TicketResponse:
    await _guard_rate(redis, context.principal.user_id)
    try:
        ticket = await SupportService(session).open(context.principal.user_id, payload.body)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    # Сервис не коммитит: обращение, сообщение и запись в очереди обязаны
    # попасть в базу одной транзакцией, иначе топик создаётся под обращение,
    # которого нет.
    await session.commit()
    # После коммита, а не до: раньше воркер не нашёл бы ни обращения, ни
    # сообщения в очереди. Иначе тема супергруппы ждала бы крона до минуты,
    # а человек всё это время смотрел бы на молчащую поддержку.
    await wake_outbox()
    return _ticket(ticket)


@router.get("/tickets/{ticket_id}", response_model=TicketThreadResponse)
async def read_ticket(
    ticket_id: int,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> TicketThreadResponse:
    ticket = await _own_ticket(session, ticket_id, context.principal.user_id)
    messages = await SupportService(session).thread(ticket_id)
    return TicketThreadResponse(
        ticket=_ticket(ticket), messages=[_message(message) for message in messages]
    )


@router.post(
    "/tickets/{ticket_id}/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=TicketMessageResponse,
)
async def reply(
    ticket_id: int,
    payload: TicketReplyRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TicketMessageResponse:
    """Владельца здесь проверяет сам сервис — тем же 404 на чужой номер."""
    await _guard_rate(redis, context.principal.user_id)
    try:
        message = await SupportService(session).reply_from_user(
            context.principal.user_id, ticket_id, payload.body
        )
    except ServiceError as error:
        raise api_error_from_service(error) from error
    await session.commit()
    await wake_outbox()
    return _message(message)


@router.post("/tickets/{ticket_id}/close", response_model=TicketResponse)
async def close_ticket(
    ticket_id: int,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> TicketResponse:
    """Закрытие частотой не ограничено: повтор ничего не создаёт и не шлёт.

    Обращение возвращается целиком, чтобы экран показал закрытое состояние без
    второго запроса.
    """
    ticket = await _own_ticket(session, ticket_id, context.principal.user_id)
    try:
        await SupportService(session).close(ticket_id, by_staff=False, notify=False)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    await session.commit()
    await wake_outbox()
    return _ticket(ticket)
