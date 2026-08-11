"""Входящие вебхуки внешних систем.

Секрета в адресе нет: URL целиком попадает в журналы прокси и мониторинга.
Источник подтверждается подписью тела.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from httpx import HTTPStatusError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import db_session, get_redis
from repibot_api.errors import ApiError
from repibot_core.db.models import CardBinding
from repibot_core.integrations.yookassa.client import create_yookassa_client
from repibot_core.services.panel_cache import PanelCache
from repibot_core.services.panel_webhooks import PanelWebhookService, verify_signature
from repibot_core.services.payment_methods import CardBindingReader, CardBindingService
from repibot_core.services.payments import PaymentService
from repibot_core.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/webhook/yookassa", status_code=status.HTTP_204_NO_CONTENT)
async def yookassa_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
) -> Response:
    """Принимает только идентификатор hint и сверяет платёж у YooKassa."""
    payload = await request.json()
    payment_id = (
        payload.get("object", {}).get("id")
        if isinstance(payload, dict) and isinstance(payload.get("object"), dict)
        else None
    )
    if not isinstance(payment_id, str) or not payment_id:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Тип события — только подсказка о том, какой ресурс читать у провайдера.
    # Коммерческое решение по-прежнему принимается по прочитанному ответу, а
    # не по телу вызова: подсунуть чужой event значит лишь послать нас не туда.
    event = payload.get("event") if isinstance(payload, dict) else None
    client = create_yookassa_client()
    try:
        if isinstance(event, str) and event.startswith("payment_method."):
            await _settle_card_binding(session, payment_id, client)
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        finalized = await PaymentService(session).verify_yookassa_callback(payment_id, client)
        if finalized is None:
            await _settle_card_binding(session, payment_id, client)
    except HTTPStatusError as error:
        # У привязки тот же вид идентификатора, но живёт она в другом ресурсе
        # провайдера, и запрос платежа отвечает 404. Это повод попробовать
        # привязку, а не сбой приёма.
        if error.response.status_code != status.HTTP_404_NOT_FOUND:
            raise
        await _settle_card_binding(session, payment_id, client)
    finally:
        await client.aclose()
    await _wake_outbox()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _wake_outbox() -> None:
    """Просит воркер разобрать очередь сейчас, а не в следующую минуту.

    Оплата подтверждена, но доступ выдаёт и уведомление шлёт та же очередь, и
    по расписанию она просыпается раз в минуту. Человек к этому моменту уже
    вернулся с формы оплаты и смотрит на экран, где ничего не изменилось.

    Постановка задачи идёт после того, как всё записано: раньше воркер ничего
    бы не нашёл. Отказ брокера ничего не отменяет — очередь разберётся по
    расписанию, просто позже.
    """
    from repibot_core.tasks import process_outbox

    try:
        await process_outbox.kiq()
    except Exception:  # недоступный брокер не должен ломать приём вебхука
        logger.warning("не удалось попросить воркер разобрать outbox", exc_info=True)


async def _settle_card_binding(
    session: AsyncSession, provider_binding_id: str, client: CardBindingReader
) -> None:
    """Дочитывает у провайдера привязку, о которой пришёл этот же вызов.

    Событие о карте приходит тем же адресом, что и о платеже, поэтому чужой
    для платежей идентификатор — не мусор, а вторая половина того же потока.
    """
    binding_id = await session.scalar(
        select(CardBinding.id).where(CardBinding.provider_binding_id == provider_binding_id)
    )
    if binding_id is None:
        return
    await CardBindingService(session).settle(binding_id, client)


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
