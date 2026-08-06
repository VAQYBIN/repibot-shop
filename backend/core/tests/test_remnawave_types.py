"""Псевдонимы типов панели переживают перегенерацию моделей."""

from __future__ import annotations

from typing import get_args

from repibot_core.integrations.remnawave.types import (
    PanelDevice,
    PanelSquad,
    PanelUsage,
    PanelUser,
)


def test_panel_user_has_identity_fields() -> None:
    """Сдвиг нумерации сгенерированных классов не должен пройти молча."""
    assert {"id", "shortUuid", "username", "expireAt", "subscriptionUrl"} <= set(
        PanelUser.model_fields
    )


def test_nullable_fields_allow_none() -> None:
    """Панель присылает null в этих полях; обязательными они быть не могут."""
    # get_args, а не __args__: аннотация поля объявлена как «тип или None»,
    # и обращение к атрибуту напрямую не проходит mypy в strict.
    for name in ("telegramId", "email", "tag", "hwidDeviceLimit"):
        assert type(None) in get_args(PanelUser.model_fields[name].annotation)


def test_panel_squad_has_uuid_and_name() -> None:
    assert {"uuid", "name"} <= set(PanelSquad.model_fields)


def test_panel_device_has_hwid_and_platform() -> None:
    """Псевдоним устройства должен пережить перенумерацию классов."""
    assert {"hwid", "userId", "platform", "deviceModel", "createdAt"} <= set(
        PanelDevice.model_fields
    )


def test_panel_usage_has_categories_and_series() -> None:
    assert {"categories", "series"} <= set(PanelUsage.model_fields)
