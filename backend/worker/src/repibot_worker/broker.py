"""Брокер воркера.

Модуль сохранён ради путей в командах запуска (`repibot_worker.broker:broker`).
Определения переехали в repibot_core.queue — их использует и api.
"""

from repibot_core.queue import broker, scheduler

__all__ = ["broker", "scheduler"]
