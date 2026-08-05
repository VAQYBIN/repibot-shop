"""Проверка того, что сама команда проверки честно сообщает об ошибках."""

from pathlib import Path

from tools.check import Check, run_checks

ROOT = Path(__file__).resolve().parents[2]


def test_run_checks_returns_empty_list_when_all_pass() -> None:
    checks = [Check(name="ok", command=["python", "-c", "pass"], cwd=ROOT)]

    assert run_checks(checks) == []


def test_run_checks_returns_names_of_failed_checks() -> None:
    checks = [
        Check(name="ok", command=["python", "-c", "pass"], cwd=ROOT),
        Check(name="плохая", command=["python", "-c", "raise SystemExit(1)"], cwd=ROOT),
    ]

    assert run_checks(checks) == ["плохая"]


def test_run_checks_does_not_stop_at_first_failure() -> None:
    """Одна упавшая проверка не должна скрывать остальные — иначе чинить придётся по одной."""
    checks = [
        Check(name="первая", command=["python", "-c", "raise SystemExit(1)"], cwd=ROOT),
        Check(name="вторая", command=["python", "-c", "raise SystemExit(1)"], cwd=ROOT),
    ]

    assert run_checks(checks) == ["первая", "вторая"]


def test_missing_executable_is_reported_as_failure() -> None:
    checks = [Check(name="нет-такой-команды", command=["repibot-no-such-tool"], cwd=ROOT)]

    assert run_checks(checks) == ["нет-такой-команды"]


def test_checks_cover_backend_and_frontend() -> None:
    """Проверка, которой нет в списке, не выполняется ни локально, ни в CI."""
    from tools.check import CHECKS

    names = {check.name for check in CHECKS}

    assert {"ruff-lint", "ruff-format", "mypy", "pytest"} <= names
    assert {"biome", "typecheck", "vitest"} <= names


def test_frontend_checks_run_in_frontend_directory() -> None:
    from tools.check import CHECKS
    from tools.check import ROOT as CHECK_ROOT

    frontend_checks = [c for c in CHECKS if c.name in {"biome", "typecheck", "vitest"}]

    assert frontend_checks
    for check in frontend_checks:
        assert check.cwd == CHECK_ROOT / "frontend"
