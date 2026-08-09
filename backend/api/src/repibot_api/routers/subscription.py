"""Витрина тарифов и подписка текущего пользователя.

Отдельным файлом, а не дописыванием в me.py: общий файл в подпроекте 1 дважды
становился местом столкновения параллельных задач.
"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, client_ip, current_context, db_session, get_redis
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.limits import PAYMENT_CREATE, enforce
from repibot_api.schemas import (
    CreateOrderRequest,
    DeviceResponse,
    DevicesResponse,
    OrderResponse,
    PublicPlanResponse,
    SubscriptionStateResponse,
    TrafficDayResponse,
    TrafficResponse,
    UnlinkDeviceRequest,
)
from repibot_api.subscription_view import (
    device_service,
    order_response,
    payment_service,
    plan_service,
    subscription_response,
    subscription_service,
    traffic_service,
    yookassa_client,
)
from repibot_core.db.models import Order, OrderPurpose, PaymentAttempt, PaymentProvider
from repibot_core.integrations.remnawave.client import RemnawaveUnavailable
from repibot_core.integrations.yookassa.client import YooKassaClient, YooKassaError
from repibot_core.ratelimit import DEVICE_UNLINK_WINDOW, Rule
from repibot_core.services.devices import DeviceService, DeviceView
from repibot_core.services.errors import ServiceError
from repibot_core.services.payments import PaymentService
from repibot_core.services.plans import PlanService
from repibot_core.services.subscriptions import SubscriptionService
from repibot_core.services.traffic import TrafficService
from repibot_core.settings import get_settings

router = APIRouter(tags=["subscription"])


async def _confirmation_urls(session: AsyncSession, order_ids: list[int]) -> dict[int, str | None]:
    if not order_ids:
        return {}
    attempts = list(
        (
            await session.scalars(
                select(PaymentAttempt).where(
                    PaymentAttempt.order_id.in_(order_ids),
                    PaymentAttempt.provider == PaymentProvider.yookassa,
                )
            )
        ).all()
    )
    urls: dict[int, str | None] = {}
    for attempt in attempts:
        payload = attempt.verified_payload or {}
        value = payload.get("confirmation_url")
        urls[attempt.order_id] = value if isinstance(value, str) else None
    return urls


@router.post("/api/me/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: CreateOrderRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    payments: Annotated[PaymentService, Depends(payment_service)],
    yookassa: Annotated[YooKassaClient, Depends(yookassa_client)],
    redis: Annotated[Redis, Depends(get_redis)],
    ip: Annotated[str | None, Depends(client_ip)],
) -> OrderResponse:
    await enforce(redis, f"payment-create:user:{context.principal.user_id}", PAYMENT_CREATE)
    if ip is not None:
        await enforce(redis, f"payment-create:ip:{ip}", PAYMENT_CREATE)
    if payload.provider != "yookassa":
        raise ApiError("провайдер недоступен", 503, "provider_unavailable")
    try:
        created = await payments.create_manual_yookassa_order(
            user_id=context.principal.user_id,
            plan_id=payload.plan_id,
            purpose=OrderPurpose(payload.purpose),
            client_key=payload.idempotency_key,
            promo_code=payload.promo_code,
            save_payment_method=payload.save_payment_method,
            yookassa=yookassa,
        )
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except (httpx.HTTPError, YooKassaError) as error:
        raise ApiError("провайдер недоступен", 503, "provider_unavailable") from error
    return order_response(created.order, created.confirmation_url)


@router.get("/api/me/orders", response_model=list[OrderResponse])
async def list_orders(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> list[OrderResponse]:
    orders = list(
        (
            await session.scalars(
                select(Order)
                .where(Order.user_id == context.principal.user_id)
                .order_by(Order.id.desc())
            )
        ).all()
    )
    urls = await _confirmation_urls(session, [order.id for order in orders])
    return [order_response(order, urls.get(order.id)) for order in orders]


@router.get("/api/me/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> OrderResponse:
    order = await session.scalar(
        select(Order).where(Order.id == order_id, Order.user_id == context.principal.user_id)
    )
    if order is None:
        raise ApiError("заказ не найден", 404, "not_found")
    urls = await _confirmation_urls(session, [order.id])
    return order_response(order, urls.get(order.id))


@router.get("/api/plans", response_model=list[PublicPlanResponse])
async def list_plans(
    plans: Annotated[PlanService, Depends(plan_service)],
) -> list[PublicPlanResponse]:
    """Витрина открыта без входа: до регистрации человеку не на что смотреть."""
    return [
        PublicPlanResponse(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            description=plan.description,
            duration_days=plan.duration_days,
            price_rub=plan.price_rub,
            price_stars=plan.price_stars,
            traffic_limit_bytes=plan.traffic_limit_bytes,
            hwid_device_limit=plan.hwid_device_limit,
            is_trial=plan.is_trial,
        )
        for plan in await plans.visible()
    ]


@router.get("/api/me/subscription", response_model=SubscriptionStateResponse)
async def my_subscription(
    subscriptions: Annotated[SubscriptionService, Depends(subscription_service)],
    context: Annotated[AuthContext, Depends(current_context)],
) -> SubscriptionStateResponse:
    """Подписки может не быть, и это не ошибка.

    Пустой ответ со статусом 200 фронтенд отличает от отказа; 404 он вынужден
    был бы разбирать по коду, чтобы понять, показывать витрину или сообщение.
    """
    view = await subscriptions.current(context.principal.user_id)
    return SubscriptionStateResponse(
        subscription=subscription_response(view) if view is not None else None,
        trial_available=await subscriptions.trial_available(context.principal.user_id),
    )


@router.post(
    "/api/me/subscription/trial",
    response_model=SubscriptionStateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def activate_trial(
    subscriptions: Annotated[SubscriptionService, Depends(subscription_service)],
    context: Annotated[AuthContext, Depends(current_context)],
) -> SubscriptionStateResponse:
    try:
        view = await subscriptions.activate_trial(context.principal.user_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveUnavailable as error:  # pragma: no cover — выдача уходит в очередь
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    # Право на триал израсходовано в той же транзакции, что и подписка:
    # перечитывать его из базы значит задать вопрос с известным ответом.
    return SubscriptionStateResponse(
        subscription=subscription_response(view), trial_available=False
    )


def _device(view: DeviceView) -> DeviceResponse:
    return DeviceResponse(
        hwid=view.hwid,
        platform=view.platform,
        device_model=view.device_model,
        os_version=view.os_version,
        created_at=view.created_at,
    )


@router.get("/api/me/devices", response_model=DevicesResponse)
async def my_devices(
    devices: Annotated[DeviceService, Depends(device_service)],
    context: Annotated[AuthContext, Depends(current_context)],
) -> DevicesResponse:
    try:
        view = await devices.list(context.principal.user_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveUnavailable as error:
        # Карточка подписки рисуется целиком: данные о ней лежат у нас, и
        # терять весь экран из-за чужого отказа нечестно. Недоступен только
        # блок устройств.
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    return DevicesResponse(
        devices=[_device(item) for item in view.devices], limit=view.limit, used=view.used
    )


@router.post("/api/me/devices/unlink", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_device(
    payload: UnlinkDeviceRequest,
    devices: Annotated[DeviceService, Depends(device_service)],
    context: Annotated[AuthContext, Depends(current_context)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    settings = get_settings()
    await enforce(
        redis,
        f"device-unlink:{context.principal.user_id}",
        Rule(limit=settings.device_unlink_limit_per_day, window=DEVICE_UNLINK_WINDOW),
    )
    try:
        await devices.unlink(context.principal.user_id, payload.hwid)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveUnavailable as error:
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error


@router.get("/api/me/traffic", response_model=TrafficResponse)
async def my_traffic(
    traffic: Annotated[TrafficService, Depends(traffic_service)],
    context: Annotated[AuthContext, Depends(current_context)],
) -> TrafficResponse:
    try:
        view = await traffic.current(context.principal.user_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveUnavailable as error:
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    return TrafficResponse(
        used_bytes=view.used_bytes,
        lifetime_bytes=view.lifetime_bytes,
        limit_bytes=view.limit_bytes,
        days=[TrafficDayResponse(day=item.day, used_bytes=item.used_bytes) for item in view.days],
    )
