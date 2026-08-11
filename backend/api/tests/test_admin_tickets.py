"""Админские маршруты обращений: обе роли, ответ персонала и закрытие."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import (
    AuditLog,
    NotificationDelivery,
    OutboxMessage,
    Ticket,
    TicketStatus,
)
from repibot_core.services.support import TOPIC_SUPPORT_OUTBOUND, SupportService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker

SUPPORT_CHAT_ID = "-1001234567890"


@pytest.fixture
def support_enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Супергруппа в окружении: без неё поддержка выключена целиком.

    Настройки закэшированы, поэтому кэш сбрасывается и на входе, и на выходе:
    без второго сброса соседний набор унаследовал бы чужую супергруппу.
    """
    monkeypatch.setenv("SUPPORT_CHAT_ID", SUPPORT_CHAT_ID)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _open_ticket(engine: AsyncEngine, user_id: int, body: str) -> int:
    """Обращение заводится сервисом, а не вставкой строки.

    Клиентский маршрут поддержки сюда не тянется намеренно: его падение не
    должно превращаться в падение админских маршрутов.
    """
    async with create_session_factory(engine)() as session:
        ticket = await SupportService(session).open(user_id, body)
        await session.commit()
        return ticket.id


async def test_support_role_sees_tickets_but_not_plans(
    api_client: AsyncClient, support_headers: dict[str, str]
) -> None:
    """Роль поддержки не должна дотягиваться до тарифов и денег."""
    tickets = await api_client.get("/api/admin/tickets", headers=support_headers)
    plans = await api_client.post("/api/admin/plans", headers=support_headers, json={"code": "x"})

    assert tickets.status_code == 200
    assert plans.status_code == 403


async def test_admin_role_also_works_with_tickets(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Админ старше поддержки: закрывать её от обращений незачем."""
    response = await api_client.get("/api/admin/tickets", headers=admin_headers)

    assert response.status_code == 200


async def test_ticket_list_carries_the_person_and_filters_by_status(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    plain_user_id: int,
    engine: AsyncEngine,
    support_enabled: None,
) -> None:
    """Очередь персонала — это «что ждёт ответа»: без фильтра её не разобрать."""
    first = await _open_ticket(engine, plain_user_id, "не открывается")
    second = await _open_ticket(engine, plain_user_id, "не приходит письмо")
    await api_client.post(f"/api/admin/tickets/{first}/close", headers=support_headers)

    everything = await api_client.get("/api/admin/tickets", headers=support_headers)
    waiting = await api_client.get(
        "/api/admin/tickets", params={"status": "waiting_staff"}, headers=support_headers
    )

    assert [item["id"] for item in everything.json()] == [second, first]
    assert everything.json()[0]["user_id"] == plain_user_id
    assert [item["id"] for item in waiting.json()] == [second]


async def test_reply_from_admin_reaches_the_person_and_the_supergroup(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    plain_user_id: int,
    engine: AsyncEngine,
    support_enabled: None,
) -> None:
    """Ответ из админки обязан дойти и до человека, и до топика.

    Без топика коллега в супергруппе не увидит, что обращение уже разобрано, и
    ответит второй раз.
    """
    ticket_id = await _open_ticket(engine, plain_user_id, "не открывается")

    response = await api_client.post(
        f"/api/admin/tickets/{ticket_id}/messages",
        json={"body": "Проверьте профиль"},
        headers=support_headers,
    )
    thread = await api_client.get(f"/api/admin/tickets/{ticket_id}", headers=support_headers)

    assert response.status_code == 201
    assert response.json()["author"] == "staff"
    assert response.json()["body"] == "Проверьте профиль"
    assert thread.json()["ticket"]["status"] == "waiting_user"
    assert [item["body"] for item in thread.json()["messages"]] == [
        "не открывается",
        "Проверьте профиль",
    ]
    async with create_session_factory(engine)() as session:
        kinds = list((await session.scalars(select(NotificationDelivery.kind))).all())
        queued = list(
            (
                await session.scalars(
                    select(OutboxMessage)
                    .where(OutboxMessage.topic == TOPIC_SUPPORT_OUTBOUND)
                    .order_by(OutboxMessage.id)
                )
            ).all()
        )
        audit = await session.scalar(select(AuditLog).where(AuditLog.action == "ticket.reply"))
    assert kinds == ["ticket_reply"]
    assert len(queued) == 2
    assert "Проверьте профиль" in str(queued[1].payload["body"])
    assert audit is not None
    assert audit.entity_id == str(ticket_id)


async def test_closed_ticket_refuses_further_replies(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    plain_user_id: int,
    engine: AsyncEngine,
    support_enabled: None,
) -> None:
    """Топик закрытого обращения в супергруппе уже закрыт: ответ туда не дойдёт."""
    ticket_id = await _open_ticket(engine, plain_user_id, "не открывается")

    closed = await api_client.post(f"/api/admin/tickets/{ticket_id}/close", headers=support_headers)
    repeated = await api_client.post(
        f"/api/admin/tickets/{ticket_id}/close", headers=support_headers
    )
    refused = await api_client.post(
        f"/api/admin/tickets/{ticket_id}/messages",
        json={"body": "и ещё"},
        headers=support_headers,
    )

    assert closed.status_code == 204
    assert repeated.status_code == 204
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "ticket_closed")
    async with create_session_factory(engine)() as session:
        ticket = await session.get(Ticket, ticket_id)
        actions = list(
            (
                await session.scalars(
                    select(AuditLog.action).where(AuditLog.entity == "ticket").order_by(AuditLog.id)
                )
            ).all()
        )
    assert ticket is not None and ticket.status is TicketStatus.closed
    # Повторное закрытие не оставляет второй записи: в журнале она означала бы
    # ещё одно действие персонала, которого не было.
    assert actions == ["ticket.close"]


async def test_missing_ticket_is_a_404(
    api_client: AsyncClient, support_headers: dict[str, str]
) -> None:
    """Номер из чужой вкладки не должен приводить к 500."""
    thread = await api_client.get("/api/admin/tickets/999999", headers=support_headers)
    reply = await api_client.post(
        "/api/admin/tickets/999999/messages", json={"body": "?"}, headers=support_headers
    )

    assert thread.status_code == 404
    assert reply.status_code == 404
