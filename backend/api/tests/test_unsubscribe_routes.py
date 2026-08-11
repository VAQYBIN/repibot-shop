"""Отписка доступна без заголовка авторизации."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.docker


async def test_unsubscribe_needs_no_authorization(
    api_client: AsyncClient, user_headers: dict[str, str]
) -> None:
    """Человек открывает ссылку из письма в браузере, где сессии может не быть."""
    from repibot_core.services.unsubscribe import sign_unsubscribe_token

    me = await api_client.get("/api/me", headers=user_headers)
    token = sign_unsubscribe_token(me.json()["id"])

    response = await api_client.post("/api/unsubscribe", json={"token": token})

    assert response.status_code == 204


async def test_bad_token_is_a_stable_error(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/unsubscribe", json={"token": "чужой"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_token"
