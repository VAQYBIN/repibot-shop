"""Сборка сервисов подписки и перевод её состояния в ответ API.

Отдельным модулем, а не в роутере: подписку начисляет и клиентский маршрут, и
админский, и собирают они один и тот же сервис и одну и ту же схему ответа.
Написанное дважды разошлось бы на первой же правке — например, при добавлении
поля в ответ, — и человек видел бы разный набор сведений в зависимости от того,
кто начислил дни.

Клиент панели создаётся отдельной функцией, потому что это единственная точка
подмены в тестах: живой панели в наборе нет.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import db_session, get_redis
from repibot_api.errors import ApiError
from repibot_api.schemas import OrderResponse, SubscriptionResponse
from repibot_core.db.models import Order
from repibot_core.integrations.remnawave.client import RemnawaveClient, create_remnawave_client
from repibot_core.integrations.remnawave.devices import PanelDevices
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.integrations.remnawave.stats import PanelStats
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.integrations.yookassa.client import (
    YooKassaClient,
    YooKassaError,
    create_yookassa_client,
)
from repibot_core.services.devices import DeviceService
from repibot_core.services.panel_cache import PanelCache
from repibot_core.services.payments import PaymentService
from repibot_core.services.plans import PlanService
from repibot_core.services.provisioning import ProvisioningService
from repibot_core.services.subscriptions import SubscriptionService, SubscriptionView
from repibot_core.services.traffic import TrafficService
from repibot_core.settings import get_settings


def panel_client() -> RemnawaveClient:
    """Точка подмены в тестах: живой панели в наборе нет."""
    return create_remnawave_client()


async def plan_service(
    session: Annotated[AsyncSession, Depends(db_session)],
) -> AsyncIterator[PlanService]:
    """Сервис тарифов вместе с клиентом панели.

    Клиент закрывается после ответа: httpx держит пул соединений, и клиент на
    каждый запрос без закрытия оставляет сокеты открытыми до сборки мусора.
    """
    client = panel_client()
    try:
        yield PlanService(session, PanelSquads(client))
    finally:
        await client.aclose()


async def subscription_service(
    session: Annotated[AsyncSession, Depends(db_session)],
) -> AsyncIterator[SubscriptionService]:
    """Сервис подписки вместе с клиентом панели.

    Клиент нужен здесь по-настоящему: начисление дней сразу же пробует завести
    пользователя в панели. Закрывается он так же, как у тарифов, — в finally.
    """
    client = panel_client()
    try:
        yield SubscriptionService(
            session, get_settings(), ProvisioningService(session, PanelUsers(client))
        )
    finally:
        await client.aclose()


async def device_service(
    session: Annotated[AsyncSession, Depends(db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AsyncIterator[DeviceService]:
    client = panel_client()
    try:
        yield DeviceService(
            session,
            PanelDevices(client),
            PanelCache(redis, get_settings().panel_cache_ttl_seconds),
        )
    finally:
        await client.aclose()


async def traffic_service(
    session: Annotated[AsyncSession, Depends(db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AsyncIterator[TrafficService]:
    client = panel_client()
    try:
        yield TrafficService(
            session,
            PanelUsers(client),
            PanelStats(client),
            PanelCache(redis, get_settings().panel_cache_ttl_seconds),
        )
    finally:
        await client.aclose()


async def payment_service(
    session: Annotated[AsyncSession, Depends(db_session)],
) -> AsyncIterator[PaymentService]:
    """Платёжный сервис не владеет HTTP-клиентом провайдера.

    Так создание заказа, callback и фоновая сверка используют одну предметную
    транзакционную точку, а provider остаётся явной зависимостью маршрута.
    """
    yield PaymentService(session, get_settings())


async def yookassa_client() -> AsyncIterator[YooKassaClient]:
    try:
        client = create_yookassa_client()
    except YooKassaError as error:
        raise ApiError("провайдер недоступен", 503, "provider_unavailable") from error
    try:
        yield client
    finally:
        await client.aclose()


def subscription_response(view: SubscriptionView) -> SubscriptionResponse:
    return SubscriptionResponse(
        plan_code=view.plan_code,
        plan_name=view.plan_name,
        status=view.status.value,
        started_at=view.started_at,
        expires_at=view.expires_at,
        subscription_url=view.subscription_url,
        traffic_limit_bytes=view.traffic_limit_bytes,
        hwid_device_limit=view.hwid_device_limit,
    )


def order_response(order: Order, confirmation_url: str | None) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        purpose=order.purpose.value,
        plan_id=order.plan_id,
        plan_code=order.plan_code_snapshot,
        plan_name=order.plan_name_snapshot,
        duration_days=order.duration_days_snapshot,
        price_rub=order.price_rub_snapshot,
        price_stars=order.price_stars_snapshot,
        gross_rub=order.gross_rub,
        discount_rub=order.discount_rub,
        amount_due_rub=order.amount_due_rub,
        status=order.status.value,
        expires_at=order.expires_at,
        confirmation_url=confirmation_url,
    )
