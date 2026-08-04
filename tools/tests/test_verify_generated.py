"""Сгенерированные файлы обязаны совпадать с результатом генерации.

Иначе типы фронтенда тихо расходятся с API, и ошибка вылезает у пользователя,
а не в сборке.
"""

from pathlib import Path

from tools.verify_generated import GENERATED, compare

ROOT = Path(__file__).resolve().parents[2]


def test_generated_files_are_declared() -> None:
    paths = {entry.path for entry in GENERATED}

    assert Path("frontend/packages/core/src/api/openapi.json") in paths
    assert Path("frontend/packages/core/src/api/schema.d.ts") in paths
    assert Path("backend/core/src/repibot_core/integrations/remnawave/models.py") in paths


def test_compare_detects_difference(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("было", encoding="utf-8")

    assert compare(target, "стало") is False


def test_compare_ignores_line_endings(tmp_path: Path) -> None:
    """Windows и Linux иначе расходились бы на каждом файле."""
    target = tmp_path / "file.txt"
    target.write_bytes(b"\xd1\x81\xd1\x82\xd1\x80\xd0\xbe\xd0\xba\xd0\xb0\r\n")

    assert compare(target, "строка\n") is True


def test_compare_reports_missing_file_as_difference(tmp_path: Path) -> None:
    assert compare(tmp_path / "нет-такого", "что угодно") is False
