"""Фоновые задачи, которые ставит не только воркер.

Расписание раз в минуту — страховка на случай, если процесс, поставивший
задачу, умер между коммитом и постановкой. Обычный путь короче: сервис ставит
задачу сразу после коммита, и письмо уходит за секунды.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.db.models import (
    CardBinding,
    CardBindingStatus,
    Order,
    OrderStatus,
    PaymentAttempt,
    PaymentProvider,
    PaymentStatus,
)
from repibot_core.integrations.remnawave.client import RemnawaveClient
from repibot_core.integrations.telegram.bot_api import BotApi
from repibot_core.integrations.telegram.support_chat import SupportChat
from repibot_core.integrations.yookassa.client import create_yookassa_client
from repibot_core.queue import broker
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.settings import get_settings

logger = logging.getLogger(__name__)

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
    # Клиент бота — один на прогон, а не на сообщение: за прогон разбирается
    # вся накопившаяся очередь, и соединение с Valkey с http-клиентом на
    # каждое сообщение означало бы платить ими за каждое уведомление.
    redis = Redis.from_url(get_settings().valkey_url)
    telegram = BotApi(get_settings(), redis)
    # Клиент супергруппы собирается только когда она задана. Без него
    # обработчик темы поддержки отложил бы обращение пять раз и отбросил, а
    # человек остался бы ждать ответа, которого никто не увидел.
    support = SupportChat(get_settings()) if get_settings().support_chat_id is not None else None
    try:
        factory = create_session_factory(engine)
        delivered = await _dispatcher(factory, panel, telegram, support).drain(factory)
    finally:
        if support is not None:
            await support.aclose()
        await telegram.aclose()
        await redis.aclose()
        await panel.aclose()
        await engine.dispose()

    return {"delivered": delivered}


async def wake_outbox() -> None:
    """Просит разобрать очередь немедленно, не дожидаясь крона.

    Отказ проглатывается намеренно: то, ради чего звали, уже записано в базу
    и уйдёт следующим прогоном крона. Уронить здесь запрос человека значило
    бы поменять минуту ожидания на потерянное действие.
    """
    try:
        await process_outbox.kiq()
    except Exception:  # природа отказа брокера роли не играет
        logger.warning("не удалось разбудить разбор очереди", exc_info=True)


@broker.task(schedule=[{"cron": "7 * * * *"}])
async def notify_subscription_events() -> dict[str, int]:
    """Ставит напоминания о конце подписки и о неоплаченном счёте.

    Раз в час и со смещением от нуля минут: в ноль работает истечение
    подписок, и запуск встык дал бы напоминание про состояние, которое
    меняется прямо сейчас.

    Задача только ставит: ни Telegram, ни SMTP отсюда не вызываются, поэтому
    недоступный транспорт не мешает собрать поводы.
    """
    from repibot_core.services.subscription_notices import SubscriptionNoticeService

    engine = create_engine(get_settings().database_url)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            staged = await SubscriptionNoticeService(session).run(now=datetime.now(UTC))
            await session.commit()
    finally:
        await engine.dispose()

    if staged:
        # Разбор очереди идёт раз в минуту, и ждать её человеку незачем:
        # напоминание об окончании доступа тем ценнее, чем раньше пришло.
        # Отказ брокера ничего не отменяет — очередь разберётся по расписанию.
        try:
            await process_outbox.kiq()
        except Exception:
            logger.warning("не удалось разбудить разбор очереди", exc_info=True)
    return {"staged": staged}


@broker.task(schedule=[{"cron": "23 9 * * *"}])
async def run_winback() -> dict[str, int]:
    """Ставит очередную ступень лесенки возврата.

    Раз в сутки и в дневное время: письмо про возвращение, пришедшее ночью, к
    утру уже погребено под остальной почтой.
    """
    from repibot_core.services.winback import WinbackService

    engine = create_engine(get_settings().database_url)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            staged = await WinbackService(session).run(now=datetime.now(UTC))
            await session.commit()
    finally:
        await engine.dispose()

    if staged:
        # Та же причина, что и у напоминаний: разбор очереди идёт раз в минуту,
        # и ждать её незачем. Отказ брокера ничего не отменяет.
        try:
            await process_outbox.kiq()
        except Exception:
            logger.warning("не удалось разбудить разбор очереди", exc_info=True)
    return {"staged": staged}


@broker.task(schedule=[{"cron": "* * * * *"}])
async def run_broadcast() -> dict[str, int]:
    """Отправляет очередную пачку текущей кампании.

    Своя задача, а не общая очередь: рассылка на пять тысяч человек иначе
    держала бы за собой чек об оплате всё время своей работы. Кампания за
    прогон одна — две одновременные поделили бы лимит Telegram пополам.
    """
    from repibot_core.integrations.email.sender import build_sender
    from repibot_core.services.broadcasts import BroadcastService

    engine = create_engine(get_settings().database_url)
    redis = Redis.from_url(get_settings().valkey_url)
    telegram = BotApi(get_settings(), redis)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            sent = await BroadcastService(session).send_batch(
                telegram=telegram, email=build_sender(get_settings())
            )
    finally:
        await telegram.aclose()
        await redis.aclose()
        await engine.dispose()
    return {"sent": sent}


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


@broker.task(schedule=[{"cron": "*/5 * * * *"}])
async def reconcile_pending_payments() -> dict[str, int]:
    """Добирает подтверждённые провайдером оплаты, если update/webhook был потерян."""
    engine = create_engine(get_settings().database_url)
    client = None
    checked = 0
    fulfilled = 0
    cards = 0
    try:
        from repibot_core.services.payment_methods import CardBindingService
        from repibot_core.services.payments import PaymentService

        factory = create_session_factory(engine)
        async with factory() as session:
            stars_attempts = list(
                (
                    await session.scalars(
                        select(PaymentAttempt.id)
                        .join(Order, Order.id == PaymentAttempt.order_id)
                        .where(
                            PaymentAttempt.provider == PaymentProvider.stars,
                            PaymentAttempt.status == PaymentStatus.succeeded,
                            Order.status == OrderStatus.pending,
                        )
                    )
                ).all()
            )
        # Сначала именно локально подтверждённые Stars. Их нельзя пропустить
        # через expiry: Telegram уже списал деньги, а финализатор идемпотентен.
        for attempt_id in stars_attempts:
            async with engine.connect() as claim_connection:
                if not await _try_claim_pending_payment(claim_connection, attempt_id):
                    continue
                checked += 1
                try:
                    async with factory() as session:
                        result = await PaymentService(session).finalize_success(attempt_id)
                finally:
                    await _release_pending_payment_claim(claim_connection, attempt_id)
                if result is not None and not result.already_finalized:
                    fulfilled += 1

        async with factory() as session:
            await PaymentService(session).expire_due_orders(now=datetime.now(UTC))
            attempts = list(
                (
                    await session.execute(
                        select(PaymentAttempt.id, PaymentAttempt.provider_payment_id)
                        .join(Order, Order.id == PaymentAttempt.order_id)
                        .where(
                            PaymentAttempt.provider == PaymentProvider.yookassa,
                            PaymentAttempt.status == PaymentStatus.pending,
                            PaymentAttempt.provider_payment_id.is_not(None),
                            Order.status == OrderStatus.pending,
                            Order.expires_at > datetime.now(UTC),
                        )
                    )
                ).all()
            )
            # Привязка ждёт того же подтверждения, что и оплата, но своего
            # ресурса у провайдера. Наличие проверяется заранее, чтобы клиент
            # не создавался там, где реквизитов нет: без них и привязок нет.
            has_bindings = (
                await session.scalar(
                    select(CardBinding.id)
                    .where(
                        CardBinding.status == CardBindingStatus.pending,
                        CardBinding.provider_binding_id.is_not(None),
                    )
                    .limit(1)
                )
            ) is not None
        if attempts or has_bindings:
            client = create_yookassa_client()
            assert client is not None
        for attempt_id, provider_payment_id in attempts:
            if provider_payment_id is None:  # pragma: no cover
                continue
            if client is None:  # pragma: no cover — client is constructed when attempts are found
                continue
            async with engine.connect() as claim_connection:
                if not await _try_claim_pending_payment(claim_connection, attempt_id):
                    continue
                checked += 1
                try:
                    async with factory() as session:
                        result = await PaymentService(session).verify_yookassa_callback(
                            provider_payment_id, client
                        )
                finally:
                    await _release_pending_payment_claim(claim_connection, attempt_id)
                if result is not None and not result.already_finalized:
                    fulfilled += 1

        if has_bindings and client is not None:
            async with factory() as session:
                cards = await CardBindingService(session).settle_pending(client)
    finally:
        if client is not None:
            await client.aclose()
        await engine.dispose()
    return {"checked": checked, "fulfilled": fulfilled, "cards": cards}


@broker.task(schedule=[{"cron": "*/10 * * * *"}])
async def attempt_auto_renewals() -> dict[str, int]:
    """Отрабатывает подошедшие циклы продления; каждый цикл идемпотентен."""
    from repibot_core.services.payment_notifications import AutoRenewalService

    # Оплата картой отключается пустыми реквизитами, и это рабочая
    # конфигурация: стенд может принимать только Stars. Без этой проверки
    # задача падала бы каждые десять минут, пряча настоящие ошибки в журнале.
    if not get_settings().yookassa_shop_id:
        return {"attempted": 0}

    engine = create_engine(get_settings().database_url)
    client = None
    try:
        client = create_yookassa_client()
        factory = create_session_factory(engine)
        async with factory() as session:
            attempted = await AutoRenewalService(session, client, get_settings()).run(
                now=datetime.now(UTC)
            )
    finally:
        if client is not None:
            await client.aclose()
        await engine.dispose()
    return {"attempted": attempted}


_PAYMENT_POLL_LOCK_NAMESPACE = 91_003


async def _try_claim_pending_payment(connection: AsyncConnection, attempt_id: int) -> bool:
    """Берёт session-level advisory lock: HTTP идёт без удержания row lock."""
    claimed = bool(
        await connection.scalar(
            select(func.pg_try_advisory_lock(_PAYMENT_POLL_LOCK_NAMESPACE, attempt_id))
        )
    )
    return claimed


async def _release_pending_payment_claim(connection: AsyncConnection, attempt_id: int) -> None:
    await connection.execute(
        select(func.pg_advisory_unlock(_PAYMENT_POLL_LOCK_NAMESPACE, attempt_id))
    )


def _panel_client() -> RemnawaveClient:
    """Импорт внутри функции по той же причине, что и у диспетчера ниже."""
    from repibot_core.integrations.remnawave.client import create_remnawave_client

    return create_remnawave_client()


def _dispatcher(
    factory: async_sessionmaker[AsyncSession],
    panel: RemnawaveClient,
    telegram: BotApi,
    support: SupportChat | None,
) -> OutboxDispatcher:
    """Собирается на каждый прогон.

    Импорт внутри функции разрывает цикл: services импортирует эту же задачу,
    чтобы поставить её после коммита.

    Фабрика сессий уходит внутрь: выдача доступа в панели работает в своей
    транзакции, а не в той, которой диспетчер закрывает сообщения очереди.
    """
    from repibot_core.integrations.remnawave.users import PanelUsers
    from repibot_core.services.dispatcher import build_dispatcher

    return build_dispatcher(factory, users=PanelUsers(panel), telegram=telegram, support=support)


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
