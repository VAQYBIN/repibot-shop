"""HTTP-клиент панели Remnawave.

Бизнес-методов здесь нет: только транспорт, авторизация и поведение при
отказах. Методы появятся в подпроекте 2 и будут возвращать модели из models.py.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class RemnawaveError(Exception):
    """Базовая ошибка взаимодействия с панелью."""


class RemnawaveUnavailable(RemnawaveError):  # noqa: N818 — суффикс Error уже в базовом классе
    """Панель недоступна или отвечает ошибкой сервера после всех попыток."""


class _RetryableResponse(Exception):  # noqa: N818
    """Внутренний сигнал для tenacity: ответ получен, но его стоит повторить."""

    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"статус {response.status_code}")
        self.response = response


class RemnawaveClient:
    """Тонкая обёртка над httpx с ретраями на временных отказах.

    Повторяются только сетевые ошибки и коды 429 и 5xx. Ответы 4xx
    возвращаются как есть: повторять запрос, на который панель ответила
    осмысленным отказом, бессмысленно и вредно.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 10.0,
        max_retries: int = 3,
    ) -> None:
        self.max_retries = max_retries
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
        )

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=0.5, max=5),
                retry=retry_if_exception_type((httpx.TransportError, _RetryableResponse)),
            ):
                with attempt:
                    response = await self._http.request(method, path, **kwargs)
                    if response.status_code in _RETRYABLE_STATUSES:
                        raise _RetryableResponse(response)
                    return response
        except RetryError as error:
            logger.warning("панель Remnawave недоступна: %s %s", method, path)
            raise RemnawaveUnavailable(f"{method} {path}") from error
        raise RemnawaveUnavailable(f"{method} {path}")  # pragma: no cover

    async def aclose(self) -> None:
        await self._http.aclose()
