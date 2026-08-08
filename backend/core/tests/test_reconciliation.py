"""Сверка: расхождение записывается, чужой тег не правится."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import FindingAction, SubscriptionSource, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.reconciliation import FindingRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.provisioning import ProvisioningService
from repibot_core.services.reconciliation import ReconciliationService
from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker

RUN = "0f6a1c2e-0000-4000-8000-000000000001"


async def _subscriber(db_session: AsyncSession) -> User:
    plan = await PlanRepository(db_session).create(
        code="month",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
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
    user = User(email="r@example.org", referral_code="rec00001")
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(UTC)
    await SubscriptionRepository(db_session).create(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.active,
        started_at=now,
        expires_at=now + timedelta(days=30),
        source=SubscriptionSource.purchase,
    )
    await db_session.commit()
    return user


async def test_run_without_differences_writes_nothing(db_session: AsyncSession) -> None:
    """Сошлось — писать нечего. Отчёт не должен превращаться в шум."""
    user = await _subscriber(db_session)
    panel = FakePanel()
    provisioning = ProvisioningService(db_session, PanelUsers(panel.client()))
    await provisioning.reconcile(user.id)

    written = await ReconciliationService(db_session, provisioning).run(run_id=RUN)

    assert written == 0
    assert await FindingRepository(db_session).latest_run() == []


async def test_manual_change_in_panel_is_recorded_and_fixed(db_session: AsyncSession) -> None:
    """Расхождение обычно значит ручную правку админа — о ней надо знать."""
    user = await _subscriber(db_session)
    panel = FakePanel()
    provisioning = ProvisioningService(db_session, PanelUsers(panel.client()))
    state = await provisioning.reconcile(user.id)
    panel.users[state.panel_id]["hwidDeviceLimit"] = 99

    written = await ReconciliationService(db_session, provisioning).run(run_id=RUN)

    findings = await FindingRepository(db_session).latest_run()
    assert written == len(findings) >= 1
    limit_finding = next(row for row in findings if row.field == "hwidDeviceLimit")
    assert limit_finding.action is FindingAction.fixed
    assert limit_finding.theirs == "99"
    assert panel.users[state.panel_id]["hwidDeviceLimit"] == 3


async def test_foreign_tag_is_skipped_not_overwritten(db_session: AsyncSession) -> None:
    """Пользователя панели, заведённого мимо нас, автоматика не трогает."""
    user = await _subscriber(db_session)
    panel = FakePanel()
    provisioning = ProvisioningService(db_session, PanelUsers(panel.client()))
    state = await provisioning.reconcile(user.id)
    panel.users[state.panel_id]["tag"] = "РУЧНОЙ"
    panel.users[state.panel_id]["hwidDeviceLimit"] = 99

    await ReconciliationService(db_session, provisioning).run(run_id=RUN)

    findings = await FindingRepository(db_session).latest_run()
    assert [row.action for row in findings] == [FindingAction.skipped]
    assert panel.users[state.panel_id]["hwidDeviceLimit"] == 99
