"""Входящие вебхуки внешних систем.

Секрета в адресе нет: URL целиком попадает в журналы прокси и мониторинга.
Источник подтверждается подписью тела.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import db_session, get_redis
from repibot_api.errors import ApiError
from repibot_core.services.panel_cache import PanelCache
from repibot_core.services.panel_webhooks import PanelWebhookService, verify_signature
from repibot_core.settings import get_settings

router = APIRouter(tags=["webhooks"])


@router.post("/webhook/remnawave", status_code=status.HTTP_204_NO_CONTENT)
async def remnawave_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    settings = get_settings()
    secret = settings.remnawave_webhook_secret.get_secret_value()
    if not secret:
        raise ApiError("вебхуки панели не настроены", 503, "webhooks_disabled")

    # Сырое тело, а не разобранный объект: пересобранный JSON отличается от
    # присланного пробелами и порядком ключей, и подпись не сойдётся.
    body = await request.body()
    if not verify_signature(secret, body, request.headers.get(settings.remnawave_webhook_header)):
        raise ApiError("подпись не сошлась", 403, "forbidden")

    cache = PanelCache(redis, ttl_seconds=settings.panel_cache_ttl_seconds)
    await PanelWebhookService(session, cache).handle(await request.json())
    # Повтор не ошибка: на ошибку панель ответит новой попыткой, и приём
    # зациклится на событии, которое мы уже обработали.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
