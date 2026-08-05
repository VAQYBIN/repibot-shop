"""Инварианты развёртывания. Проверяются разбором compose.yml.

Ошибки в этом файле дают самые дорогие отказы: миграции наперегонки,
сервис без ограничения перезапуска, секрет, попавший в репозиторий.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((ROOT / "compose.yml").read_text(encoding="utf-8"))
    return loaded


def test_all_expected_services_are_declared(compose: dict[str, Any]) -> None:
    expected = {
        "nginx",
        "web",
        "api",
        "bot",
        "worker",
        "scheduler",
        "migrate",
        "postgres",
        "valkey",
    }

    assert expected <= set(compose["services"])


def test_application_services_wait_for_migrations(compose: dict[str, Any]) -> None:
    """Три процесса, стартующие одновременно, иначе дерутся за блокировку Alembic."""
    for service in ("api", "bot", "worker"):
        depends = compose["services"][service]["depends_on"]
        assert depends["migrate"]["condition"] == "service_completed_successfully"


def test_migrate_waits_for_healthy_database(compose: dict[str, Any]) -> None:
    depends = compose["services"]["migrate"]["depends_on"]

    assert depends["postgres"]["condition"] == "service_healthy"


def test_database_and_cache_have_healthchecks(compose: dict[str, Any]) -> None:
    for service in ("postgres", "valkey"):
        assert "healthcheck" in compose["services"][service]


def test_postgres_volume_uses_versioned_layout(compose: dict[str, Any]) -> None:
    """Образ 18+ отказывается стартовать, если том смонтирован в .../data."""
    mounts = compose["services"]["postgres"]["volumes"]

    assert "postgres-data:/var/lib/postgresql" in mounts


def test_migrate_does_not_restart(compose: dict[str, Any]) -> None:
    """Одноразовый сервис с restart: always уходит в вечный цикл."""
    assert compose["services"]["migrate"].get("restart", "no") == "no"


def test_only_nginx_publishes_ports(compose: dict[str, Any]) -> None:
    """Открытый наружу порт базы — самый частый способ потерять данные.

    Инвариант проверяется на рабочем наборе. Сервисы с профилем `dev` (Mailpit
    для писем в разработке) обычным `docker compose up` не поднимаются, и их
    порты на сервере не появляются.
    """
    with_ports = {
        name
        for name, service in compose["services"].items()
        if service.get("ports") and not service.get("profiles")
    }

    assert with_ports == {"nginx"}


def test_dev_only_services_are_behind_a_profile(compose: dict[str, Any]) -> None:
    """Mailpit принимает почту без пароля — на сервере ему делать нечего.

    Забыть профиль здесь означает открыть наружу чужую переписку, поэтому
    проверяется именно он, а не наличие сервиса.
    """
    mailpit = compose["services"]["mailpit"]

    assert mailpit.get("profiles") == ["dev"]


def test_frontend_service_does_not_receive_backend_secrets(compose: dict[str, Any]) -> None:
    """Веб-приложению нужна разметка, а не токен бота и ключ подписи.

    Подключение общего .env выглядит безобидно и кладёт все секреты в процесс,
    который их не использует, — лишняя поверхность на ровном месте.
    """
    web = compose["services"]["web"]

    assert "env_file" not in web
    assert "environment" not in web


def test_no_literal_secrets_in_compose() -> None:
    text = (ROOT / "compose.yml").read_text(encoding="utf-8")

    for marker in ("password:", "secret:", "token:"):
        for line in text.splitlines():
            if marker in line.lower() and "${" not in line:
                pytest.fail(f"похоже на секрет в открытом виде: {line.strip()}")


def test_env_example_covers_every_variable_used_in_compose() -> None:
    """Переменная, которой нет в .env.example, обнаружится только на чужом сервере."""
    compose_text = (ROOT / "compose.yml").read_text(encoding="utf-8")
    used = set(re.findall(r"\$\{([A-Z0-9_]+)", compose_text))
    documented = {
        line.split("=", 1)[0].strip()
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#") and "=" in line
    }

    assert used <= documented, f"не описаны в .env.example: {sorted(used - documented)}"
