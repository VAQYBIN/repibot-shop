"""Проверка синхронности сгенерированных файлов.

Генераторы умеют писать только по своим путям, поэтому проверка запускает их
как есть, сравнивает результат с закоммиченным и возвращает файлу прежнее
содержимое. Рабочее дерево после проверки остаётся таким же, каким было:
устаревший файл чинит разработчик запуском генератора, а не проверка молча.

Расхождение означает, что кто-то поменял источник и забыл перегенерировать
результат.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Generated:
    """Файл под контролем генерации и команда, которая его создаёт."""

    path: Path
    command: list[str]
    cwd: Path


GENERATED: list[Generated] = [
    Generated(
        path=Path("frontend/packages/core/src/api/openapi.json"),
        command=["uv", "run", "export-openapi"],
        cwd=ROOT,
    ),
    Generated(
        path=Path("frontend/packages/core/src/api/schema.d.ts"),
        command=["pnpm", "--filter", "@repibot/core", "gen:api"],
        cwd=ROOT / "frontend",
    ),
    Generated(
        path=Path("backend/core/src/repibot_core/integrations/remnawave/models.py"),
        command=["uv", "run", "python", "tools/gen_remnawave_models.py"],
        cwd=ROOT,
    ),
]


def compare(path: Path, expected: str) -> bool:
    """Сравнивает содержимое файла, не придираясь к переводам строк."""
    if not path.exists():
        return False
    actual = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return actual == expected.replace("\r\n", "\n")


def _resolve(command: list[str]) -> list[str]:
    """Windows не запускает pnpm без расширения — ищем реальный исполняемый файл."""
    executable = shutil.which(command[0])
    if executable is None:
        return command
    return [executable, *command[1:]]


def verify_generated(entries: list[Generated] | None = None, root: Path = ROOT) -> list[str]:
    """Перегенерирует файлы и возвращает пути тех, что разошлись.

    Исходное содержимое восстанавливается в любом случае: проверка сообщает
    о расхождении, но не правит рабочее дерево за разработчика.
    """
    stale: list[str] = []
    for entry in entries if entries is not None else GENERATED:
        target = root / entry.path
        existed = target.exists()
        before = target.read_bytes() if existed else b""

        subprocess.run(_resolve(entry.command), cwd=entry.cwd, check=True)  # noqa: S603

        if not compare(target, before.decode("utf-8")):
            stale.append(str(entry.path))

        if existed:
            target.write_bytes(before)
        else:
            target.unlink(missing_ok=True)
    return stale


def main() -> int:
    stale = verify_generated()
    if stale:
        print("Сгенерированные файлы устарели:")  # noqa: T201
        for path in stale:
            print(f"  {path}")  # noqa: T201
        print("Перегенерируйте их и закоммитьте результат.")  # noqa: T201
        return 1
    print("Сгенерированные файлы актуальны.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
