"""Фоновые задачи, которые ставит не только воркер.

Расписание раз в минуту — страховка на случай, если процесс, поставивший
задачу, умер между коммитом и постановкой. Обычный путь короче: сервис ставит
задачу сразу после коммита, и письмо уходит за секунды.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.integrations.remnawave.client import RemnawaveClient
from repibot_core.queue import broker
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.settings import get_settings


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
