"""Эндпоинты входа: формат ответов, cookie, лимиты, проверка Origin."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.models import User, UserRole
from repibot_core.testing.initdata import build_init_data

pytestmark = pytest.mark.docker

PASSWORD = "совершенно обычный пароль"
ORIGIN = "https://example.org"


async def _register_and_verify(client: AsyncClient, email: str = "user@example.org") -> None:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD, "language": "ru"}
    )
    assert response.status_code == 202

    from repibot_api.deps import get_session_factory

    async with get_session_factory()() as session:
        row = await session.execute(
            text("select payload from outbox where topic = 'email.verify' order by id desc limit 1")
        )
        link = str(row.scalar_one()["link"])

    token = link.split("token=")[1]
    confirmed = await client.post("/api/auth/verify-email", json={"token": token})
    assert confirmed.status_code == 200


async def _set_email_role(engine: AsyncEngine, role: UserRole) -> None:
    from repibot_core.db.engine import create_session_factory

    async with create_session_factory(engine)() as session:
        await session.execute(
            update(User).where(User.email == "user@example.org").values(role=role)
        )
        await session.commit()


async def test_registration_answers_202_without_leaking_anything(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/auth/register",
        json={"email": "user@example.org", "password": PASSWORD, "language": "ru"},
    )

    assert response.status_code == 202
    assert response.json() == {"status": "verification_sent"}


async def test_weak_password_returns_code(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/auth/register",
        json={"email": "user@example.org", "password": "короткий", "language": "ru"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "weak_password"


async def test_login_sets_httponly_cookie_scoped_to_refresh(api_client: AsyncClient) -> None:
    await _register_and_verify(api_client)

    response = await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["expires_in"] == 900

    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    # Starlette пишет значение как передано, а тип параметра допускает только
    # строчные варианты; по RFC 6265bis регистр атрибута всё равно не значим.
    assert "SameSite=lax" in cookie
    # Путь ограничен единственным эндпоинтом, который эту cookie читает.
    assert "Path=/api/auth/refresh" in cookie
    # Токен не должен появиться в теле ответа: там его достала бы любая XSS.
    assert "refresh" not in body


async def test_admin_login_sets_a_short_lived_assertion_scoped_to_admin(
    api_client: AsyncClient, engine: AsyncEngine
) -> None:
    """A browser admin receives routing evidence, not another API credential."""
    await _register_and_verify(api_client)
    await _set_email_role(engine, UserRole.admin)

    response = await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )

    assert response.status_code == 200
    admin_cookie = next(
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith("repibot_admin_assertion=")
    )
    assert "HttpOnly" in admin_cookie
    assert "SameSite=lax" in admin_cookie
    assert "Path=/admin" in admin_cookie
    assert "Max-Age=300" in admin_cookie


async def test_refresh_clears_admin_assertion_after_role_revocation(
    api_client: AsyncClient, engine: AsyncEngine
) -> None:
    await _register_and_verify(api_client)
    await _set_email_role(engine, UserRole.admin)
    await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )
    await _set_email_role(engine, UserRole.user)

    response = await api_client.post("/api/auth/refresh", headers={"Origin": ORIGIN})

    assert response.status_code == 200
    admin_cookie = next(
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith("repibot_admin_assertion=")
    )
    assert "Path=/admin" in admin_cookie
    assert "Max-Age=0" in admin_cookie


async def test_logout_clears_the_admin_assertion_cookie(
    api_client: AsyncClient, engine: AsyncEngine
) -> None:
    await _register_and_verify(api_client)
    await _set_email_role(engine, UserRole.admin)
    login = await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )

    response = await api_client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )

    assert response.status_code == 204
    admin_cookie = next(
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith("repibot_admin_assertion=")
    )
    assert "Path=/admin" in admin_cookie
    assert "Max-Age=0" in admin_cookie


async def test_login_before_verification_returns_403(api_client: AsyncClient) -> None:
    await api_client.post(
        "/api/auth/register",
        json={"email": "user@example.org", "password": PASSWORD, "language": "ru"},
    )

    response = await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_not_verified"


async def test_refresh_requires_matching_origin(api_client: AsyncClient) -> None:
    """Единственный эндпоинт, читающий cookie, обязан проверять Origin."""
    await _register_and_verify(api_client)
    await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )

    foreign = await api_client.post("/api/auth/refresh", headers={"Origin": "https://evil.example"})

    assert foreign.status_code == 403
    assert foreign.json()["error"]["code"] == "forbidden"


async def test_refresh_rotates_cookie(api_client: AsyncClient) -> None:
    await _register_and_verify(api_client)
    login = await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )
    first_cookie = login.headers["set-cookie"]

    refreshed = await api_client.post("/api/auth/refresh", headers={"Origin": ORIGIN})

    assert refreshed.status_code == 200
    assert refreshed.headers["set-cookie"] != first_cookie
    assert refreshed.json()["access_token"]


async def test_refresh_without_cookie_returns_401(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/auth/refresh", headers={"Origin": ORIGIN})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_logout_clears_cookie(api_client: AsyncClient) -> None:
    await _register_and_verify(api_client)
    login = await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )
    token = login.json()["access_token"]

    response = await api_client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]


async def test_login_rate_limit_returns_429_with_retry_after(api_client: AsyncClient) -> None:
    await _register_and_verify(api_client)

    for _ in range(5):
        await api_client.post(
            "/api/auth/login", json={"email": "user@example.org", "password": "неверный"}
        )
    response = await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": "неверный"}
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert int(response.headers["retry-after"]) > 0


async def test_forgot_password_answers_the_same_for_unknown_email(api_client: AsyncClient) -> None:
    known = await api_client.post("/api/auth/password/forgot", json={"email": "user@example.org"})
    unknown = await api_client.post("/api/auth/password/forgot", json={"email": "no@example.org"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


async def test_miniapp_login_returns_token_without_cookie(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/auth/telegram/miniapp",
        json={"init_data": build_init_data(bot_token="123456:test-token")},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "set-cookie" not in response.headers


async def test_bad_init_data_returns_401(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/auth/telegram/miniapp", json={"init_data": "подделка"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
