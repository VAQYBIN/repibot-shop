"""Задачи проверяются на InMemoryBroker — реальный Valkey для этого не нужен."""

import pytest
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
