"""Сохранённая карта принадлежит своему владельцу и управляет автоплатежом."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import Subscription
from repibot_core.integrations.yookassa.types import YooKassaBindingStatus, YooKassaCardBinding
from repibot_core.services.payment_methods import PaymentMethodService


class FakeBindingProvider:
    """Узкая заглушка: проверяем контракт маршрута, а не транспорт."""

    def __init__(self) -> None:
        self.calls = 0

    async def create_card_binding(
        self, *, idempotence_key: str, return_url: str
    ) -> YooKassaCardBinding:
        del idempotence_key
        self.calls += 1
        return YooKassaCardBinding(
            id="binding-1",
            status=YooKassaBindingStatus.pending,
            saved=False,
            title=None,
            confirmation_url=f"{return_url}?binding=binding-1",
        )

    async def get_card_binding(self, binding_id: str) -> YooKassaCardBinding:
        """Провайдер ещё не решил: пользователь не дошёл до формы."""
        return YooKassaCardBinding(
            id=binding_id,
            status=YooKassaBindingStatus.pending,
            saved=False,
            title=None,
            confirmation_url=None,
        )

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_binding_provider(monkeypatch: pytest.MonkeyPatch) -> FakeBindingProvider:
    from repibot_api import subscription_view

    fake = FakeBindingProvider()
    monkeypatch.setattr(subscription_view, "create_yookassa_client", lambda: fake, raising=False)
    return fake


async def _link_card(engine: AsyncEngine, user_id: int) -> None:
    async with create_session_factory(engine)() as session:
        await PaymentMethodService(session).save(
            user_id, provider_method_id="method-1", title="Bank card *4444"
        )
        await session.commit()


async def _auto_renew(engine: AsyncEngine, user_id: int) -> bool:
    """Флаг читается из базы: эндпоинт настройки требует активной подписки."""
    async with create_session_factory(engine)() as session:
        value = await session.scalar(
            select(Subscription.auto_renew_enabled).where(Subscription.user_id == user_id)
        )
    return bool(value)


async def _user_id(api_client: AsyncClient, headers: dict[str, str]) -> int:
    response = await api_client.get("/api/me", headers=headers)
    assert response.status_code == 200
    return int(response.json()["id"])


async def test_absent_card_is_reported_without_inventing_a_title(
    api_client: AsyncClient, user_headers: dict[str, str]
) -> None:
    """Клиент не должен придумывать название карты сам."""
    response = await api_client.get("/api/me/payment-method", headers=user_headers)

    assert response.status_code == 200
    assert response.json() == {"title": None, "linked_at": None, "binding_available": False}


async def test_linked_card_is_shown_with_the_provider_title(
    api_client: AsyncClient, user_headers: dict[str, str], engine: AsyncEngine
) -> None:
    await _link_card(engine, await _user_id(api_client, user_headers))

    response = await api_client.get("/api/me/payment-method", headers=user_headers)

    body = response.json()
    assert body["title"] == "Bank card *4444"
    assert body["linked_at"] is not None


async def test_unlinking_a_card_turns_auto_renew_off(
    api_client: AsyncClient,
    telegram_user_headers: dict[str, str],
    trial_subscriber: str,
    engine: AsyncEngine,
) -> None:
    """Автоплатёж без карты обещал бы списание, которого не будет."""
    del trial_subscriber
    headers = telegram_user_headers
    user_id = await _user_id(api_client, headers)
    await _link_card(engine, user_id)
    assert await _auto_renew(engine, user_id) is True

    removed = await api_client.delete("/api/me/payment-method", headers=headers)

    assert removed.status_code == 204
    assert (await api_client.get("/api/me/payment-method", headers=headers)).json()["title"] is None
    assert await _auto_renew(engine, user_id) is False


async def test_unlinking_twice_is_not_an_error(
    api_client: AsyncClient, user_headers: dict[str, str]
) -> None:
    """У отсутствия карты и её удаления один наблюдаемый итог."""
    first = await api_client.delete("/api/me/payment-method", headers=user_headers)
    second = await api_client.delete("/api/me/payment-method", headers=user_headers)

    assert (first.status_code, second.status_code) == (204, 204)


async def test_card_routes_require_authentication(api_client: AsyncClient) -> None:
    """Без этого чужую карту было бы видно и можно было бы отвязать."""
    shown = await api_client.get("/api/me/payment-method")
    removed = await api_client.delete("/api/me/payment-method")
    started = await api_client.post("/api/me/payment-method/bindings")

    assert (shown.status_code, removed.status_code, started.status_code) == (401, 401, 401)


async def test_binding_is_refused_until_the_shop_gets_it(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    fake_binding_provider: FakeBindingProvider,
) -> None:
    """Провайдер ответил бы своей ошибкой; отказ должен быть нашим и стабильным."""
    response = await api_client.post(
        "/api/me/payment-method/bindings",
        json={"return_surface": "web"},
        headers=user_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "binding_unavailable"
    assert fake_binding_provider.calls == 0


async def test_enabled_binding_returns_the_provider_confirmation_url(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    fake_binding_provider: FakeBindingProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from repibot_core.settings import get_settings

    monkeypatch.setattr(get_settings(), "yookassa_zero_amount_binding", True)

    response = await api_client.post(
        "/api/me/payment-method/bindings",
        json={"return_surface": "web"},
        headers=user_headers,
    )

    assert response.status_code == 201
    assert response.json()["confirmation_url"].endswith("?binding=binding-1")
    assert fake_binding_provider.calls == 1
    # Карта появляется только после подтверждения провайдером, не в этот момент.
    assert (await api_client.get("/api/me/payment-method", headers=user_headers)).json()[
        "title"
    ] is None


async def test_card_screen_settles_a_binding_left_pending_by_the_provider(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """После формы провайдера человек попадает сюда — и карта должна быть уже видна.

    Ждать сверки по расписанию значит показать «карта не привязана» сразу
    после успешной привязки и получить вторую попытку от растерянного
    пользователя.
    """
    from repibot_api import subscription_view
    from repibot_core.db.models import CardBinding, CardBindingStatus, PaymentProvider
    from repibot_core.settings import get_settings

    monkeypatch.setattr(get_settings(), "yookassa_zero_amount_binding", True)
    user_id = await _user_id(api_client, user_headers)
    async with create_session_factory(engine)() as session:
        session.add(
            CardBinding(
                user_id=user_id,
                provider=PaymentProvider.yookassa,
                provider_binding_id="binding-1",
                status=CardBindingStatus.pending,
            )
        )
        await session.commit()

    class SettlingProvider(FakeBindingProvider):
        async def get_card_binding(self, binding_id: str) -> YooKassaCardBinding:
            assert binding_id == "binding-1"
            return YooKassaCardBinding(
                id=binding_id,
                status=YooKassaBindingStatus.active,
                saved=True,
                title="Bank card *4444",
                confirmation_url=None,
            )

    monkeypatch.setattr(
        subscription_view, "create_yookassa_client", SettlingProvider, raising=False
    )

    response = await api_client.get("/api/me/payment-method", headers=user_headers)

    assert response.json()["title"] == "Bank card *4444"
