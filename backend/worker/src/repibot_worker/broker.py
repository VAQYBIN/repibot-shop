"""Брокер и планировщик.

Расписание живёт в метках задач (LabelScheduleSource), а не во внешнем
хранилище: расписание — часть кода и должно ездить вместе с ним в git.
"""

from __future__ import annotations

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from repibot_core.settings import get_settings

_settings = get_settings()

result_backend: RedisAsyncResultBackend[object] = RedisAsyncResultBackend(
    redis_url=_settings.valkey_url,
    result_ex_time=86_400,
    prefix_str="repibot_results",
)

broker = ListQueueBroker(url=_settings.valkey_url, queue_name="repibot_tasks").with_result_backend(
    result_backend
)

scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])
