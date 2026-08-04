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
