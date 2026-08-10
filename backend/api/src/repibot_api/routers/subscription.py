"""Витрина тарифов и подписка текущего пользователя.

Отдельным файлом, а не дописыванием в me.py: общий файл в подпроекте 1 дважды
становился местом столкновения параллельных задач.
"""

from __future__ import annotations

import logging
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
    AutoRenewRequest,
    AutoRenewResponse,
    CardBindingRequest,
    CardBindingResponse,
    CreateOrderRequest,
    DeviceResponse,
    DevicesResponse,
    GiftVoucherResponse,
    OrderResponse,
    PaymentMethodResponse,
    PublicPlanResponse,
    RedeemGiftRequest,
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
from repibot_core.db.models import Order, OrderPurpose, PaymentAttempt, PaymentProvider, User
from repibot_core.integrations.remnawave.client import RemnawaveUnavailable
from repibot_core.integrations.telegram.bot_api import TIMEOUT_SECONDS as BOT_TIMEOUT_SECONDS
from repibot_core.integrations.telegram.bot_api import BotApi
from repibot_core.integrations.yookassa.client import YooKassaError
from repibot_core.ratelimit import DEVICE_UNLINK_WINDOW, Rule
from repibot_core.services.auth.types import AuthError
from repibot_core.services.devices import DeviceService, DeviceView
from repibot_core.services.errors import ServiceError
from repibot_core.services.payment_methods import CardBindingService, PaymentMethodService
from repibot_core.services.payments import PaymentService
from repibot_core.services.plans import PlanService
from repibot_core.services.promotions import GiftService
from repibot_core.services.subscriptions import SubscriptionService
from repibot_core.services.traffic import TrafficService
from repibot_core.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["subscription"])


@router.get("/api/me/gifts", response_model=list[GiftVoucherResponse])
async def my_gifts(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> list[GiftVoucherResponse]:
    return [
        GiftVoucherResponse.model_validate(item, from_attributes=True)
        for item in await GiftService(session).list_for_user(context.principal.user_id)
    ]


@router.post("/api/me/gifts/redeem", response_model=SubscriptionStateResponse)
async def redeem_gift(
    payload: RedeemGiftRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> SubscriptionStateResponse:
    try:
        view = await GiftService(session).redeem(payload.code, context.principal.user_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    return SubscriptionStateResponse(
        subscription=subscription_response(view), trial_available=False
    )


async def stars_handoff_url(redis: Redis, handoff_reference: str) -> str:
    """Постоянная ссылка будит бота; идентификатор оплаты браузер не пересекает."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=BOT_TIMEOUT_SECONDS) as client:
        username = await BotApi(settings, redis, client=client).username()
    return f"https://t.me/{username}?start=pay_{handoff_reference}"


async def return_url_for(redis: Redis, surface: str) -> str:
    """Куда провайдер вернёт человека после своей формы.

    Адрес собирается здесь, а не приходит из запроса: принять чужой URL значит
    согласиться увести плательщика с нашего домена куда угодно.

    Из Mini App оплата открывается внешним браузером, и вернуться в него же
    некуда — страница приложения вне Telegram войти не может. Поэтому обратно
    ведём в чат бота, откуда человек снова откроет приложение.
    """
    settings = get_settings()
    if surface != "miniapp":
        return f"{settings.public_web_url.rstrip('/')}/account/payments"
    async with httpx.AsyncClient(timeout=BOT_TIMEOUT_SECONDS) as client:
        username = await BotApi(settings, redis, client=client).username()
    return f"https://t.me/{username}"


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
    redis: Annotated[Redis, Depends(get_redis)],
    ip: Annotated[str | None, Depends(client_ip)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> OrderResponse:
    replay = await session.scalar(
        select(Order.id).where(
            Order.user_id == context.principal.user_id,
            Order.client_key == payload.idempotency_key,
        )
    )
    if replay is None:
        await enforce(redis, f"payment-create:user:{context.principal.user_id}", PAYMENT_CREATE)
        if ip is not None:
            await enforce(redis, f"payment-create:ip:{ip}", PAYMENT_CREATE)
    try:
        if payload.provider == "stars":
            user = await session.get(User, context.principal.user_id)
            if user is None or user.telegram_id is None:
                raise ApiError("сначала привяжите Telegram", 409, "telegram_required")
            stars_order = await payments.create_stars_order(
                user_id=context.principal.user_id,
                plan_id=payload.plan_id,
                purpose=OrderPurpose(payload.purpose),
                client_key=payload.idempotency_key,
                promo_code=payload.promo_code,
            )
            return order_response(
                stars_order.order,
                None,
                telegram_invoice_required=stars_order.invoice_payload is not None,
                telegram_handoff_url=(
                    await stars_handoff_url(redis, stars_order.handoff_reference)
                    if stars_order.handoff_reference is not None
                    else None
                ),
            )
        async with yookassa_client() as yookassa:
            yookassa_order = await payments.create_manual_yookassa_order(
                user_id=context.principal.user_id,
                plan_id=payload.plan_id,
                purpose=OrderPurpose(payload.purpose),
                client_key=payload.idempotency_key,
                promo_code=payload.promo_code,
                return_url=await return_url_for(redis, payload.return_surface),
                yookassa=yookassa,
            )
        return order_response(yookassa_order.order, yookassa_order.confirmation_url)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except AuthError as error:
        raise ApiError("Telegram временно недоступен", 503, "telegram_unavailable") from error
    except (httpx.HTTPError, YooKassaError) as error:
        raise ApiError("провайдер недоступен", 503, "provider_unavailable") from error


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


@router.get("/api/me/subscription/auto-renew", response_model=AutoRenewResponse)
async def get_auto_renew(
    subscriptions: Annotated[SubscriptionService, Depends(subscription_service)],
    context: Annotated[AuthContext, Depends(current_context)],
) -> AutoRenewResponse:
    try:
        enabled = await subscriptions.auto_renew_enabled(context.principal.user_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    return AutoRenewResponse(auto_renew_enabled=enabled)


@router.put("/api/me/subscription/auto-renew", response_model=AutoRenewResponse)
async def set_auto_renew(
    payload: AutoRenewRequest,
    subscriptions: Annotated[SubscriptionService, Depends(subscription_service)],
    context: Annotated[AuthContext, Depends(current_context)],
) -> AutoRenewResponse:
    try:
        enabled = await subscriptions.set_auto_renew_enabled(
            context.principal.user_id, payload.auto_renew_enabled
        )
    except ServiceError as error:
        raise api_error_from_service(error) from error
    return AutoRenewResponse(auto_renew_enabled=enabled)


@router.get("/api/me/payment-method", response_model=PaymentMethodResponse)
async def my_payment_method(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> PaymentMethodResponse:
    bindings = CardBindingService(session)
    # Человек попадает сюда сразу после формы провайдера. Дочитать его
    # привязку здесь дешевле, чем показать «карта не привязана» и получить
    # вторую попытку привязки от растерянного пользователя.
    if await bindings.has_pending(context.principal.user_id):
        try:
            async with yookassa_client() as yookassa:
                await bindings.settle_for_user(context.principal.user_id, yookassa)
        except (ApiError, httpx.HTTPError, YooKassaError):
            # Экран карты не должен падать из-за молчащего провайдера:
            # непрочитанную привязку добёрет сверка по расписанию.
            logger.warning("не удалось дочитать привязку карты", exc_info=True)
    card = await PaymentMethodService(session).current(context.principal.user_id)
    return PaymentMethodResponse(
        title=None if card is None else card.title,
        linked_at=None if card is None else card.linked_at,
        binding_available=get_settings().yookassa_zero_amount_binding,
    )


@router.delete("/api/me/payment-method", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_payment_method(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> None:
    """Отвязывает карту; автоплатёж выключается вместе с ней.

    Повтор не ошибка: у отсутствия карты и её удаления один и тот же
    наблюдаемый итог.
    """
    if session.in_transaction():
        await session.commit()
    async with session.begin():
        await PaymentMethodService(session).revoke(context.principal.user_id)


@router.post(
    "/api/me/payment-method/bindings",
    response_model=CardBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_card_binding(
    payload: CardBindingRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    ip: Annotated[str | None, Depends(client_ip)],
) -> CardBindingResponse:
    """Начинает привязку карты без списания."""
    await enforce(redis, f"payment-create:user:{context.principal.user_id}", PAYMENT_CREATE)
    if ip is not None:
        await enforce(redis, f"payment-create:ip:{ip}", PAYMENT_CREATE)
    try:
        async with yookassa_client() as yookassa:
            started = await CardBindingService(session).start(
                context.principal.user_id,
                yookassa,
                return_url=await return_url_for(redis, payload.return_surface),
            )
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except (httpx.HTTPError, YooKassaError) as error:
        raise ApiError("провайдер недоступен", 503, "provider_unavailable") from error
    return CardBindingResponse(confirmation_url=started.confirmation_url)


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
