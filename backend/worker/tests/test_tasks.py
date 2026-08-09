"""Задачи проверяются на InMemoryBroker — реальный Valkey для этого не нужен."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from taskiq import InMemoryBroker

from repibot_worker import tasks
from repibot_worker.broker import broker


async def test_heartbeat_returns_alive_status(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _reachable(*_args: object, **_kwargs: object) -> bool:
        return True

    monkeypatch.setattr("repibot_worker.tasks.check_database", _reachable)

    result = await tasks.heartbeat()

    assert result == {"status": "alive", "database": "ok"}


async def test_heartbeat_reports_database_down(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _unreachable(*_args: object, **_kwargs: object) -> bool:
        return False

    monkeypatch.setattr("repibot_worker.tasks.check_database", _unreachable)

    result = await tasks.heartbeat()

    assert result["database"] == "down"


async def test_task_can_be_dispatched_and_executed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _reachable(*_args: object, **_kwargs: object) -> bool:
        return True

    monkeypatch.setattr("repibot_worker.tasks.check_database", _reachable)

    test_broker = InMemoryBroker()
    task = test_broker.register_task(tasks.heartbeat.original_func, task_name="heartbeat")

    await test_broker.startup()
    handle = await task.kiq()
    result = await handle.wait_result(timeout=5)
    await test_broker.shutdown()

    assert result.is_err is False
    assert result.return_value["status"] == "alive"


def test_heartbeat_has_schedule_label() -> None:
    """Без метки schedule задача не выполнится сама — это легко упустить."""
    schedule = tasks.heartbeat.labels.get("schedule")

    assert schedule, "у задачи heartbeat нет метки schedule"
    assert schedule[0]["cron"] == "*/5 * * * *"


def test_broker_queue_name_is_namespaced() -> None:
    """Один Valkey может обслуживать и панель, и магазин — очереди не должны пересекаться."""
    assert broker.queue_name == "repibot_tasks"


def test_broker_disables_socket_read_timeout() -> None:
    """С таймаутом чтения воркер умирает через пять секунд простоя.

    Он ждёт задачу блокирующим brpop, а таймаут превращает ожидание в ошибку,
    которую taskiq-redis не обрабатывает.
    """
    assert broker.connection_pool.connection_kwargs["socket_timeout"] is None


@pytest.mark.docker
async def test_poll_recovers_a_succeeded_payment_without_a_webhook(
    postgres_url: str, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost webhook must not strand a successfully paid, non-expired order."""
    from repibot_core.db.models import (
        Order,
        OrderStatus,
        PaymentProvider,
        Plan,
        TrafficResetStrategy,
        User,
    )
    from repibot_core.db.repositories.orders import OrderRepository, PaymentAttemptRepository
    from repibot_core.integrations.yookassa.testing import FakeYooKassa
    from repibot_core.settings import get_settings

    plan = Plan(
        code="poll-month",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("254.15"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=["11111111-1111-4111-8111-111111111111"],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    user = User(email="poll@example.org", referral_code="poll00001")
    db_session.add_all((plan, user))
    await db_session.flush()
    order = await OrderRepository(db_session).create_pending(
        user_id=user.id,
        plan=plan,
        client_key="poll-order",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    attempt = await PaymentAttemptRepository(db_session).get_or_create(
        order_id=order.id,
        provider=PaymentProvider.yookassa,
        attempt_no=1,
        provider_key="poll-attempt",
        provider_payment_id="poll-payment",
    )
    await db_session.commit()

    fake = FakeYooKassa()
    fake.set_payment("poll-payment", status="succeeded", amount="254.15", currency="RUB")
    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", postgres_url)
    monkeypatch.setattr("repibot_core.tasks.create_yookassa_client", lambda: fake)

    result = await tasks.reconcile_pending_payments()

    assert result == {"checked": 1, "fulfilled": 1}
    status = await db_session.scalar(select(Order.status).where(Order.id == order.id))
    assert status is OrderStatus.fulfilled
    assert attempt.provider_payment_id == "poll-payment"


@pytest.mark.docker
async def test_pending_payment_claim_is_exclusive_between_overlapping_polls(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Two poll workers must not fetch the same pending provider payment concurrently."""
    from repibot_core import tasks as core_tasks
    from repibot_core.db.models import (
        PaymentProvider,
        Plan,
        TrafficResetStrategy,
        User,
    )
    from repibot_core.db.repositories.orders import OrderRepository, PaymentAttemptRepository

    plan = Plan(
        code="claim-month",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("254.15"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=["11111111-1111-4111-8111-111111111111"],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    user = User(email="claim@example.org", referral_code="claim001")
    db_session.add_all((plan, user))
    await db_session.flush()
    order = await OrderRepository(db_session).create_pending(
        user_id=user.id,
        plan=plan,
        client_key="claim-order",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    attempt = await PaymentAttemptRepository(db_session).get_or_create(
        order_id=order.id,
        provider=PaymentProvider.yookassa,
        attempt_no=1,
        provider_key="claim-attempt",
        provider_payment_id="claim-payment",
    )
    await db_session.commit()

    async with engine.connect() as first, engine.connect() as second:
        assert await core_tasks._try_claim_pending_payment(first, attempt.id)
        assert not await core_tasks._try_claim_pending_payment(second, attempt.id)
        await core_tasks._release_pending_payment_claim(first, attempt.id)
