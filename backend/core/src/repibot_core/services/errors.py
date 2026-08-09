"""Ошибка сервиса: что произошло, а не как об этом сообщить по HTTP.

Код выбирает сервис, статус — слой API. Так одно и то же событие одинаково
называется в ответе REST, в боте и в логе.
"""

from __future__ import annotations


class ServiceError(Exception):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code
