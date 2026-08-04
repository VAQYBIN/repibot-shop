"""Обход $ref должен собирать все зависимые схемы, иначе генерация упадёт."""

import json
from pathlib import Path

from tools.gen_remnawave_models import ROOT_SCHEMAS, collect_schemas


def test_collect_schemas_follows_nested_refs() -> None:
    schemas: dict[str, object] = {
        "Root": {"properties": {"child": {"$ref": "#/components/schemas/Child"}}},
        "Child": {"properties": {"leaf": {"$ref": "#/components/schemas/Leaf"}}},
        "Leaf": {"type": "string"},
        "Unrelated": {"type": "string"},
    }

    assert collect_schemas(schemas, ("Root",)) == {"Root", "Child", "Leaf"}


def test_collect_schemas_survives_cycles() -> None:
    schemas: dict[str, object] = {
        "A": {"properties": {"b": {"$ref": "#/components/schemas/B"}}},
        "B": {"properties": {"a": {"$ref": "#/components/schemas/A"}}},
    }

    assert collect_schemas(schemas, ("A",)) == {"A", "B"}


def test_declared_root_schemas_exist_in_panel_specification() -> None:
    """Опечатка в имени корневой схемы иначе проявится пустым файлом моделей."""
    root = Path(__file__).resolve().parents[3]
    document = json.loads(
        (root / "docs" / "remnawave-api" / "api-1.json").read_text(encoding="utf-8")
    )

    available = set(document["components"]["schemas"])
    assert set(ROOT_SCHEMAS) <= available


def test_generated_models_are_importable() -> None:
    """Генератор тянет типы вроде EmailStr, требующие отдельных зависимостей."""
    from repibot_core.integrations.remnawave import models

    for name in ROOT_SCHEMAS:
        assert hasattr(models, name), f"в моделях нет класса {name}"
