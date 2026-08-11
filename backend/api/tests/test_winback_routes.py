"""Подарочные дни лесенки: кнопка из письма нажимается в кабинете."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import create_session_factory
from repibot_core.services.winback import WinbackService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker

# Ступень бесплатных дней при умолчании порогов лесенки.
DAYS_STEP = 3


async def _token(engine: AsyncEngine, user_id: int) -> str:
    async with create_session_factory(engine)() as session:
        raw = await WinbackService(session).issue_days_token(user_id, step=DAYS_STEP)
        await session.commit()
    return raw


async def test_days_are_granted_once(
    api_client: AsyncClient,
    engine: AsyncEngine,
    user_headers: dict[str, str],
    plain_user_id: int,
    month_plan: int,
) -> None:
    """Второй запрос приходит от почтового сканера ссылок, а не от человека."""
    token = await _token(engine, plain_user_id)

    granted = await api_client.post(
        "/api/winback/claim", json={"token": token}, headers=user_headers
    )
    again = await api_client.post("/api/winback/claim", json={"token": token}, headers=user_headers)

    assert granted.status_code == 200
    assert granted.json() == {"days": get_settings().winback_free_days}
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_token"


async def test_link_gives_nothing_to_the_stranger_who_got_the_letter(
    api_client: AsyncClient,
    engine: AsyncEngine,
    user_headers: dict[str, str],
    plain_user_id: int,
    telegram_user_headers: dict[str, str],
    month_plan: int,
) -> None:
    """Дни начисляются на аккаунт, и он должен быть свой."""
    token = await _token(engine, plain_user_id)

    response = await api_client.post(
        "/api/winback/claim", json={"token": token}, headers=telegram_user_headers
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_token"


async def test_claim_requires_signing_in(
    api_client: AsyncClient,
    engine: AsyncEngine,
    user_headers: dict[str, str],
    plain_user_id: int,
    month_plan: int,
) -> None:
    """Без входа неизвестно, кому начислять: токен личности не доказывает."""
    token = await _token(engine, plain_user_id)

    response = await api_client.post("/api/winback/claim", json={"token": token})

    assert response.status_code == 401
