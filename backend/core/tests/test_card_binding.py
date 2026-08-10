"""Привязка карты без списания: доказательством остаётся состояние у провайдера."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    CardBinding,
    CardBindingStatus,
    Subscription,
    SubscriptionSource,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.yookassa.types import YooKassaBindingStatus, YooKassaCardBinding
from repibot_core.services.errors import ServiceError
from repibot_core.services.payment_methods import CardBindingService, PaymentMethodService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker


class FakeBindings:
    """Провайдер в памяти: карту запоминает он, а не наш запрос.

    Ключ идемпотентности учитывается всерьёз — повтор старта после потерянного
    ответа не должен порождать вторую привязку у провайдера.
    """

    def __init__(self) -> None:
        self._bindings: dict[str, YooKassaCardBinding] = {}
        self._keys: dict[str, str] = {}
        self.create_calls = 0

    async def create_card_binding(
        self, *, idempotence_key: str, return_url: str
    ) -> YooKassaCardBinding:
        self.create_calls += 1
        if idempotence_key in self._keys:
            return self._bindings[self._keys[idempotence_key]]
        binding_id = f"provider-binding-{len(self._bindings) + 1}"
        binding = YooKassaCardBinding(
            id=binding_id,
            status=YooKassaBindingStatus.pending,
            saved=False,
            title=None,
            confirmation_url=f"{return_url}?binding={binding_id}",
        )
        self._keys[idempotence_key] = binding_id
        self._bindings[binding_id] = binding
        return binding

    async def get_card_binding(self, binding_id: str) -> YooKassaCardBinding:
        return self._bindings[binding_id]

    def confirm(self, binding_id: str, *, status: YooKassaBindingStatus, saved: bool) -> None:
        self._bindings[binding_id] = replace(
            self._bindings[binding_id],
            status=status,
            saved=saved,
            title="Bank card *4444" if saved else None,
        )


async def _subscriber(session: AsyncSession, code: str) -> User:
    plan = await PlanRepository(session).create(
        code=f"plan-{code}",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("300.00"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=["11111111-1111-4111-8111-111111111111"],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    user = User(email=f"{code}@example.org", referral_code=code)
    session.add(user)
    await session.flush()
    session.add(
        Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionState.active,
            started_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=30),
            source=SubscriptionSource.purchase,
            entitlement_price_rub=plan.price_rub,
            entitlement_duration_days=plan.duration_days,
        )
    )
    await session.commit()
    return user


@pytest.fixture
def binding_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Магазину стенда привязка на нулевую сумму «подключена»."""
    monkeypatch.setattr(get_settings(), "yookassa_zero_amount_binding", True)


async def _provider_binding_id(session: AsyncSession, binding_id: int) -> str:
    provider_id = await session.scalar(
        select(CardBinding.provider_binding_id).where(CardBinding.id == binding_id)
    )
    assert provider_id is not None
    return str(provider_id)


async def _binding_status(session: AsyncSession, binding_id: int) -> CardBindingStatus:
    status = await session.scalar(select(CardBinding.status).where(CardBinding.id == binding_id))
    assert status is not None
    return status


async def _auto_renew(session: AsyncSession, user_id: int) -> bool:
    value = await session.scalar(
        select(Subscription.auto_renew_enabled).where(Subscription.user_id == user_id)
    )
    return bool(value)


async def test_binding_becomes_a_card_only_after_provider_confirms_saved(
    db_session: AsyncSession, binding_enabled: None
) -> None:
    """Возврат пользователя ничего не доказывает: состояние читается у провайдера."""
    user = await _subscriber(db_session, "binding1")
    provider = FakeBindings()
    bindings = CardBindingService(db_session)

    started = await bindings.start(user.id, provider)

    assert started.confirmation_url is not None
    assert await PaymentMethodService(db_session).current(user.id) is None
    assert await _binding_status(db_session, started.binding_id) is CardBindingStatus.pending

    provider.confirm(
        await _provider_binding_id(db_session, started.binding_id),
        status=YooKassaBindingStatus.active,
        saved=True,
    )

    assert await bindings.settle(started.binding_id, provider) is True
    current = await PaymentMethodService(db_session).current(user.id)
    assert current is not None and current.title == "Bank card *4444"
    assert await _binding_status(db_session, started.binding_id) is CardBindingStatus.active


async def test_inactive_binding_creates_no_card_and_is_marked_failed(
    db_session: AsyncSession, binding_enabled: None
) -> None:
    """Непройденная проверка карты не должна оставлять привязку вечно открытой."""
    user = await _subscriber(db_session, "binding2")
    provider = FakeBindings()
    bindings = CardBindingService(db_session)
    started = await bindings.start(user.id, provider)
    provider.confirm(
        await _provider_binding_id(db_session, started.binding_id),
        status=YooKassaBindingStatus.inactive,
        saved=False,
    )

    assert await bindings.settle(started.binding_id, provider) is False
    assert await PaymentMethodService(db_session).current(user.id) is None
    assert await _binding_status(db_session, started.binding_id) is CardBindingStatus.failed


async def test_settling_the_same_binding_twice_saves_one_card(
    db_session: AsyncSession, binding_enabled: None
) -> None:
    """Webhook и добор приходят оба: второй обязан быть безрезультатным."""
    user = await _subscriber(db_session, "binding3")
    provider = FakeBindings()
    bindings = CardBindingService(db_session)
    started = await bindings.start(user.id, provider)
    provider.confirm(
        await _provider_binding_id(db_session, started.binding_id),
        status=YooKassaBindingStatus.active,
        saved=True,
    )

    assert await bindings.settle(started.binding_id, provider) is True
    assert await bindings.settle(started.binding_id, provider) is False
    assert await bindings.settle_pending(provider) == 0


async def test_pending_binding_is_left_alone_until_the_provider_decides(
    db_session: AsyncSession, binding_enabled: None
) -> None:
    """Пока провайдер думает, привязку нельзя ни закрыть, ни признать картой."""
    user = await _subscriber(db_session, "binding4")
    provider = FakeBindings()
    bindings = CardBindingService(db_session)
    started = await bindings.start(user.id, provider)

    assert await bindings.settle(started.binding_id, provider) is False
    assert await _binding_status(db_session, started.binding_id) is CardBindingStatus.pending

    provider.confirm(
        await _provider_binding_id(db_session, started.binding_id),
        status=YooKassaBindingStatus.active,
        saved=True,
    )

    assert await bindings.settle_pending(provider) == 1


async def test_disabled_binding_is_refused_without_touching_the_provider(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Магазину без подключённой привязки провайдер ответил бы своей ошибкой."""
    monkeypatch.setattr(get_settings(), "yookassa_zero_amount_binding", False)
    user = await _subscriber(db_session, "binding5")
    provider = FakeBindings()

    with pytest.raises(ServiceError) as error:
        await CardBindingService(db_session).start(user.id, provider)

    assert error.value.code == "binding_unavailable"
    assert provider.create_calls == 0


async def test_confirmed_binding_turns_auto_renew_on(
    db_session: AsyncSession, binding_enabled: None
) -> None:
    """Привязка — то же согласие на повторные списания, что и галочка при оплате."""
    user = await _subscriber(db_session, "binding6")
    provider = FakeBindings()
    bindings = CardBindingService(db_session)
    started = await bindings.start(user.id, provider)
    assert await _auto_renew(db_session, user.id) is False

    provider.confirm(
        await _provider_binding_id(db_session, started.binding_id),
        status=YooKassaBindingStatus.active,
        saved=True,
    )
    await bindings.settle(started.binding_id, provider)

    assert await _auto_renew(db_session, user.id) is True
