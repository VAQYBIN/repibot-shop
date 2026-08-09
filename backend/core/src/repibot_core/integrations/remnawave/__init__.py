"""Панель Remnawave: HTTP-клиент, фасады и сгенерированные модели её схемы."""

from repibot_core.integrations.remnawave.client import (
    RemnawaveClient,
    RemnawaveError,
    RemnawaveRejected,
    RemnawaveUnavailable,
    create_remnawave_client,
)
from repibot_core.integrations.remnawave.devices import PanelDevices
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.integrations.remnawave.stats import PanelStats
from repibot_core.integrations.remnawave.users import PanelUsers

__all__ = [
    "PanelDevices",
    "PanelSquads",
    "PanelStats",
    "PanelUsers",
    "RemnawaveClient",
    "RemnawaveError",
    "RemnawaveRejected",
    "RemnawaveUnavailable",
    "create_remnawave_client",
]
