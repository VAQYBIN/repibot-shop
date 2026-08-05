"""Сгенерированные файлы обязаны совпадать с результатом генерации.

Иначе типы фронтенда тихо расходятся с API, и ошибка вылезает у пользователя,
а не в сборке.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from tools.verify_generated import GENERATED, Generated, compare, verify_generated

ROOT = Path(__file__).resolve().parents[2]


def test_generated_files_are_declared() -> None:
    paths = {path for entry in GENERATED for path in entry.paths}

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


def _writer(target: Path, content: str) -> list[str]:
    """Команда, записывающая заданный текст, — подмена настоящего генератора."""
    code = (
        f"import pathlib; pathlib.Path({str(target)!r}).write_text({content!r}, encoding='utf-8')"
    )
    return [sys.executable, "-c", code]


def test_stale_file_keeps_its_committed_content(tmp_path: Path) -> None:
    """Проверка не должна подменять файл в рабочем дереве.

    Иначе `uv run check` молча перезаписывает исходники и оставляет за собой
    изменения, которых разработчик не делал.
    """
    target = tmp_path / "generated.txt"
    target.write_text("закоммиченное", encoding="utf-8")

    entry = Generated(
        paths=(target.relative_to(tmp_path),),
        command=_writer(target, "другое"),
        cwd=tmp_path,
    )

    assert verify_generated([entry], root=tmp_path) == [str(entry.paths[0])]
    assert target.read_text(encoding="utf-8") == "закоммиченное"


def test_up_to_date_file_is_reported_as_current(tmp_path: Path) -> None:
    target = tmp_path / "generated.txt"
    target.write_text("одно и то же", encoding="utf-8")

    entry = Generated(
        paths=(target.relative_to(tmp_path),),
        command=_writer(target, "одно и то же"),
        cwd=tmp_path,
    )

    assert verify_generated([entry], root=tmp_path) == []


def test_failed_generator_does_not_leave_the_file_damaged(tmp_path: Path) -> None:
    """Генератор мог успеть записать половину файла и упасть.

    Восстановление вне finally оставило бы закоммиченный файл затёртым —
    проверка испортила бы ровно то, что должна была защитить.
    """
    target = tmp_path / "generated.txt"
    target.write_text("закоммиченное", encoding="utf-8")

    code = (
        f"import pathlib; pathlib.Path({str(target)!r}).write_text('половина', encoding='utf-8');"
        " raise SystemExit(1)"
    )
    entry = Generated(
        paths=(Path("generated.txt"),), command=[sys.executable, "-c", code], cwd=tmp_path
    )

    with pytest.raises(subprocess.CalledProcessError):
        verify_generated([entry], root=tmp_path)

    assert target.read_text(encoding="utf-8") == "закоммиченное"


def test_missing_generator_is_reported_without_a_traceback(tmp_path: Path) -> None:
    """Нет pnpm — это сообщение, а не трассировка: в tools/check.py уже так."""
    entry = Generated(
        paths=(Path("generated.txt"),), command=["repibot-no-such-tool"], cwd=tmp_path
    )

    assert verify_generated([entry], root=tmp_path) == ["generated.txt"]


def test_absent_file_is_not_left_behind(tmp_path: Path) -> None:
    """Файла не было — после проверки его быть не должно."""
    target = tmp_path / "generated.txt"

    entry = Generated(
        paths=(target.relative_to(tmp_path),),
        command=_writer(target, "новое"),
        cwd=tmp_path,
    )

    assert verify_generated([entry], root=tmp_path) == [str(entry.paths[0])]
    assert not target.exists()


def test_one_command_can_own_several_files(tmp_path: Path) -> None:
    """Генератор бренда выдаёт тринадцать файлов за один запуск."""
    first = tmp_path / "one.txt"
    second = tmp_path / "two.txt"
    first.write_text("одно", encoding="utf-8")
    second.write_text("устарело", encoding="utf-8")

    code = (
        f"import pathlib;"
        f" pathlib.Path({str(first)!r}).write_text('одно', encoding='utf-8');"
        f" pathlib.Path({str(second)!r}).write_text('другое', encoding='utf-8')"
    )
    entry = Generated(
        paths=(Path("one.txt"), Path("two.txt")),
        command=[sys.executable, "-c", code],
        cwd=tmp_path,
    )

    assert verify_generated([entry], root=tmp_path) == ["two.txt"]
    assert second.read_text(encoding="utf-8") == "устарело"
