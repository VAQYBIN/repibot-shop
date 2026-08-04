"""Единая команда проверки.

Один и тот же вход локально и в CI. Реализована на Python, а не Makefile:
основная машина разработки под Windows, где make не установлен, CI — под Linux.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Check:
    """Одна проверка: как её зовут, что запустить и в какой директории."""

    name: str
    command: list[str]
    cwd: Path


CHECKS: list[Check] = [
    Check(name="ruff-lint", command=["uv", "run", "ruff", "check", "."], cwd=ROOT),
    Check(name="ruff-format", command=["uv", "run", "ruff", "format", "--check", "."], cwd=ROOT),
    Check(name="mypy", command=["uv", "run", "mypy"], cwd=ROOT),
    Check(name="pytest", command=["uv", "run", "pytest", "-q"], cwd=ROOT),
]


def run_checks(checks: list[Check]) -> list[str]:
    """Выполняет все проверки и возвращает имена упавших.

    Ни одна упавшая проверка не прерывает остальные: разработчик должен увидеть
    весь список проблем за один прогон, а не чинить их по одной.
    """
    failed: list[str] = []
    for check in checks:
        print(f"\n=== {check.name} ===", flush=True)  # noqa: T201
        try:
            result = subprocess.run(check.command, cwd=check.cwd, check=False)  # noqa: S603
        except FileNotFoundError:
            print(f"команда не найдена: {check.command[0]}", flush=True)  # noqa: T201
            failed.append(check.name)
            continue
        if result.returncode != 0:
            failed.append(check.name)
    return failed


def main() -> int:
    failed = run_checks(CHECKS)
    if failed:
        print(f"\nПровалено: {', '.join(failed)}", flush=True)  # noqa: T201
        return 1
    print("\nВсе проверки пройдены.", flush=True)  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
