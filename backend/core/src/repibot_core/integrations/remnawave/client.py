"""HTTP-клиент панели Remnawave.

Бизнес-методов здесь нет: только транспорт, авторизация и поведение при
отказах. Адреса и разбор ответов живут в фасадах users.py и squads.py — так
поведение при отказе панели меняется в одном месте, а не в каждом методе.
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

from repibot_core.settings import get_settings

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class RemnawaveError(Exception):
    """Базовая ошибка взаимодействия с панелью."""


class RemnawaveUnavailable(RemnawaveError):  # noqa: N818 — суффикс Error уже в базовом классе
    """Панель недоступна или отвечает ошибкой сервера после всех попыток."""


class RemnawaveRejected(RemnawaveError):  # noqa: N818 — суффикс Error уже в базовом классе
    """Панель ответила осмысленным отказом: 4xx кроме 404."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"панель отклонила запрос: {status_code}")
        self.status_code = status_code
        self.body = body


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

    max_attempts — именно попытки, а не повторы: три означает три запроса,
    а не один плюс три.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 10.0,
        max_attempts: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.max_attempts = max_attempts
        # Транспорт подменяется в тестах: заглушка отвечает за поведение
        # панели, а маршруты и тела запросов при этом проверяются настоящие.
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                # Тела фасады отдают готовой строкой JSON через content=, а на
                # него httpx тип содержимого не проставляет — панель без этого
                # заголовка читает запрос как пустой.
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.max_attempts),
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


def create_remnawave_client() -> RemnawaveClient:
    """Клиент по настройкам развёртывания.

    Единственная точка сборки: собранный вручную клиент не получает ни таймаут,
    ни число попыток из конфигурации, и обе настройки остаются мёртвыми.
    """
    settings = get_settings()
    return RemnawaveClient(
        base_url=settings.remnawave_base_url,
        token=settings.remnawave_token.get_secret_value(),
        timeout=settings.remnawave_timeout_seconds,
        max_attempts=settings.remnawave_max_attempts,
    )
