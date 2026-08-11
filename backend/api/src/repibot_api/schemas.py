"""Схемы запросов и ответов. Ровно то, что видит клиент."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from repibot_core.settings import Language


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    language: Language = "ru"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class EmailRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=1)
    password: str = Field(min_length=1)


class MiniAppLoginRequest(BaseModel):
    init_data: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    expires_in: int


class AcceptedResponse(BaseModel):
    status: str


class AuthMethodsResponse(BaseModel):
    """Какие способы входа показывать на экране входа.

    Passkey поддерживает браузер, а не сервер, поэтому здесь он всегда true:
    решение принимает клиент. Telegram зависит от настроек развёртывания.
    """

    telegram: bool
    passkey: bool = True


class PasskeyOptionsResponse(BaseModel):
    """Параметры WebAuthn как есть.

    Структура задана спецификацией браузера и целиком уходит в
    `navigator.credentials`; описывать её своими моделями значит поддерживать
    копию чужого стандарта.
    """

    options: dict[str, Any]


class PasskeyRegisterRequest(BaseModel):
    credential: dict[str, Any]
    name: str = Field(default="", max_length=64)


class PasskeyLoginRequest(BaseModel):
    credential: dict[str, Any]


class PasskeyResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None


class MeResponse(BaseModel):
    id: int
    email: str | None
    email_verified: bool
    telegram_username: str | None
    name: str | None
    language: Language
    role: str
    referral_code: str
    has_password: bool
    has_telegram: bool
    passkey_count: int


class UpdateMeRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    language: Language


class SetPasswordRequest(BaseModel):
    current_password: str | None = None
    new_password: str = Field(min_length=1)


class ChangeEmailRequest(BaseModel):
    email: EmailStr


class SessionResponse(BaseModel):
    id: UUID
    user_agent: str | None
    ip: str | None
    created_at: datetime
    is_current: bool


class LinkCodeResponse(BaseModel):
    """Код привязки Telegram и готовая ссылка в чат бота."""

    code: str
    url: str
    expires_in: int


class PlanRequest(BaseModel):
    """Тариф, каким его заводит администратор.

    Признака is_active здесь нет: тариф снимается с продажи архивацией через
    DELETE, а не переключением поля в форме редактирования.
    """

    code: str = Field(min_length=2, max_length=32)
    name: dict[str, str]
    description: dict[str, str] | None = None
    duration_days: int = Field(gt=0)
    # Строкой, а не float: цена уходит в YooKassa в виде «299.00», и двоичная
    # дробь превращается в расхождение с чеком.
    price_rub: Decimal = Field(ge=0, decimal_places=2)
    price_stars: int = Field(ge=0)
    traffic_limit_bytes: int = Field(ge=0)
    traffic_reset_strategy: Literal["NO_RESET", "DAY", "WEEK", "MONTH", "MONTH_ROLLING"]
    hwid_device_limit: int = Field(ge=0)
    internal_squad_uuids: list[UUID] = Field(min_length=1)
    is_trial: bool = False
    is_visible: bool = True
    sort_order: int = 0


class PlanResponse(BaseModel):
    id: int
    code: str
    name: dict[str, str]
    description: dict[str, str] | None
    duration_days: int
    price_rub: Decimal
    price_stars: int
    traffic_limit_bytes: int
    traffic_reset_strategy: str
    hwid_device_limit: int
    internal_squad_uuids: list[UUID]
    is_trial: bool
    is_active: bool
    is_visible: bool
    sort_order: int


class SquadResponse(BaseModel):
    uuid: UUID
    name: str


class PublicPlanResponse(BaseModel):
    """Тариф в витрине. Внутренние поля наружу не уезжают.

    internal_squad_uuids не отдаётся: состав локаций — наша кухня, а не то,
    что клиент должен видеть в ответе API.
    """

    id: int
    code: str
    name: dict[str, str]
    description: dict[str, str] | None
    duration_days: int
    price_rub: Decimal
    price_stars: int
    traffic_limit_bytes: int
    hwid_device_limit: int
    is_trial: bool


class SubscriptionResponse(BaseModel):
    plan_code: str
    plan_name: dict[str, str]
    status: str
    started_at: datetime
    expires_at: datetime
    subscription_url: str | None
    traffic_limit_bytes: int
    hwid_device_limit: int
    auto_renew_enabled: bool


class AutoRenewRequest(BaseModel):
    auto_renew_enabled: bool


class AutoRenewResponse(BaseModel):
    auto_renew_enabled: bool


class PaymentMethodResponse(BaseModel):
    """Действующая карта пользователя и доступность привязки без оплаты."""

    # Название приходит от провайдера («Bank card *4444»); пустое title при
    # непустой linked_at означает старую карту, привязанную до появления поля.
    title: str | None
    linked_at: datetime | None
    binding_available: bool
    # Начатая привязка, ответа по которой ещё нет. Провайдер отвечает не в тот
    # момент, когда человек вернулся в приложение, поэтому экрану нужно знать,
    # что ответ ещё в пути, — иначе он покажет «карта не привязана» тому, кто
    # только что её привязал.
    binding_pending: bool = False


class CardBindingResponse(BaseModel):
    """Адрес формы провайдера, где пользователь подтверждает карту."""

    confirmation_url: str | None


class AdminSubscriptionRequest(BaseModel):
    """Начисление дней или смена тарифа админом."""

    plan_id: int
    # Пустое значение означает смену тарифа с конвертацией остатка, а не
    # начисление нуля дней: у этих двух действий разный смысл.
    days: int | None = Field(default=None, gt=0)
    comment: str | None = Field(default=None, max_length=512)


class RefundMarkRequest(BaseModel):
    """Доказательство, что возврат у провайдера уже сделан человеком."""

    reference: str = Field(min_length=1, max_length=255)
    comment: str = Field(min_length=1, max_length=512)


class CompensationRequest(BaseModel):
    """Одна необратимая местная коррекция, подтверждаемая отдельно."""

    action: Literal["revoke_days", "reverse_referral_reward"]
    idempotency_key: str = Field(min_length=1, max_length=128)
    comment: str = Field(min_length=1, max_length=512)


class SubscriptionStateResponse(BaseModel):
    """Подписка вместе с правом на триал.

    Одним ответом, а не двумя запросами: экран подписки решает по обоим полям
    сразу, показать срок или кнопку триала.
    """

    subscription: SubscriptionResponse | None
    trial_available: bool


class DeviceResponse(BaseModel):
    hwid: str
    platform: str | None
    device_model: str | None
    os_version: str | None
    created_at: datetime


class DevicesResponse(BaseModel):
    devices: list[DeviceResponse]
    limit: int
    used: int


class UnlinkDeviceRequest(BaseModel):
    # В теле, а не в пути: hwid приходит от клиента произвольной строкой и в
    # сегменте адреса ломается.
    hwid: str = Field(min_length=1, max_length=255)


class TrafficDayResponse(BaseModel):
    day: date
    used_bytes: int


class TrafficResponse(BaseModel):
    used_bytes: int
    lifetime_bytes: int
    limit_bytes: int
    days: list[TrafficDayResponse]


class CreateOrderRequest(BaseModel):
    """Только намерение покупателя; тариф и сумма всегда читаются сервером."""

    plan_id: int = Field(gt=0)
    purpose: Literal["purchase", "renew", "gift"]
    # Stars намеренно остаётся значением контракта: сервер возвращает
    # стабильный provider_unavailable, пока ручной маршрут обслуживает YooKassa.
    provider: Literal["yookassa", "stars"]
    promo_code: str | None = Field(default=None, min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)
    # Не адрес, а поверхность: адрес возврата собирает сервер. Принять URL от
    # клиента значит согласиться увести человека с оплаты куда угодно.
    return_surface: Literal["web", "miniapp"] = "web"


class CardBindingRequest(BaseModel):
    """Откуда пользователь начал привязку — чтобы вернуть его туда же."""

    return_surface: Literal["web", "miniapp"] = "web"


class OrderResponse(BaseModel):
    """Без provider payload: клиенту достаточно снимка заказа и URL оплаты."""

    id: int
    purpose: str
    plan_id: int
    plan_code: str
    plan_name: dict[str, str]
    duration_days: int
    price_rub: Decimal
    price_stars: int
    gross_rub: Decimal
    discount_rub: Decimal
    amount_due_rub: Decimal
    status: str
    expires_at: datetime
    confirmation_url: str | None
    telegram_invoice_required: bool = False
    telegram_handoff_url: str | None = None


class PromoRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    percent_off: int = Field(default=0, ge=0, le=100)
    bonus_days: int = Field(default=0, ge=0)
    max_uses: int | None = Field(default=None, gt=0)
    per_user_limit: int | None = Field(default=None, gt=0)
    is_active: bool = True
    starts_at: datetime | None = None
    expires_at: datetime | None = None


class PromoResponse(BaseModel):
    id: int
    code: str
    percent_off: int
    bonus_days: int
    max_uses: int | None
    per_user_limit: int | None
    is_active: bool
    starts_at: datetime | None
    expires_at: datetime | None


class RedeemGiftRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class GiftVoucherResponse(BaseModel):
    code: str
    purchased_at: datetime
    redeemed_at: datetime | None
    expires_at: datetime
    purchased_by_me: bool
    redeemed_by_me: bool


class UnsubscribeRequest(BaseModel):
    token: str = Field(min_length=1, max_length=2048)


class WinbackClaimRequest(BaseModel):
    token: str = Field(min_length=1, max_length=2048)


class WinbackClaimResponse(BaseModel):
    days: int


class NotificationSettingsResponse(BaseModel):
    marketing_enabled: bool


class UpdateNotificationSettingsRequest(BaseModel):
    marketing_enabled: bool
