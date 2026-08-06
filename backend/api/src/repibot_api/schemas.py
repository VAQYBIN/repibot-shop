"""Схемы запросов и ответов. Ровно то, что видит клиент."""

from __future__ import annotations

from datetime import datetime
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
