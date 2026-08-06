"""Публичные эндпоинты входа.

Роутер разбирает запрос, вызывает сервис и раскладывает результат по ответу и
cookie. Решений здесь нет — они в services.
"""

from __future__ import annotations

import hmac
import secrets
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.cookies import (
    OIDC_COOKIE,
    REFRESH_COOKIE,
    clear_oidc_cookie,
    clear_refresh_cookie,
    set_oidc_cookie,
    set_refresh_cookie,
)
from repibot_api.deps import (
    AuthContext,
    client_ip,
    current_context,
    db_session,
    get_principals,
    get_redis,
)
from repibot_api.errors import ApiError, api_error_from
from repibot_api.origins import allowed_origins
from repibot_api.schemas import (
    AcceptedResponse,
    AuthMethodsResponse,
    EmailRequest,
    LoginRequest,
    MiniAppLoginRequest,
    PasskeyLoginRequest,
    PasskeyOptionsResponse,
    PasswordResetRequest,
    RegisterRequest,
    TokenRequest,
    TokenResponse,
)
from repibot_core.integrations.telegram.oidc import TIMEOUT_SECONDS, TelegramOidc
from repibot_core.integrations.telegram.oidc import is_configured as telegram_is_configured
from repibot_core.ratelimit import (
    LETTER_PER_EMAIL,
    LETTER_PER_IP,
    LOGIN_PER_EMAIL,
    LOGIN_PER_IP,
    MINIAPP_PER_IP,
    OIDC_START_PER_IP,
    PASSKEY_PER_IP,
    REGISTER_PER_IP,
    RateLimiter,
    Rule,
)
from repibot_core.security.pkce import code_challenge, generate_code_verifier
from repibot_core.services.auth.passkey import PasskeyAuth
from repibot_core.services.auth.password import PasswordAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.telegram import TelegramAuth
from repibot_core.services.auth.types import AuthError, IssuedSession
from repibot_core.services.challenges import ChallengeStore
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import Settings, get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Десять минут на дорогу до Telegram и обратно: человек успевает подтвердить
# вход в другом приложении, а брошенная попытка не висит в Valkey сутками.
STATE_TTL_SECONDS = 600


async def _enforce(redis: Redis, key: str, rule: Rule) -> None:
    result = await RateLimiter(redis).hit(key, rule)
    if not result.allowed:
        raise ApiError(
            "слишком часто",
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            {"Retry-After": str(result.retry_after_seconds)},
        )


def _services(
    session: AsyncSession, principals: PrincipalCache
) -> tuple[AuthService, PasswordAuth, TelegramAuth]:
    settings = get_settings()
    auth = AuthService(session, settings, principals)
    return auth, PasswordAuth(session, settings, auth), TelegramAuth(session, settings, auth)


def _respond(response: Response, issued: IssuedSession) -> TokenResponse:
    if issued.refresh_token is not None and issued.refresh_expires_at is not None:
        set_refresh_cookie(
            response,
            issued.refresh_token,
            expires_at=issued.refresh_expires_at,
            secure=get_settings().environment == "production",
        )
    return TokenResponse(access_token=issued.access_token, expires_in=issued.access_expires_in)


@router.post("/register", status_code=202, response_model=AcceptedResponse)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AcceptedResponse:
    ip = client_ip(request)
    await _enforce(redis, f"register:ip:{ip}", REGISTER_PER_IP)

    _, letters, _ = _services(session, principals)
    try:
        await letters.register(
            email=payload.email, password=payload.password, language=payload.language
        )
    except AuthError as error:
        raise api_error_from(error) from error

    # Ответ одинаков и для нового адреса, и для повторной регистрации на
    # неподтверждённый: он не сообщает, есть ли такой аккаунт.
    return AcceptedResponse(status="verification_sent")


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(
    payload: TokenRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> TokenResponse:
    _, letters, _ = _services(session, principals)
    try:
        issued = await letters.verify_email(
            payload.token,
            user_agent=request.headers.get("user-agent"),
            ip=client_ip(request),
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return _respond(response, issued)


@router.post("/resend-verification", status_code=202, response_model=AcceptedResponse)
async def resend_verification(
    payload: EmailRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AcceptedResponse:
    await _enforce(redis, f"letter:email:{payload.email}", LETTER_PER_EMAIL)
    await _enforce(redis, f"letter:ip:{client_ip(request)}", LETTER_PER_IP)

    _, letters, _ = _services(session, principals)
    await letters.resend_verification(payload.email)
    return AcceptedResponse(status="verification_sent")


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TokenResponse:
    await _enforce(redis, f"login:ip:{client_ip(request)}", LOGIN_PER_IP)
    await _enforce(redis, f"login:email:{payload.email}", LOGIN_PER_EMAIL)

    _, letters, _ = _services(session, principals)
    try:
        issued = await letters.login(
            email=payload.email,
            password=payload.password,
            user_agent=request.headers.get("user-agent"),
            ip=client_ip(request),
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return _respond(response, issued)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> TokenResponse:
    settings = get_settings()
    origin = request.headers.get("origin")
    # Этот эндпоинт — единственный, работающий по cookie, поэтому единственный,
    # которому нужна защита от межсайтовой подделки запроса.
    if origin is None or origin not in allowed_origins(
        settings.public_web_url, settings.public_app_url
    ):
        raise ApiError("origin не разрешён", 403, "forbidden")

    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise ApiError("нет refresh-токена", 401, "unauthorized")

    auth, _, _ = _services(session, principals)
    try:
        issued = await auth.refresh(
            token, user_agent=request.headers.get("user-agent"), ip=client_ip(request)
        )
    except AuthError as error:
        # Ротация не удалась — cookie гасится, иначе браузер будет повторять
        # запрос с мёртвым токеном до истечения срока.
        clear_refresh_cookie(response, secure=settings.environment == "production")
        raise api_error_from(error) from error
    return _respond(response, issued)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> None:
    auth, _, _ = _services(session, principals)
    await auth.logout(context.session_id)
    clear_refresh_cookie(response, secure=get_settings().environment == "production")


@router.post("/password/forgot", status_code=202, response_model=AcceptedResponse)
async def forgot_password(
    payload: EmailRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AcceptedResponse:
    await _enforce(redis, f"letter:email:{payload.email}", LETTER_PER_EMAIL)
    await _enforce(redis, f"letter:ip:{client_ip(request)}", LETTER_PER_IP)

    _, letters, _ = _services(session, principals)
    await letters.request_reset(payload.email)
    # Ответ одинаков для существующего и несуществующего адреса: иначе форма
    # превращается в проверку, зарегистрирован ли человек.
    return AcceptedResponse(status="reset_sent")


@router.post("/password/reset", response_model=TokenResponse)
async def reset_password(
    payload: PasswordResetRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> TokenResponse:
    _, letters, _ = _services(session, principals)
    try:
        issued = await letters.reset(
            payload.token,
            payload.password,
            user_agent=request.headers.get("user-agent"),
            ip=client_ip(request),
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return _respond(response, issued)


@router.post("/email/change-confirm", status_code=204)
async def confirm_email_change(
    payload: TokenRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> None:
    """Подтверждение нового адреса.

    Эндпоинт публичный: письмо открывают в том браузере, где почта, а не в том,
    где открыт кабинет. Операцию авторизует сам токен.
    """
    _, letters, _ = _services(session, principals)
    try:
        await letters.apply_email_change(payload.token)
    except AuthError as error:
        raise api_error_from(error) from error


@router.post("/telegram/miniapp", response_model=TokenResponse)
async def login_from_miniapp(
    payload: MiniAppLoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TokenResponse:
    await _enforce(redis, f"miniapp:ip:{client_ip(request)}", MINIAPP_PER_IP)

    _, _, telegram = _services(session, principals)
    try:
        issued = await telegram.login_from_miniapp(payload.init_data, ip=client_ip(request))
    except AuthError as error:
        raise api_error_from(error) from error
    return _respond(response, issued)


def _passkeys(session: AsyncSession, principals: PrincipalCache, redis: Redis) -> PasskeyAuth:
    settings = get_settings()
    auth = AuthService(session, settings, principals)
    return PasskeyAuth(session, settings, auth, ChallengeStore(redis))


@router.post("/passkey/login/options", response_model=PasskeyOptionsResponse)
async def passkey_login_options(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> PasskeyOptionsResponse:
    await _enforce(redis, f"passkey:ip:{client_ip(request)}", PASSKEY_PER_IP)
    options = await _passkeys(session, principals, redis).login_options()
    return PasskeyOptionsResponse(options=options)


@router.post("/passkey/login/verify", response_model=TokenResponse)
async def passkey_login_verify(
    payload: PasskeyLoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TokenResponse:
    try:
        issued = await _passkeys(session, principals, redis).login(
            payload.credential,
            user_agent=request.headers.get("user-agent"),
            ip=client_ip(request),
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return _respond(response, issued)


def oidc_http_client() -> httpx.AsyncClient:
    """Отдельная функция — точка подмены в тестах: сети к Telegram там нет."""
    return httpx.AsyncClient(timeout=TIMEOUT_SECONDS)


def _redirect_uri(settings: Settings) -> str:
    """Адрес возврата собирается из PUBLIC_WEB_URL и должен совпадать с BotFather."""
    return f"{settings.public_web_url}/api/auth/telegram/callback"


def _to_login(settings: Settings, code: str) -> RedirectResponse:
    redirect = RedirectResponse(f"{settings.public_web_url}/login?error={code}", status_code=307)
    # Попытка входа закончилась — привязка к браузеру больше не нужна ни при
    # отказе, ни при успехе, и оставлять её значит держать лишний ключ, по
    # которому можно доиграть чужой state.
    clear_oidc_cookie(redirect, secure=settings.environment == "production")
    return redirect


@router.get("/methods", response_model=AuthMethodsResponse)
async def auth_methods() -> AuthMethodsResponse:
    # Тот же признак, что у самого входа: список способов не должен обещать
    # больше, чем эндпоинт готов выполнить.
    return AuthMethodsResponse(telegram=telegram_is_configured(get_settings()))


@router.get("/telegram/start")
async def telegram_start(
    request: Request, redis: Annotated[Redis, Depends(get_redis)]
) -> RedirectResponse:
    # Каждый старт кладёт в Valkey запись state на десять минут, а эндпоинт
    # публичный: без предела аноним набивает память. Превышение уходит обычной
    # ошибкой API, а не редиректом на страницу входа — отказ обслужить запрос
    # не является закончившейся попыткой входа.
    await _enforce(redis, f"oidc:start:ip:{client_ip(request)}", OIDC_START_PER_IP)

    settings = get_settings()
    async with oidc_http_client() as client:
        oidc = TelegramOidc(settings, redis, client=client)
        if not oidc.is_configured:
            return _to_login(settings, "telegram_unavailable")

        verifier = generate_code_verifier()
        state = secrets.token_urlsafe(32)
        # Привязка попытки к браузеру. Одного state мало: он приходит обратно в
        # адресе, и подсунуть жертве чужой готовый код — известный способ тихо
        # усадить её в аккаунт злоумышленника.
        binding = secrets.token_urlsafe(32)
        # Verifier живёт только у нас: браузеру достаётся его хеш, и перехваченный
        # код без нашего Valkey обменять нельзя.
        await redis.set(f"oidc:state:{state}", f"{binding}:{verifier}", ex=STATE_TTL_SECONDS)

        redirect = RedirectResponse(
            oidc.authorization_url(
                state=state,
                code_challenge=code_challenge(verifier),
                redirect_uri=_redirect_uri(settings),
            ),
            status_code=307,
        )
        set_oidc_cookie(redirect, binding, secure=settings.environment == "production")
        return redirect


@router.get("/telegram/callback")
async def telegram_callback(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> RedirectResponse:
    settings = get_settings()
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        return _to_login(settings, "token_invalid")

    # GETDEL: state одноразовый, иначе перехваченная ссылка возврата работала бы
    # столько же, сколько живёт запись.
    stored = await redis.getdel(f"oidc:state:{state}")
    if stored is None:
        return _to_login(settings, "token_invalid")
    raw = stored.decode() if isinstance(stored, bytes) else str(stored)
    binding, _, verifier = raw.partition(":")

    # Вход должен закончиться в том же браузере, где начался. Иначе ссылку
    # возврата с чужим кодом можно подсунуть жертве, и она молча окажется в
    # аккаунте злоумышленника.
    presented = request.cookies.get(OIDC_COOKIE, "")
    if not hmac.compare_digest(presented, binding):
        return _to_login(settings, "token_invalid")

    auth = AuthService(session, settings, principals)
    telegram = TelegramAuth(session, settings, auth)
    try:
        async with oidc_http_client() as client:
            oidc = TelegramOidc(settings, redis, client=client)
            token = await oidc.exchange(
                code=code, code_verifier=verifier, redirect_uri=_redirect_uri(settings)
            )
            identity = await oidc.verify_id_token(token)
        issued = await telegram.login_from_oidc(
            identity, user_agent=request.headers.get("user-agent"), ip=client_ip(request)
        )
    except AuthError as error:
        return _to_login(settings, error.code)

    # Access-токен остаётся вне адреса: кабинет получит его в память, вызвав
    # refresh по только что поставленной cookie. В строке он попал бы в историю
    # браузера и в журнал прокси.
    redirect = RedirectResponse(f"{settings.public_web_url}/account", status_code=307)
    if issued.refresh_token is not None and issued.refresh_expires_at is not None:
        set_refresh_cookie(
            redirect,
            issued.refresh_token,
            expires_at=issued.refresh_expires_at,
            secure=settings.environment == "production",
        )
    clear_oidc_cookie(redirect, secure=settings.environment == "production")
    return redirect
