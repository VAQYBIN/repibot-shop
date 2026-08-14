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
    """Файлы под контролем генерации и команда, которая их создаёт.

    Одна команда может выдавать несколько файлов: сборка бренда пишет
    пятнадцать за раз, и запускать её пятнадцать раз было бы расточительно.
    """

    paths: tuple[Path, ...]
    command: list[str]
    cwd: Path


GENERATED: list[Generated] = [
    Generated(
        paths=(Path("frontend/packages/core/src/api/openapi.json"),),
        command=["uv", "run", "export-openapi"],
        cwd=ROOT,
    ),
    Generated(
        paths=(Path("frontend/packages/core/src/api/schema.d.ts"),),
        command=["pnpm", "--filter", "@repibot/core", "gen:api"],
        cwd=ROOT / "frontend",
    ),
    Generated(
        paths=(Path("backend/core/src/repibot_core/integrations/remnawave/models.py"),),
        command=["uv", "run", "python", "tools/gen_remnawave_models.py"],
        cwd=ROOT,
    ),
    Generated(
        paths=(Path("tools/brand/wordmark_paths.py"),),
        command=["uv", "run", "python", "tools/brand/wordmark_source.py"],
        cwd=ROOT,
    ),
    Generated(
        paths=(
            Path("docs/design/logo/logo-mark.svg"),
            Path("docs/design/logo/logo-mark-mono.svg"),
            Path("docs/design/logo/logo-mark-small.svg"),
            Path("docs/design/logo/wordmark.svg"),
            Path("docs/design/logo/logo-lockup-h.svg"),
            Path("docs/design/logo/logo-lockup-v.svg"),
            Path("docs/design/logo/badge.svg"),
            Path("docs/design/logo/badge-inverse.svg"),
            Path("docs/design/logo/favicon.svg"),
            Path("docs/design/logo/avatar.svg"),
            Path("docs/design/logo/og-image.svg"),
            Path("docs/design/logo/banner.svg"),
            Path("docs/design/logo/banner-light.svg"),
            Path("frontend/apps/web/public/favicon.svg"),
            Path("frontend/apps/miniapp/public/favicon.svg"),
        ),
        command=["uv", "run", "build-brand"],
        cwd=ROOT,
    ),
]


def _normalise(text: str) -> str:
    return text.replace("\r\n", "\n")


def compare(path: Path, expected: str) -> bool:
    """Сравнивает содержимое файла, не придираясь к переводам строк."""
    if not path.exists():
        return False
    return _normalise(path.read_text(encoding="utf-8")) == _normalise(expected)


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
        targets = [root / path for path in entry.paths]
        before = [target.read_bytes() if target.exists() else None for target in targets]

        produced: list[bytes | None] = []
        try:
            subprocess.run(_resolve(entry.command), cwd=entry.cwd, check=True)  # noqa: S603
        except FileNotFoundError:
            # Нет pnpm или uv — это сообщение, а не трассировка.
            print(f"команда не найдена: {entry.command[0]}", flush=True)  # noqa: T201
            stale.extend(str(path) for path in entry.paths)
            continue
        finally:
            # Снимок и восстановление именно в finally: упавший генератор мог
            # успеть записать половину файла, и без восстановления проверка
            # испортила бы ровно то, что должна была защитить.
            for target, original in zip(targets, before, strict=True):
                produced.append(target.read_bytes() if target.exists() else None)
                if original is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(original)

        for path, original, current in zip(entry.paths, before, produced, strict=True):
            if current is None or _normalise(current.decode("utf-8")) != _normalise(
                (original or b"").decode("utf-8")
            ):
                stale.append(str(path))
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
