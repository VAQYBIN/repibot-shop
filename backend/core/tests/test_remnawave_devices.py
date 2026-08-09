"""Фасады устройств и трафика: адреса, тела запросов, разбор ответов."""

from __future__ import annotations

from datetime import date

import pytest

from repibot_core.integrations.remnawave.client import RemnawaveRejected
from repibot_core.integrations.remnawave.devices import PanelDevices
from repibot_core.integrations.remnawave.stats import PanelStats
from repibot_core.testing.remnawave import FakePanel


async def test_devices_are_listed_for_user() -> None:
    panel = FakePanel()
    panel.add_device(7, "hwid-1", platform="iOS", device_model="iPhone 15")
    panel.add_device(7, "hwid-2", platform="Android", device_model=None)
    panel.add_device(9, "чужое", platform="Windows", device_model=None)

    devices = await PanelDevices(panel.client()).list(7)

    assert [device.hwid for device in devices] == ["hwid-1", "hwid-2"]
    assert devices[1].deviceModel is None


async def test_unknown_user_has_no_devices() -> None:
    """Пустой список, а не отказ: у нового пользователя устройств просто нет."""
    assert await PanelDevices(FakePanel().client()).list(404) == []


async def test_delete_sends_user_and_hwid_in_body() -> None:
    panel = FakePanel()
    panel.add_device(7, "hwid-1")

    await PanelDevices(panel.client()).delete(7, "hwid-1")

    assert panel.devices[7] == []
    assert ("POST", "/api/hwid/devices/delete") in panel.requests


async def test_delete_of_missing_device_is_rejected() -> None:
    """Панель отвечает отказом, и глушить его нельзя: сервис отличает чужой hwid."""
    panel = FakePanel()
    with pytest.raises(RemnawaveRejected):
        await PanelDevices(panel.client()).delete(7, "нет-такого")


async def test_usage_asks_for_the_given_range() -> None:
    panel = FakePanel()
    panel.add_usage(7, "2026-08-05", 1024)
    panel.add_usage(7, "2026-08-06", 2048)

    usage = await PanelStats(panel.client()).usage(7, start=date(2026, 8, 1), end=date(2026, 8, 6))

    assert usage.categories == ["2026-08-05", "2026-08-06"]
    assert [point for series in usage.series for point in series.data] == [1024, 2048]
    method, path = panel.requests[-1]
    assert method == "GET"
    assert path == "/api/bandwidth-stats/users/7"
    assert panel.last_query == {"start": "2026-08-01", "end": "2026-08-06"}
