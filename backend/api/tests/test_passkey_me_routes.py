"""Управление ключами доступа в кабинете: заведение, список, удаление.

Здесь ключ заводится тем же путём, что у человека, — через HTTP: параметры,
ответ аутентификатора, сохранение. Тесты входа лежат отдельно и сервис зовут
напрямую, потому что проверяют другое.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from webauthn.helpers import base64url_to_bytes

from repibot_core.security.webauthn import relying_party
from repibot_core.settings import get_settings
from repibot_core.testing.webauthn import SoftAuthenticator

pytestmark = pytest.mark.docker

PASSWORD = "совершенно обычный пароль"


def _device() -> SoftAuthenticator:
    party = relying_party(get_settings().public_web_url)
    return SoftAuthenticator(rp_id=party.rp_id, origin=party.origin)


async def _sign_in(client: AsyncClient, email: str = "user@example.org") -> str:
    """Регистрация, подтверждение по ссылке из outbox. Возвращает access-токен."""
    registered = await client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD, "language": "ru"}
    )
    assert registered.status_code == 202

    from repibot_api.deps import get_session_factory

    async with get_session_factory()() as session:
        row = await session.execute(
            text("select payload from outbox where topic = 'email.verify' order by id desc limit 1")
        )
        link = str(row.scalar_one()["link"])

    confirmed = await client.post("/api/auth/verify-email", json={"token": link.split("token=")[1]})
    assert confirmed.status_code == 200
    return str(confirmed.json()["access_token"])


async def _add_key(
    client: AsyncClient, token: str, device: SoftAuthenticator, name: str = "Ноутбук"
) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    options = await client.post("/api/me/passkeys/options", headers=headers)
    assert options.status_code == 200
    challenge = base64url_to_bytes(options.json()["options"]["challenge"])

    created = await client.post(
        "/api/me/passkeys",
        headers=headers,
        json={"credential": device.register(challenge), "name": name},
    )
    assert created.status_code == 201


async def test_registered_key_appears_in_the_list(api_client: AsyncClient) -> None:
    token = await _sign_in(api_client)
    await _add_key(api_client, token, _device(), name="Рабочий ноутбук")

    response = await api_client.get(
        "/api/me/passkeys", headers={"Authorization": f"Bearer {token}"}
    )

    body: list[dict[str, Any]] = response.json()
    assert [item["name"] for item in body] == ["Рабочий ноутбук"]
    assert body[0]["last_used_at"] is None


async def test_profile_counts_registered_keys(api_client: AsyncClient) -> None:
    token = await _sign_in(api_client)
    await _add_key(api_client, token, _device())

    response = await api_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert response.json()["passkey_count"] == 1


async def test_key_is_removed_while_password_remains(api_client: AsyncClient) -> None:
    """У аккаунта есть пароль, поэтому ключ снять можно."""
    token = await _sign_in(api_client)
    await _add_key(api_client, token, _device())
    headers = {"Authorization": f"Bearer {token}"}
    listed = await api_client.get("/api/me/passkeys", headers=headers)

    removed = await api_client.delete(f"/api/me/passkeys/{listed.json()[0]['id']}", headers=headers)

    assert removed.status_code == 204
    assert (await api_client.get("/api/me/passkeys", headers=headers)).json() == []


async def test_second_key_of_the_same_device_is_refused(api_client: AsyncClient) -> None:
    """Тот же аутентификатор дважды: в списке появились бы два неотличимых ключа."""
    token = await _sign_in(api_client)
    device = _device()
    await _add_key(api_client, token, device)
    headers = {"Authorization": f"Bearer {token}"}

    options = await api_client.post("/api/me/passkeys/options", headers=headers)
    challenge = base64url_to_bytes(options.json()["options"]["challenge"])
    repeated = await api_client.post(
        "/api/me/passkeys",
        headers=headers,
        json={"credential": device.register(challenge), "name": "Второй"},
    )

    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "link_conflict"


async def test_foreign_key_is_not_found(api_client: AsyncClient) -> None:
    """Чужой ключ не удаляется, и о его существовании не сообщается."""
    owner = await _sign_in(api_client)
    await _add_key(api_client, owner, _device())
    listed = await api_client.get("/api/me/passkeys", headers={"Authorization": f"Bearer {owner}"})
    stranger = await _sign_in(api_client, email="other@example.org")

    response = await api_client.delete(
        f"/api/me/passkeys/{listed.json()[0]['id']}",
        headers={"Authorization": f"Bearer {stranger}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_options_require_authentication(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/me/passkeys/options")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
