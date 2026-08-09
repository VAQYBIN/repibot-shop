"""Заглушка должна вести себя как панель, иначе тесты сервисов ничего не значат."""

from __future__ import annotations

import pytest

from repibot_core.integrations.remnawave.client import RemnawaveUnavailable
from repibot_core.integrations.remnawave.types import CreateUserBody, UpdateUserBody
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.testing.remnawave import FakePanel


async def test_created_user_gets_numeric_id_and_subscription_url() -> None:
    panel = FakePanel()
    users = PanelUsers(panel.client())

    created = await users.create(
        CreateUserBody(username="rp_1", expireAt="2026-09-06T12:00:00Z", tag="REPIBOT")
    )

    assert isinstance(created.id, float | int)
    assert created.subscriptionUrl.endswith(created.shortUuid)
    assert created.tag == "REPIBOT"


async def test_resolve_finds_by_username_and_misses_unknown() -> None:
    panel = FakePanel()
    users = PanelUsers(panel.client())
    await users.create(CreateUserBody(username="rp_1", expireAt="2026-09-06T12:00:00Z"))

    assert await users.resolve(username="rp_1") is not None
    assert await users.resolve(username="rp_2") is None


async def test_update_changes_only_given_fields() -> None:
    panel = FakePanel()
    users = PanelUsers(panel.client())
    created = await users.create(
        CreateUserBody(username="rp_1", expireAt="2026-09-06T12:00:00Z", hwidDeviceLimit=3)
    )

    updated = await users.update(UpdateUserBody(id=int(created.id), hwidDeviceLimit=5))

    assert updated.hwidDeviceLimit == 5
    assert updated.username == "rp_1"


async def test_fail_next_makes_panel_unavailable() -> None:
    """Сценарий «панель лежит» нужен тестам провижининга."""
    panel = FakePanel()
    panel.fail_next(times=10)

    with pytest.raises(RemnawaveUnavailable):
        await PanelUsers(panel.client()).get(1)
