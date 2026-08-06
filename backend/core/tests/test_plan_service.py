"""Тарифы: проверка сквадов, видимость, архивация."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import TrafficResetStrategy
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.services.errors import ServiceError
from repibot_core.services.plans import PlanInput, PlanService
from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


def _input(code: str, **overrides: object) -> PlanInput:
    # Аннотация обязательна: без неё mypy выводит union из типов значений, и
    # update словарём с overrides: dict[str, object] уже не проходит.
    data: dict[str, object] = {
        "code": code,
        "name": {"ru": "Месяц", "en": "Month"},
        "description": None,
        "duration_days": 30,
        "price_rub": Decimal("299.00"),
        "price_stars": 199,
        "traffic_limit_bytes": 0,
        "traffic_reset_strategy": TrafficResetStrategy.NO_RESET,
        "hwid_device_limit": 3,
        "internal_squad_uuids": [SQUAD],
        "is_trial": False,
        "is_visible": True,
        "sort_order": 0,
    }
    data.update(overrides)
    return PlanInput(**data)  # type: ignore[arg-type]


def _service(session: AsyncSession, panel: FakePanel) -> PlanService:
    return PlanService(session, PanelSquads(panel.client()))


async def test_plan_with_unknown_squad_is_rejected(db_session: AsyncSession) -> None:
    """Тариф со сквадом, которого нет в панели, продаётся и не работает."""
    panel = FakePanel()
    with pytest.raises(ServiceError) as error:
        await _service(db_session, panel).create(_input("month"))
    assert error.value.code == "plan_squads_unknown"


async def test_created_plan_is_visible(db_session: AsyncSession) -> None:
    panel = FakePanel()
    panel.add_squad(SQUAD, "Европа")
    service = _service(db_session, panel)

    created = await service.create(_input("month"))

    assert created.id > 0
    assert [plan.code for plan in await service.visible()] == ["month"]


async def test_duplicate_code_is_rejected(db_session: AsyncSession) -> None:
    panel = FakePanel()
    panel.add_squad(SQUAD, "Европа")
    service = _service(db_session, panel)
    await service.create(_input("month"))

    with pytest.raises(ServiceError) as error:
        await service.create(_input("month"))
    assert error.value.code == "plan_code_taken"


async def test_archived_plan_leaves_visible_list(db_session: AsyncSession) -> None:
    panel = FakePanel()
    panel.add_squad(SQUAD, "Европа")
    service = _service(db_session, panel)
    created = await service.create(_input("month"))

    await service.archive(created.id)

    assert await service.visible() == []
    assert [plan.code for plan in await service.all()] == ["month"]


async def test_missing_plan_reports_not_found(db_session: AsyncSession) -> None:
    panel = FakePanel()
    with pytest.raises(ServiceError) as error:
        await _service(db_session, panel).require(404)
    assert error.value.code == "plan_not_found"
