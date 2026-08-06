"""Схемы запросов и ответов. Ровно то, что видит клиент."""

from __future__ import annotations

from datetime import datetime
from typing import Any
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
