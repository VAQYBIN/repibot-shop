"""Фоновые задачи, которые ставит не только воркер.

Расписание раз в минуту — страховка на случай, если процесс, поставивший
задачу, умер между коммитом и постановкой. Обычный путь короче: сервис ставит
задачу сразу после коммита, и письмо уходит за секунды.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.integrations.remnawave.client import RemnawaveClient
from repibot_core.queue import broker
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.settings import get_settings

if TYPE_CHECKING:
    # Только ради аннотации: настоящий импорт сервиса на уровне модуля
    # замкнул бы цикл services → tasks → services.
    from repibot_core.services.subscriptions import SubscriptionService


@broker.task(schedule=[{"cron": "* * * * *"}])
async def process_outbox() -> dict[str, int]:
    engine = create_engine(get_settings().database_url)
    # Клиент панели закрывается наравне с движком: задача идёт раз в минуту, и
    # брошенный httpx.AsyncClient — это утечка сокетов, растущая весь день.
    panel = _panel_client()
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            delivered = await _dispatcher(factory, panel).process(session)
    finally:
        await panel.aclose()
        await engine.dispose()

    return {"delivered": delivered}


@broker.task(schedule=[{"cron": "0 * * * *"}])
async def expire_subscriptions() -> dict[str, int]:
    """Переводит просроченные подписки в expired и снимает доступ в панели.

    Раз в час, а не раз в сутки: каждый лишний час доступа после окончания
    оплаченного срока — это доступ, за который никто не заплатил. Дата
    окончания при этом не двигается: expired — следствие даты, а не решение.
    """
    engine = create_engine(get_settings().database_url)
    # Клиент панели нужен сервису подписки при сборке и закрывается наравне с
    # движком: задача идёт каждый час, и брошенный httpx.AsyncClient — это
    # утечка сокетов, растущая всё время работы воркера.
    panel = _panel_client()
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            expired = await _subscriptions(session, panel).expire_due(now=datetime.now(UTC))
    finally:
        await panel.aclose()
        await engine.dispose()

    return {"expired": expired}


@broker.task(schedule=[{"cron": f"17 */{get_settings().reconcile_interval_hours} * * *"}])
async def reconcile_panel() -> dict[str, int]:
    """Периодически приводит панель к нашему состоянию и записывает отличия."""
    engine = create_engine(get_settings().database_url)
    panel = _panel_client()
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            from repibot_core.integrations.remnawave.users import PanelUsers
            from repibot_core.services.provisioning import ProvisioningService
            from repibot_core.services.reconciliation import ReconciliationService

            written = await ReconciliationService(
                session, ProvisioningService(session, PanelUsers(panel))
            ).run(run_id=str(uuid4()))
    finally:
        await panel.aclose()
        await engine.dispose()

    return {"written": written}


def _panel_client() -> RemnawaveClient:
    """Импорт внутри функции по той же причине, что и у диспетчера ниже."""
    from repibot_core.integrations.remnawave.client import create_remnawave_client

    return create_remnawave_client()


def _dispatcher(
    factory: async_sessionmaker[AsyncSession], panel: RemnawaveClient
) -> OutboxDispatcher:
    """Собирается на каждый прогон.

    Импорт внутри функции разрывает цикл: services импортирует эту же задачу,
    чтобы поставить её после коммита.

    Фабрика сессий уходит внутрь: выдача доступа в панели работает в своей
    транзакции, а не в той, которой диспетчер закрывает сообщения очереди.
    """
    from repibot_core.integrations.remnawave.users import PanelUsers
    from repibot_core.services.dispatcher import build_dispatcher

    return build_dispatcher(factory, users=PanelUsers(panel))


def _subscriptions(session: AsyncSession, panel: RemnawaveClient) -> SubscriptionService:
    """Сервис подписок на сессию задачи.

    Импорты внутри функции по той же причине, что и у диспетчера: services
    зовёт задачи этого модуля после коммита, и цикл services → tasks →
    services иначе не разрывается.

    Примирение сервису передаётся, хотя истечение само в панель не ходит:
    доступ снимает разбор outbox отдельной транзакцией, а сервис собирается
    ровно одним способом на всех вызывающих.
    """
    from repibot_core.integrations.remnawave.users import PanelUsers
    from repibot_core.services.provisioning import ProvisioningService
    from repibot_core.services.subscriptions import SubscriptionService

    return SubscriptionService(
        session, get_settings(), ProvisioningService(session, PanelUsers(panel))
    )
