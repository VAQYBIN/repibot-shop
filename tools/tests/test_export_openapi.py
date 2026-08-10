"""The schema exporter must not depend on deployment secrets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repibot_core.settings import Settings, get_settings
from tools import export_openapi


def test_export_openapi_supplies_required_settings_without_deployment_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Removing the assertion placeholder must make this real export fail."""
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    monkeypatch.setattr(export_openapi, "ROOT", tmp_path)
    monkeypatch.setattr(export_openapi, "TARGET", tmp_path / "openapi.json")
    get_settings.cache_clear()

    try:
        assert export_openapi.main() == 0
        schema = json.loads(export_openapi.TARGET.read_text(encoding="utf-8"))
        assert schema["info"]["title"] == "Re:Pibot Shop API"
    finally:
        get_settings.cache_clear()
