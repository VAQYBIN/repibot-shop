# Подпроект 0 «Фундамент» — план реализации

> **Для агентов:** ОБЯЗАТЕЛЬНЫЙ ПОД-СКИЛЛ: используйте superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans для выполнения задача-за-задачей. Шаги размечены чекбоксами (`- [ ]`).

**Цель:** собрать каркас, на котором `docker compose up` поднимает работающий стек из девяти сервисов, а `uv run check` проходит все проверки — без единой бизнес-функции.

**Архитектура:** бэкенд — uv workspace из четырёх пакетов: `repibot-core` с бизнес-логикой и три тонкие точки входа (`api`, `bot`, `worker`), собираемые в один Docker-образ и различающиеся командой запуска. Фронтенд — pnpm workspace: два приложения (`miniapp` на Vite, `web` на Next.js) над тремя общими пакетами (`core` — логика, `ui` — компоненты и токены, `config` — настройки инструментов). Связь между бэкендом и фронтендом — OpenAPI-схема, экспортируемая в файл и коммитируемая.

**Стек:** Python 3.13, FastAPI, aiogram, TaskIQ, SQLAlchemy 2.0, Alembic, Pydantic v2, PostgreSQL 18, Valkey, uv, Ruff, mypy, pytest, testcontainers. TypeScript 6, React 19, Vite 8, Next.js 16, TanStack Router, TanStack Query v5, Tailwind v4, Radix, Biome, Vitest, Playwright, pnpm.

## Глобальные ограничения

- Python 3.13. Node 24. pnpm 10. PostgreSQL 18. Valkey последней стабильной версии.
- Все Python-зависимости фиксируются в `uv.lock`, все Node-зависимости в `pnpm-lock.yaml`; оба файла коммитятся.
- TypeScript в `strict`, mypy в `strict`. Оба — блокирующие проверки.
- Ни одной бизнес-функции: тарифов, платежей, аутентификации, вызовов бизнес-методов панели Remnawave в этом подпроекте нет.
- Названия в тексте интерфейса: `Re:Pibot` в прозе, `re:pibot` в технических контекстах. Двоеточие в вордмарке — в цвете Jade, буквы — в цвете Ink.
- Цвета берутся из `docs/design/repibot-brandbook.md` дословно. Ни одного hex-значения «на глаз».
- Секретов в репозитории нет. `.env` в `.gitignore`, `.env.example` содержит только безопасные значения.
- Каждая задача завершается коммитом. Сообщения коммитов на русском, в формате `тип: краткое описание`.
- Тесты, требующие Docker (testcontainers), помечаются маркером `docker` и пропускаются, если демон недоступен.

## Структура файлов

```
pyproject.toml                     # корень uv workspace, dev-зависимости, конфиг ruff/mypy/pytest
tools/check.py                     # единая команда проверки
tools/export_openapi.py            # выгрузка схемы FastAPI в файл
tools/gen_remnawave_models.py      # генерация Pydantic-моделей панели из подмножества схем

backend/core/                      # пакет repibot_core
  src/repibot_core/settings.py     # Pydantic Settings, единственный источник конфигурации
  src/repibot_core/logging.py      # JSON-логи, идентификатор запроса, маскирование секретов
  src/repibot_core/db/base.py      # DeclarativeBase и примеси
  src/repibot_core/db/engine.py    # движок, фабрика сессий, проверка доступности
  src/repibot_core/db/models/user.py
  src/repibot_core/db/migrations/  # Alembic
  src/repibot_core/integrations/remnawave/models.py   # сгенерированные модели
  src/repibot_core/integrations/remnawave/client.py   # HTTP-клиент с ретраями
  src/repibot_core/domain/__init__.py      # пустой слой, наполняется в подпроекте 2
  src/repibot_core/services/__init__.py    # пустой слой, наполняется в подпроекте 1

backend/api/src/repibot_api/       # main.py, health.py, errors.py, middleware.py
backend/bot/src/repibot_bot/       # main.py, handlers/start.py
backend/worker/src/repibot_worker/ # broker.py, tasks.py

frontend/packages/config/          # tsconfig.base.json, biome.json
frontend/packages/ui/              # theme.css, компоненты, шрифты
frontend/packages/core/            # api-клиент, query-провайдер, i18n
frontend/apps/miniapp/             # Vite, TanStack Router, Telegram SDK
frontend/apps/web/                 # Next.js App Router, Playwright

docker/backend.Dockerfile  docker/web.Dockerfile  docker/nginx.Dockerfile  docker/nginx.conf
compose.yml  compose.local-panel.yml  .env.example
.github/workflows/ci.yml
```

---

### Задача 1: Каркас бэкенда и команда проверки

Первый рабочий результат — `uv run check` выполняется и падает осмысленно. Всё остальное вешается на этот крючок.

**Файлы:**
- Создать: `pyproject.toml`, `backend/core/pyproject.toml`
- Создать: `backend/core/src/repibot_core/__init__.py`, `backend/core/src/repibot_core/py.typed`
- Создать: `tools/__init__.py`, `tools/check.py`
- Тест: `tools/tests/test_check.py`

**Интерфейсы:**
- Отдаёт: `tools.check.Check(name: str, command: list[str], cwd: Path)` — описание одной проверки; `tools.check.run_checks(checks: list[Check]) -> list[str]` возвращает имена упавших проверок; `tools.check.CHECKS: list[Check]`; `tools.check.main() -> int` — точка входа, возвращает код выхода.

- [ ] **Шаг 1: Создать корневой `pyproject.toml`**

```toml
[project]
name = "repibot"
version = "0.1.0"
description = "Re:Pibot Shop — магазин VPN-подписок поверх Remnawave"
requires-python = ">=3.13"
dependencies = ["repibot-core"]

[project.scripts]
check = "tools.check:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["tools"]

[tool.uv.workspace]
members = ["backend/core", "backend/api", "backend/bot", "backend/worker"]

[tool.uv.sources]
repibot-core = { workspace = true }

[dependency-groups]
dev = ["ruff>=0.9", "mypy>=1.15", "pytest>=8.3", "pytest-asyncio>=0.25"]

[tool.ruff]
line-length = 100
target-version = "py313"
src = ["backend/core/src", "backend/api/src", "backend/bot/src", "backend/worker/src", "tools"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF", "ASYNC", "S", "T20"]
ignore = ["S101"]

[tool.ruff.lint.per-file-ignores]
"**/tests/*" = ["S105", "S106"]
"**/migrations/*" = ["E501"]

[tool.mypy]
python_version = "3.13"
strict = true
files = ["backend", "tools"]
exclude = "migrations"

[tool.pytest.ini_options]
testpaths = ["backend", "tools"]
asyncio_mode = "auto"
markers = ["docker: требует запущенный Docker (testcontainers)"]
```

- [ ] **Шаг 2: Создать пакет `repibot-core`**

`backend/core/pyproject.toml`:

```toml
[project]
name = "repibot-core"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/repibot_core"]
```

`backend/core/src/repibot_core/__init__.py`:

```python
"""Бизнес-логика Re:Pibot Shop. Точки входа (api, bot, worker) зависят от этого пакета."""
```

Создать пустой файл `backend/core/src/repibot_core/py.typed`.

- [ ] **Шаг 3: Создать пустые слои `domain` и `services`**

Эти каталоги наполняются в подпроектах 1 и 2, но границы слоёв фиксируются
сейчас: место, куда класть логику, должно существовать до того, как логика появится.

`backend/core/src/repibot_core/domain/__init__.py`:

```python
"""Правила предметной области: расчёт дней, промокоды, реферальные начисления.

Чистые функции и dataclass'ы без обращений к базе, сети и времени. Всё, что
здесь лежит, тестируется без запущенной инфраструктуры. Наполняется в подпроекте 2.
"""
```

`backend/core/src/repibot_core/services/__init__.py`:

```python
"""Сценарии: покупка, продление, триал, синхронизация, погашение промокода.

Единственный слой, который видят api, bot и worker. Оркестрирует domain, db
и integrations. Наполняется в подпроекте 1.
"""
```

- [ ] **Шаг 4: Написать падающий тест на `run_checks`**

`tools/tests/test_check.py`:

```python
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
```

- [ ] **Шаг 5: Запустить тест и убедиться, что он падает**

Выполнить: `uv run pytest tools/tests/test_check.py -v`
Ожидается: FAIL — `ModuleNotFoundError: No module named 'tools.check'`

- [ ] **Шаг 6: Написать `tools/check.py`**

```python
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
```

Создать пустой `tools/__init__.py` и `tools/tests/__init__.py`.

- [ ] **Шаг 7: Запустить тест и убедиться, что он проходит**

Выполнить: `uv sync && uv run pytest tools/tests/test_check.py -v`
Ожидается: PASS, четыре теста.

- [ ] **Шаг 8: Прогнать полную проверку**

Выполнить: `uv run check`
Ожидается: код выхода 0, «Все проверки пройдены».

Если ruff или mypy ругаются на собственный код — исправить код, а не ослабить правила.

- [ ] **Шаг 9: Коммит**

```bash
git add pyproject.toml uv.lock backend/core tools
git commit -m "feat: каркас uv workspace, слои core и команда uv run check"
```

---

### Задача 2: Настройки

Конфигурация — единственный источник правды о том, где что находится. Ошибка здесь проявляется как непонятное падение в рантайме через неделю, поэтому падать она должна на старте и с именем недостающей переменной.

**Файлы:**
- Создать: `backend/core/src/repibot_core/settings.py`
- Изменить: `backend/core/pyproject.toml` (зависимости)
- Тест: `backend/core/tests/test_settings.py`

**Интерфейсы:**
- Отдаёт: `Settings` (класс `pydantic_settings.BaseSettings`) с полями `environment`, `database_url`, `valkey_url`, `bot_token`, `bot_webhook_secret`, `bot_webhook_base_url`, `bot_use_polling`, `remnawave_base_url`, `remnawave_token`, `jwt_secret`, `encryption_key`, `public_web_url`, `public_app_url`, `default_language`, `supported_languages`; `get_settings() -> Settings` — кэшированный доступ.

- [ ] **Шаг 1: Добавить зависимости в `backend/core/pyproject.toml`**

```toml
dependencies = [
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
]
```

- [ ] **Шаг 2: Написать падающий тест**

`backend/core/tests/test_settings.py`:

```python
"""Настройки обязаны падать на старте, а не при первом обращении к пустому полю."""

import pytest
from pydantic import ValidationError

from repibot_core.settings import Settings

REQUIRED_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/repibot",
    "VALKEY_URL": "redis://localhost:6379/0",
    "BOT_TOKEN": "123456:test-token",
    "BOT_WEBHOOK_SECRET": "webhook-secret",
    "BOT_WEBHOOK_BASE_URL": "https://example.org",
    "REMNAWAVE_BASE_URL": "https://panel.example.org",
    "REMNAWAVE_TOKEN": "panel-token",
    "JWT_SECRET": "jwt-secret",
    "ENCRYPTION_KEY": "encryption-key",
    "PUBLIC_WEB_URL": "https://example.org",
    "PUBLIC_APP_URL": "https://example.org/app",
}


def _build(**overrides: str) -> Settings:
    env = {**REQUIRED_ENV, **overrides}
    return Settings(_env_file=None, **{k.lower(): v for k, v in env.items()})


def test_settings_load_from_environment() -> None:
    settings = _build()

    assert settings.environment == "local"
    assert settings.default_language == "ru"
    assert settings.supported_languages == ("ru", "en")
    assert settings.bot_use_polling is False


def test_secrets_are_not_exposed_in_repr() -> None:
    """Настройки попадают в логи целиком чаще, чем хотелось бы."""
    settings = _build()

    assert "panel-token" not in repr(settings)
    assert "123456:test-token" not in repr(settings)
    assert settings.remnawave_token.get_secret_value() == "panel-token"


@pytest.mark.parametrize("missing", sorted(REQUIRED_ENV))
def test_missing_required_variable_fails_with_its_name(missing: str) -> None:
    env = {k.lower(): v for k, v in REQUIRED_ENV.items() if k != missing}

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, **env)

    assert missing.lower() in str(exc.value)


def test_unsupported_default_language_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _build(DEFAULT_LANGUAGE="de")
```

- [ ] **Шаг 3: Запустить тест и убедиться, что он падает**

Выполнить: `uv run pytest backend/core/tests/test_settings.py -v`
Ожидается: FAIL — `ModuleNotFoundError: No module named 'repibot_core.settings'`

- [ ] **Шаг 4: Написать `settings.py`**

```python
"""Единственный источник конфигурации. Всё остальное читает настройки отсюда."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Language = Literal["ru", "en"]


class Settings(BaseSettings):
    """Конфигурация развёртывания.

    Поля без значения по умолчанию обязательны: их отсутствие валит процесс
    на старте с указанием имени переменной.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["local", "production"] = "local"

    database_url: str
    valkey_url: str

    bot_token: SecretStr
    bot_webhook_secret: SecretStr
    bot_webhook_base_url: str
    bot_use_polling: bool = False

    remnawave_base_url: str
    remnawave_token: SecretStr
    remnawave_timeout_seconds: float = 10.0
    remnawave_max_retries: int = 3

    jwt_secret: SecretStr
    encryption_key: SecretStr

    public_web_url: str
    public_app_url: str

    default_language: Language = "ru"
    supported_languages: tuple[Language, ...] = ("ru", "en")

    log_level: str = Field(default="INFO")

    @field_validator("default_language")
    @classmethod
    def _default_language_is_supported(cls, value: Language) -> Language:
        if value not in ("ru", "en"):
            msg = f"язык {value} не поддерживается"
            raise ValueError(msg)
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Кэшированные настройки. Читаются один раз за жизнь процесса."""
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Шаг 5: Запустить тесты и убедиться, что они проходят**

Выполнить: `uv run pytest backend/core/tests/test_settings.py -v`
Ожидается: PASS, 15 тестов (11 параметризованных плюс четыре обычных).

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core uv.lock
git commit -m "feat: настройки приложения на pydantic-settings"
```

---

### Задача 3: Логирование

**Файлы:**
- Создать: `backend/core/src/repibot_core/logging.py`
- Изменить: `backend/core/pyproject.toml` (зависимости)
- Тест: `backend/core/tests/test_logging.py`

**Интерфейсы:**
- Отдаёт: `configure_logging(level: str) -> None`; `request_id_var: ContextVar[str | None]`; `set_request_id(value: str) -> None`; `JsonFormatter` (класс `logging.Formatter`); `SecretFilter` (класс `logging.Filter`).

- [ ] **Шаг 1: Написать падающий тест**

`backend/core/tests/test_logging.py`:

```python
"""Логи читает машина, а секреты в них не попадают никогда."""

import json
import logging
from io import StringIO

from repibot_core.logging import JsonFormatter, SecretFilter, request_id_var, set_request_id


def _capture(logger_name: str) -> tuple[logging.Logger, StringIO]:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretFilter())
    logger = logging.getLogger(logger_name)
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def test_record_is_valid_json_with_expected_fields() -> None:
    logger, stream = _capture("test.json")

    logger.info("подписка продлена")

    payload = json.loads(stream.getvalue())
    assert payload["message"] == "подписка продлена"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.json"
    assert "timestamp" in payload


def test_request_id_is_attached_when_set() -> None:
    logger, stream = _capture("test.request")
    set_request_id("req-42")

    logger.info("готово")

    assert json.loads(stream.getvalue())["request_id"] == "req-42"
    request_id_var.set(None)


def test_bot_token_is_masked() -> None:
    logger, stream = _capture("test.secret")

    logger.info("вызов https://api.telegram.org/bot123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw/getMe")

    output = stream.getvalue()
    assert "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw" not in output
    assert "***" in output


def test_authorization_header_value_is_masked() -> None:
    logger, stream = _capture("test.header")

    logger.info("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature")

    output = stream.getvalue()
    assert "eyJhbGciOiJIUzI1NiJ9.payload.signature" not in output
    assert "***" in output


def test_exception_info_is_included() -> None:
    logger, stream = _capture("test.exc")

    try:
        raise ValueError("панель недоступна")
    except ValueError:
        logger.exception("сбой синхронизации")

    payload = json.loads(stream.getvalue())
    assert "ValueError" in payload["exception"]
    assert "панель недоступна" in payload["exception"]
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Выполнить: `uv run pytest backend/core/tests/test_logging.py -v`
Ожидается: FAIL — `ModuleNotFoundError: No module named 'repibot_core.logging'`

- [ ] **Шаг 3: Написать `logging.py`**

```python
"""Структурные логи в JSON с идентификатором запроса и маскированием секретов."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"bot\d+:[A-Za-z0-9_-]{30,}"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"),
    re.compile(r"(?i)(\"?(?:token|secret|password|api_key)\"?\s*[:=]\s*\"?)[^\s\",}]+"),
)


def set_request_id(value: str) -> None:
    """Устанавливает идентификатор запроса для текущего контекста выполнения."""
    request_id_var.set(value)


class SecretFilter(logging.Filter):
    """Вырезает токены и пароли из текста сообщения.

    Это последний рубеж, а не замена дисциплине: логировать секреты осознанно
    всё равно нельзя. Но чужие библиотеки об этом не знают.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = message
        for pattern in _SECRET_PATTERNS:
            masked = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "***", masked)
        if masked != message:
            record.msg = masked
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """Одна строка JSON на запись."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Настраивает корневой логгер. Вызывается один раз при старте процесса."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    for noisy in ("httpx", "httpcore", "aiogram.event"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
```

- [ ] **Шаг 4: Запустить тесты и убедиться, что они проходят**

Выполнить: `uv run pytest backend/core/tests/test_logging.py -v`
Ожидается: PASS, пять тестов.

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core
git commit -m "feat: структурное логирование с маскированием секретов"
```

---

### Задача 4: База данных и миграции

**Файлы:**
- Создать: `backend/core/src/repibot_core/db/__init__.py`, `base.py`, `engine.py`
- Создать: `backend/core/src/repibot_core/db/models/__init__.py`, `models/user.py`
- Создать: `backend/core/src/repibot_core/db/migrations/env.py`, `script.py.mako`, `versions/0001_initial.py`
- Создать: `alembic.ini`
- Изменить: `backend/core/pyproject.toml` (зависимости)
- Тест: `backend/core/tests/conftest.py`, `backend/core/tests/test_migrations.py`

**Интерфейсы:**
- Отдаёт: `Base` (DeclarativeBase); `TimestampMixin` с полями `created_at`, `updated_at`; `User` — модель таблицы `users` с полями `id: int`, `created_at`, `updated_at`; `create_engine(url: str) -> AsyncEngine`; `create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]`; `check_database(engine: AsyncEngine) -> bool`.

- [ ] **Шаг 1: Добавить зависимости**

В `backend/core/pyproject.toml`:

```toml
dependencies = [
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30",
    "alembic>=1.14",
]
```

В корневой `pyproject.toml`, в группу `dev`: `"testcontainers[postgres]>=4.9"`.

- [ ] **Шаг 2: Написать падающий тест**

`backend/core/tests/conftest.py`:

```python
"""Общие фикстуры. Postgres поднимается в контейнере — SQLite здесь не подходит.

Мы полагаемся на поведение конкретной СУБД (типы, ограничения, миграции),
и проверять их на другой базе — значит проверять не то, что поедет в продакшен.
"""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.postgres import PostgresContainer

from repibot_core.db.engine import create_engine


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as container:
        yield container.get_connection_url()


@pytest_asyncio.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(postgres_url)
    yield engine
    await engine.dispose()
```

`backend/core/tests/test_migrations.py`:

```python
"""Миграции должны применяться на чистой базе и откатываться обратно."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import check_database

pytestmark = pytest.mark.docker


def _alembic_config(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("+asyncpg", "+psycopg"))
    return config


def test_migrations_apply_and_rollback(postgres_url: str) -> None:
    config = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


async def test_users_table_exists_after_migration(
    postgres_url: str, engine: AsyncEngine
) -> None:
    command.upgrade(_alembic_config(postgres_url), "head")

    async with engine.connect() as connection:
        result = await connection.execute(
            text("select column_name from information_schema.columns where table_name = 'users'")
        )
        columns = {row[0] for row in result}

    assert {"id", "created_at", "updated_at"} <= columns


async def test_check_database_returns_true_when_reachable(engine: AsyncEngine) -> None:
    assert await check_database(engine) is True


async def test_check_database_returns_false_when_unreachable() -> None:
    from repibot_core.db.engine import create_engine

    engine = create_engine("postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nothing")
    try:
        assert await check_database(engine) is False
    finally:
        await engine.dispose()
```

Добавить в группу `dev` корневого `pyproject.toml`: `"psycopg[binary]>=3.2"` — Alembic ходит синхронным драйвером.

- [ ] **Шаг 3: Запустить тест и убедиться, что он падает**

Выполнить: `uv run pytest backend/core/tests/test_migrations.py -v`
Ожидается: FAIL — `ModuleNotFoundError: No module named 'repibot_core.db'`

- [ ] **Шаг 4: Написать `db/base.py`**

```python
"""Декларативная база и общие примеси."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Общий предок всех моделей."""


class TimestampMixin:
    """Отметки создания и изменения. Проставляются базой, а не приложением."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

- [ ] **Шаг 5: Написать `db/engine.py`**

```python
"""Движок и фабрика сессий."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Создаёт асинхронный движок.

    pool_pre_ping спасает от накопленных мёртвых соединений после перезапуска
    базы — без него первый запрос после рестарта Postgres падает.
    """
    return create_async_engine(url, echo=echo, pool_pre_ping=True, pool_size=5, max_overflow=5)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def check_database(engine: AsyncEngine) -> bool:
    """Проверяет доступность базы. Используется в /health."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except (SQLAlchemyError, OSError):
        logger.warning("база данных недоступна", exc_info=True)
        return False
    return True
```

- [ ] **Шаг 6: Написать модель `db/models/user.py`**

```python
"""Пользователь. В этом подпроекте — минимальный каркас.

Поля почты, Telegram, роли и языка добавляются в подпроекте 1 отдельной миграцией.
"""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
```

В `db/models/__init__.py`:

```python
"""Импорт всех моделей — Alembic должен видеть их в метаданных."""

from repibot_core.db.models.user import User

__all__ = ["User"]
```

- [ ] **Шаг 7: Настроить Alembic**

`alembic.ini` в корне:

```ini
[alembic]
script_location = backend/core/src/repibot_core/db/migrations
prepend_sys_path = backend/core/src
file_template = %%(rev)s_%%(slug)s

[loggers]
keys = root

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console

[handler_console]
class = StreamHandler
args = (sys.stderr,)
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

`backend/core/src/repibot_core/db/migrations/env.py`:

```python
"""Окружение Alembic. Работает синхронным драйвером — миграции запускаются
отдельным одноразовым процессом, асинхронность там ничего не даёт."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from repibot_core.db.base import Base
from repibot_core.db.models import User  # noqa: F401 — регистрация в метаданных

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`script.py.mako` — скопировать стандартный шаблон из `alembic init` (создать временную папку через `uv run alembic init tmp_alembic`, забрать файл, папку удалить).

- [ ] **Шаг 8: Написать первую миграцию**

`backend/core/src/repibot_core/db/migrations/versions/0001_initial.py`:

```python
"""Начальная схема: таблица пользователей.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("users")
```

- [ ] **Шаг 9: Запустить тесты и убедиться, что они проходят**

Выполнить: `uv run pytest backend/core/tests/test_migrations.py -v`
Ожидается: PASS, четыре теста. Первый запуск дольше — скачивается образ Postgres.

Если Docker не запущен — тесты не пропустятся автоматически, а упадут на создании контейнера. Это ожидаемо: маркер `docker` позволяет исключить их командой `-m "not docker"`, но по умолчанию они выполняются.

- [ ] **Шаг 10: Коммит**

```bash
git add backend/core alembic.ini pyproject.toml uv.lock
git commit -m "feat: слой базы данных, модели и первая миграция"
```

---

### Задача 5: FastAPI и проверка живости

**Файлы:**
- Создать: `backend/api/pyproject.toml`
- Создать: `backend/api/src/repibot_api/__init__.py`, `main.py`, `health.py`, `errors.py`, `middleware.py`
- Тест: `backend/api/tests/conftest.py`, `test_health.py`, `test_errors.py`

**Интерфейсы:**
- Потребляет: `get_settings()`, `configure_logging()`, `set_request_id()`, `create_engine()`, `check_database()`.
- Отдаёт: `create_app() -> FastAPI`; `ApiError(message: str, status_code: int, code: str)`; `HealthResponse` с полями `status: Literal["ok", "degraded"]`, `database: bool`, `valkey: bool`; `check_valkey(url: str) -> bool`.

- [ ] **Шаг 1: Создать пакет**

`backend/api/pyproject.toml`:

```toml
[project]
name = "repibot-api"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["repibot-core", "fastapi>=0.115", "uvicorn[standard]>=0.34", "redis>=5.2"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/repibot_api"]
```

В корневом `pyproject.toml` добавить `"repibot-api"` в `dependencies` и `repibot-api = { workspace = true }` в `[tool.uv.sources]`. В группу `dev` добавить `"httpx>=0.28"`.

- [ ] **Шаг 2: Написать общий conftest для тестов API**

`backend/api/tests/conftest.py`:

```python
"""Переменные окружения для тестов. Реальные подключения замоканы в самих тестах."""

import os

import pytest

_TEST_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/repibot",
    "VALKEY_URL": "redis://localhost:6379/0",
    "BOT_TOKEN": "123456:test-token",
    "BOT_WEBHOOK_SECRET": "webhook-secret",
    "BOT_WEBHOOK_BASE_URL": "https://example.org",
    "REMNAWAVE_BASE_URL": "https://panel.example.org",
    "REMNAWAVE_TOKEN": "panel-token",
    "JWT_SECRET": "jwt-secret",
    "ENCRYPTION_KEY": "encryption-key",
    "PUBLIC_WEB_URL": "https://example.org",
    "PUBLIC_APP_URL": "https://example.org/app",
}


@pytest.fixture(autouse=True, scope="session")
def _test_environment() -> None:
    for key, value in _TEST_ENV.items():
        os.environ.setdefault(key, value)
    from repibot_core.settings import get_settings

    get_settings.cache_clear()
```

- [ ] **Шаг 3: Написать падающие тесты**

`backend/api/tests/test_health.py`:

```python
"""Проверка живости отвечает раздельно по каждой зависимости.

Ответ «что-то не работает» бесполезен в три часа ночи — нужно знать, что именно.
"""

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from repibot_api.main import create_app


def _always(value: bool) -> Callable[..., Coroutine[Any, Any, bool]]:
    async def _inner(*_args: object, **_kwargs: object) -> bool:
        return value

    return _inner


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_health_reports_ok_when_all_dependencies_are_up(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repibot_api.health.check_database", _always(True))
    monkeypatch.setattr("repibot_api.health.check_valkey", _always(True))

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True, "valkey": True}


async def test_health_reports_degraded_when_database_is_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repibot_api.health.check_database", _always(False))
    monkeypatch.setattr("repibot_api.health.check_valkey", _always(True))

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": False, "valkey": True}


async def test_health_reports_degraded_when_valkey_is_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repibot_api.health.check_database", _always(True))
    monkeypatch.setattr("repibot_api.health.check_valkey", _always(False))

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["valkey"] is False


async def test_openapi_schema_is_served(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Re:Pibot Shop API"


async def test_response_carries_request_id_header(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repibot_api.health.check_database", _always(True))
    monkeypatch.setattr("repibot_api.health.check_valkey", _always(True))

    response = await client.get("/health")

    assert response.headers["x-request-id"]
```

`backend/api/tests/test_errors.py`:

```python
"""Ошибки отдаются одним форматом — клиенту не нужно разбирать три разных."""

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from repibot_api.errors import ApiError
from repibot_api.main import create_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise ApiError(message="тариф не найден", status_code=404, code="plan_not_found")

    @app.get("/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("внутренняя подробность, которой не место в ответе")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_api_error_is_rendered_in_common_shape(client: AsyncClient) -> None:
    response = await client.get("/boom")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "plan_not_found", "message": "тариф не найден"}}


async def test_unexpected_error_does_not_leak_internals(client: AsyncClient) -> None:
    response = await client.get("/unexpected")

    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "Внутренняя ошибка"}}
    assert "внутренняя подробность" not in response.text
```

- [ ] **Шаг 4: Запустить тесты и убедиться, что они падают**

Выполнить: `uv run pytest backend/api/tests -v`
Ожидается: FAIL — `ModuleNotFoundError: No module named 'repibot_api'`

- [ ] **Шаг 5: Написать `errors.py`**

```python
"""Единый формат ошибок API."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Ожидаемая ошибка, о которой клиенту можно рассказать честно."""

    def __init__(self, message: str, status_code: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message))

    @app.exception_handler(Exception)
    async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("необработанная ошибка", exc_info=exc)
        return JSONResponse(status_code=500, content=_body("internal_error", "Внутренняя ошибка"))
```

- [ ] **Шаг 6: Написать `middleware.py`**

```python
"""Сквозной идентификатор запроса."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from repibot_core.logging import set_request_id

HEADER = "X-Request-ID"


def register_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(HEADER) or str(uuid.uuid4())
        set_request_id(request_id)
        response = await call_next(request)
        response.headers[HEADER] = request_id
        return response
```

- [ ] **Шаг 7: Написать `health.py`**

```python
"""Проверка живости: раздельный статус по каждой зависимости."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from redis.asyncio import Redis

from repibot_core.db.engine import check_database, create_engine
from repibot_core.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    valkey: bool


async def check_valkey(url: str) -> bool:
    client: Redis = Redis.from_url(url)
    try:
        await client.ping()
    except (OSError, ConnectionError):
        logger.warning("valkey недоступен", exc_info=True)
        return False
    finally:
        await client.aclose()
    return True


@router.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    settings = get_settings()

    engine = create_engine(settings.database_url)
    try:
        database_ok = await check_database(engine)
    finally:
        await engine.dispose()

    valkey_ok = await check_valkey(settings.valkey_url)

    healthy = database_ok and valkey_ok
    if not healthy:
        response.status_code = 503
    return HealthResponse(
        status="ok" if healthy else "degraded", database=database_ok, valkey=valkey_ok
    )
```

- [ ] **Шаг 8: Написать `main.py`**

```python
"""Сборка приложения FastAPI."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from repibot_api.errors import register_error_handlers
from repibot_api.health import router as health_router
from repibot_api.middleware import register_request_id_middleware
from repibot_core.logging import configure_logging
from repibot_core.settings import get_settings

client_router = APIRouter(prefix="/api", tags=["client"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Re:Pibot Shop API",
        version="0.1.0",
        docs_url="/api/docs" if settings.environment == "local" else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.public_web_url, settings.public_app_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_request_id_middleware(app)
    register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(client_router)
    app.include_router(admin_router)
    return app


app = create_app()
```

- [ ] **Шаг 9: Запустить тесты и убедиться, что они проходят**

Выполнить: `uv run pytest backend/api/tests -v`
Ожидается: PASS, семь тестов.

- [ ] **Шаг 10: Коммит**

```bash
git add backend/api pyproject.toml uv.lock
git commit -m "feat: приложение FastAPI с проверкой живости и единым форматом ошибок"
```

---

### Задача 6: Телеграм-бот

**Файлы:**
- Создать: `backend/bot/pyproject.toml`
- Создать: `backend/bot/src/repibot_bot/__init__.py`, `main.py`, `handlers/__init__.py`, `handlers/start.py`
- Создать: `backend/bot/tests/conftest.py` (копия conftest из задачи 5)
- Тест: `backend/bot/tests/test_start.py`

**Интерфейсы:**
- Потребляет: `get_settings()`, `configure_logging()`.
- Отдаёт: `handle_start(message: Message) -> None`; `build_dispatcher(storage: BaseStorage) -> Dispatcher`; `run_webhook() -> None`; `run_polling() -> None`; `main() -> None`.

- [ ] **Шаг 1: Создать пакет**

`backend/bot/pyproject.toml`:

```toml
[project]
name = "repibot-bot"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["repibot-core", "aiogram>=3.30", "redis>=5.2"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/repibot_bot"]
```

Добавить `"repibot-bot"` в зависимости корня и в `[tool.uv.sources]`. Скопировать `backend/api/tests/conftest.py` в `backend/bot/tests/conftest.py` без изменений.

- [ ] **Шаг 2: Написать падающий тест**

`backend/bot/tests/test_start.py`:

```python
"""Хендлер проверяется напрямую: поднимать Telegram ради проверки текста незачем."""

from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.storage.memory import MemoryStorage

from repibot_bot.handlers.start import handle_start
from repibot_bot.main import build_dispatcher


async def test_start_greets_user_by_name() -> None:
    message = MagicMock()
    message.answer = AsyncMock()
    message.from_user.full_name = "Иван"

    await handle_start(message)

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "Иван" in text
    assert "Re:Pibot" in text


async def test_start_survives_missing_from_user() -> None:
    """Сообщения от каналов приходят без from_user — падать на этом нельзя."""
    message = MagicMock()
    message.answer = AsyncMock()
    message.from_user = None

    await handle_start(message)

    message.answer.assert_awaited_once()


def test_dispatcher_registers_start_router() -> None:
    dispatcher = build_dispatcher(MemoryStorage())

    assert any(router.name == "start" for router in dispatcher.sub_routers)
```

- [ ] **Шаг 3: Запустить тест и убедиться, что он падает**

Выполнить: `uv run pytest backend/bot/tests -v`
Ожидается: FAIL — `ModuleNotFoundError: No module named 'repibot_bot'`

- [ ] **Шаг 4: Написать `handlers/start.py`**

```python
"""Обработчик /start. В этом подпроекте — заглушка.

Регистрация, привязка аккаунта и кнопка запуска MiniApp появятся в подпроекте 1.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    name = message.from_user.full_name if message.from_user else "друг"
    await message.answer(f"Привет, {name}. Это Re:Pibot — магазин ещё готовится.")
```

- [ ] **Шаг 5: Написать `main.py`**

```python
"""Точка входа бота.

Вебхук — рабочий режим за Nginx. Long polling включается переменной окружения
и нужен только локально, где внешний вебхук недоступен.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from repibot_bot.handlers.start import router as start_router
from repibot_core.logging import configure_logging
from repibot_core.settings import get_settings

logger = logging.getLogger(__name__)

WEB_SERVER_HOST = "0.0.0.0"  # noqa: S104 — контейнер закрыт сетью compose, наружу смотрит nginx
WEB_SERVER_PORT = 8080


def build_dispatcher(storage: BaseStorage) -> Dispatcher:
    dispatcher = Dispatcher(storage=storage)
    dispatcher.include_router(start_router)
    return dispatcher


def _build_bot() -> Bot:
    settings = get_settings()
    return Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def _webhook_path() -> str:
    """Секрет в пути — первый барьер: чужие запросы не доходят до разбора апдейта."""
    return f"/tg/webhook/{get_settings().bot_webhook_secret.get_secret_value()}"


def run_webhook() -> None:
    settings = get_settings()
    bot = _build_bot()
    dispatcher = build_dispatcher(RedisStorage.from_url(settings.valkey_url))

    async def on_startup(bot: Bot) -> None:
        url = f"{settings.bot_webhook_base_url}{_webhook_path()}"
        await bot.set_webhook(
            url,
            secret_token=settings.bot_webhook_secret.get_secret_value(),
            drop_pending_updates=True,
        )
        logger.info("вебхук установлен")

    dispatcher.startup.register(on_startup)

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=settings.bot_webhook_secret.get_secret_value(),
    ).register(app, path=_webhook_path())
    setup_application(app, dispatcher, bot=bot)

    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)


def run_polling() -> None:
    async def _main() -> None:
        bot = _build_bot()
        dispatcher = build_dispatcher(RedisStorage.from_url(get_settings().valkey_url))
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)

    asyncio.run(_main())


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.bot_use_polling:
        logger.info("бот запускается в режиме long polling")
        run_polling()
    else:
        logger.info("бот запускается в режиме вебхука")
        run_webhook()


if __name__ == "__main__":
    main()
```

- [ ] **Шаг 6: Запустить тесты и убедиться, что они проходят**

Выполнить: `uv run pytest backend/bot/tests -v`
Ожидается: PASS, три теста.

- [ ] **Шаг 7: Коммит**

```bash
git add backend/bot pyproject.toml uv.lock
git commit -m "feat: бот на aiogram с вебхуком и режимом polling для разработки"
```

---

### Задача 7: Фоновый воркер

**Файлы:**
- Создать: `backend/worker/pyproject.toml`
- Создать: `backend/worker/src/repibot_worker/__init__.py`, `broker.py`, `tasks.py`
- Создать: `backend/worker/tests/conftest.py` (копия conftest из задачи 5)
- Тест: `backend/worker/tests/test_tasks.py`

**Интерфейсы:**
- Потребляет: `get_settings()`, `check_database()`, `create_engine()`.
- Отдаёт: `broker` — экземпляр `ListQueueBroker` с `queue_name="repibot_tasks"`; `scheduler` — экземпляр `TaskiqScheduler`; `heartbeat() -> dict[str, str]`.

- [ ] **Шаг 1: Создать пакет**

`backend/worker/pyproject.toml`:

```toml
[project]
name = "repibot-worker"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["repibot-core", "taskiq>=0.11", "taskiq-redis>=1.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/repibot_worker"]
```

Добавить `"repibot-worker"` в зависимости корня и в `[tool.uv.sources]`. Скопировать conftest.

- [ ] **Шаг 2: Написать падающий тест**

`backend/worker/tests/test_tasks.py`:

```python
"""Задачи проверяются на InMemoryBroker — реальный Valkey для этого не нужен."""

from taskiq import InMemoryBroker

from repibot_worker import tasks
from repibot_worker.broker import broker


async def test_heartbeat_returns_alive_status(monkeypatch) -> None:  # noqa: ANN001
    async def _reachable(*_args: object, **_kwargs: object) -> bool:
        return True

    monkeypatch.setattr("repibot_worker.tasks.check_database", _reachable)

    result = await tasks.heartbeat()

    assert result == {"status": "alive", "database": "ok"}


async def test_heartbeat_reports_database_down(monkeypatch) -> None:  # noqa: ANN001
    async def _unreachable(*_args: object, **_kwargs: object) -> bool:
        return False

    monkeypatch.setattr("repibot_worker.tasks.check_database", _unreachable)

    result = await tasks.heartbeat()

    assert result["database"] == "down"


async def test_task_can_be_dispatched_and_executed(monkeypatch) -> None:  # noqa: ANN001
    async def _reachable(*_args: object, **_kwargs: object) -> bool:
        return True

    monkeypatch.setattr("repibot_worker.tasks.check_database", _reachable)

    test_broker = InMemoryBroker()
    task = test_broker.register_task(tasks.heartbeat.original_func, task_name="heartbeat")

    await test_broker.startup()
    handle = await task.kiq()
    result = await handle.wait_result(timeout=5)
    await test_broker.shutdown()

    assert result.is_err is False
    assert result.return_value["status"] == "alive"


def test_heartbeat_has_schedule_label() -> None:
    """Без метки schedule задача не выполнится сама — это легко упустить."""
    schedule = tasks.heartbeat.labels.get("schedule")

    assert schedule, "у задачи heartbeat нет метки schedule"
    assert schedule[0]["cron"] == "*/5 * * * *"


def test_broker_queue_name_is_namespaced() -> None:
    """Один Valkey может обслуживать и панель, и магазин — очереди не должны пересекаться."""
    assert broker.queue_name == "repibot_tasks"
```

- [ ] **Шаг 3: Запустить тест и убедиться, что он падает**

Выполнить: `uv run pytest backend/worker/tests -v`
Ожидается: FAIL — `ModuleNotFoundError: No module named 'repibot_worker'`

- [ ] **Шаг 4: Написать `broker.py`**

```python
"""Брокер и планировщик.

Расписание живёт в метках задач (LabelScheduleSource), а не во внешнем
хранилище: расписание — часть кода и должно ездить вместе с ним в git.
"""

from __future__ import annotations

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from repibot_core.settings import get_settings

_settings = get_settings()

result_backend: RedisAsyncResultBackend[object] = RedisAsyncResultBackend(
    redis_url=_settings.valkey_url,
    result_ex_time=86_400,
    prefix_str="repibot_results",
)

broker = ListQueueBroker(url=_settings.valkey_url, queue_name="repibot_tasks").with_result_backend(
    result_backend
)

scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])
```

- [ ] **Шаг 5: Написать `tasks.py`**

```python
"""Задачи воркера.

В этом подпроекте одна задача-заглушка: она подтверждает, что очередь,
планировщик и подключение к базе из воркера действительно работают.
"""

from __future__ import annotations

import logging

from repibot_core.db.engine import check_database, create_engine
from repibot_core.settings import get_settings
from repibot_worker.broker import broker

logger = logging.getLogger(__name__)


@broker.task(schedule=[{"cron": "*/5 * * * *"}])
async def heartbeat() -> dict[str, str]:
    """Проверяет, что воркер жив и видит базу."""
    engine = create_engine(get_settings().database_url)
    try:
        database_ok = await check_database(engine)
    finally:
        await engine.dispose()

    logger.info("heartbeat: база %s", "доступна" if database_ok else "недоступна")
    return {"status": "alive", "database": "ok" if database_ok else "down"}
```

`backend/worker/src/repibot_worker/__init__.py`:

```python
"""Фоновые задачи Re:Pibot Shop."""

from repibot_worker.broker import broker, scheduler

__all__ = ["broker", "scheduler"]
```

- [ ] **Шаг 6: Запустить тесты и убедиться, что они проходят**

Выполнить: `uv run pytest backend/worker/tests -v`
Ожидается: PASS, пять тестов.

- [ ] **Шаг 7: Коммит**

```bash
git add backend/worker pyproject.toml uv.lock
git commit -m "feat: воркер TaskIQ с планировщиком и задачей heartbeat"
```

---

### Задача 8: Клиент панели Remnawave

Ни одного бизнес-метода — только транспорт, типы и поведение при отказах. Методы появятся в подпроекте 2.

**Файлы:**
- Создать: `tools/gen_remnawave_models.py`
- Создать: `backend/core/src/repibot_core/integrations/__init__.py`, `remnawave/__init__.py`, `remnawave/client.py`
- Создать генерацией: `backend/core/src/repibot_core/integrations/remnawave/models.py`
- Изменить: `backend/core/pyproject.toml`, корневой `pyproject.toml`
- Тест: `backend/core/tests/test_remnawave_client.py`

**Интерфейсы:**
- Отдаёт: `RemnawaveClient(base_url: str, token: str, timeout: float = 10.0, max_retries: int = 3)` с методами `async request(method: str, path: str, **kwargs) -> httpx.Response` и `async aclose() -> None`; `RemnawaveError(Exception)`; `RemnawaveUnavailable(RemnawaveError)`; `ROOT_SCHEMAS: tuple[str, ...]` в скрипте генерации.

- [ ] **Шаг 1: Добавить зависимости**

В `backend/core/pyproject.toml` добавить `"httpx>=0.28"` и `"tenacity>=9.0"`. В группу `dev` корня добавить `"datamodel-code-generator>=0.26"`.

- [ ] **Шаг 2: Написать скрипт генерации моделей**

`tools/gen_remnawave_models.py`:

```python
"""Генерация Pydantic-моделей панели Remnawave.

Схема панели — 142 эндпоинта и полтора мегабайта JSON. Генерировать всё
целиком значит принести в репозиторий десятки тысяч строк, которые никто не
читает. Генерируем только нужные корневые схемы и всё, на что они ссылаются;
список растёт по мере появления методов клиента.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "remnawave-api" / "api-1.json"
TARGET = ROOT / "backend/core/src/repibot_core/integrations/remnawave/models.py"

ROOT_SCHEMAS: tuple[str, ...] = ("GetUserByUuidResponseDto",)


def _refs_in(node: object) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                found.append(value.rsplit("/", 1)[-1])
            else:
                found.extend(_refs_in(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_refs_in(item))
    return found


def collect_schemas(schemas: dict[str, object], roots: tuple[str, ...]) -> set[str]:
    """Собирает имена схем, достижимых из корневых по $ref."""
    seen: set[str] = set()
    queue = list(roots)
    while queue:
        name = queue.pop()
        if name in seen or name not in schemas:
            continue
        seen.add(name)
        queue.extend(_refs_in(schemas[name]))
    return seen


def main() -> int:
    document = json.loads(SOURCE.read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]
    needed = collect_schemas(schemas, ROOT_SCHEMAS)

    subset = {
        "openapi": document["openapi"],
        "info": document["info"],
        "paths": {},
        "components": {"schemas": {name: schemas[name] for name in sorted(needed)}},
    }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(subset, handle, ensure_ascii=False)
        temp_path = Path(handle.name)

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(  # noqa: S603
            [
                "uv", "run", "datamodel-codegen",
                "--input", str(temp_path),
                "--input-file-type", "openapi",
                "--output", str(TARGET),
                "--output-model-type", "pydantic_v2.BaseModel",
                "--target-python-version", "3.13",
                "--use-standard-collections",
                "--use-union-operator",
                "--disable-timestamp",
                "--custom-file-header",
                "# Сгенерировано tools/gen_remnawave_models.py. Не редактировать вручную.",
            ],
            cwd=ROOT,
            check=True,
        )
    finally:
        temp_path.unlink(missing_ok=True)

    print(f"Сгенерировано схем: {len(needed)}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Шаг 3: Написать тест на сборку подмножества схем**

`backend/core/tests/test_remnawave_models_generation.py`:

```python
"""Обход $ref должен собирать все зависимые схемы, иначе генерация упадёт."""

from tools.gen_remnawave_models import ROOT_SCHEMAS, collect_schemas


def test_collect_schemas_follows_nested_refs() -> None:
    schemas = {
        "Root": {"properties": {"child": {"$ref": "#/components/schemas/Child"}}},
        "Child": {"properties": {"leaf": {"$ref": "#/components/schemas/Leaf"}}},
        "Leaf": {"type": "string"},
        "Unrelated": {"type": "string"},
    }

    assert collect_schemas(schemas, ("Root",)) == {"Root", "Child", "Leaf"}


def test_collect_schemas_survives_cycles() -> None:
    schemas = {
        "A": {"properties": {"b": {"$ref": "#/components/schemas/B"}}},
        "B": {"properties": {"a": {"$ref": "#/components/schemas/A"}}},
    }

    assert collect_schemas(schemas, ("A",)) == {"A", "B"}


def test_declared_root_schemas_exist_in_panel_specification() -> None:
    """Опечатка в имени корневой схемы иначе проявится пустым файлом моделей."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    document = json.loads(
        (root / "docs" / "remnawave-api" / "api-1.json").read_text(encoding="utf-8")
    )

    available = set(document["components"]["schemas"])
    assert set(ROOT_SCHEMAS) <= available
```

- [ ] **Шаг 4: Запустить тест и убедиться, что он падает**

Выполнить: `uv run pytest backend/core/tests/test_remnawave_models_generation.py -v`
Ожидается: FAIL — `ModuleNotFoundError: No module named 'tools.gen_remnawave_models'` (если шаг 2 ещё не выполнен) либо PASS, если скрипт уже написан. В последнем случае перейти к шагу 5.

- [ ] **Шаг 5: Сгенерировать модели**

Выполнить: `uv run python tools/gen_remnawave_models.py`
Ожидается: вывод «Сгенерировано схем: N» (N больше единицы), файл `models.py` содержит класс `GetUserByUuidResponseDto`.

- [ ] **Шаг 6: Написать падающий тест клиента**

`backend/core/tests/test_remnawave_client.py`:

```python
"""Клиент панели: авторизация, ретраи, поведение при отказе.

Панель может стоять на другом сервере и уходить в перезагрузку ровно в момент
оплаты — поведение при отказах здесь важнее набора методов.
"""

import httpx
import pytest

from repibot_core.integrations.remnawave.client import RemnawaveClient, RemnawaveUnavailable


def _client(transport: httpx.MockTransport) -> RemnawaveClient:
    client = RemnawaveClient(
        base_url="https://panel.example.org", token="panel-token", timeout=1.0, max_retries=3
    )
    client._http = httpx.AsyncClient(  # noqa: SLF001
        transport=transport,
        base_url="https://panel.example.org",
        headers={"Authorization": "Bearer panel-token"},
    )
    return client


async def test_request_sends_bearer_token() -> None:
    seen: dict[str, str] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"response": {}})

    client = _client(httpx.MockTransport(handle))
    await client.request("GET", "/api/system/health")
    await client.aclose()

    assert seen["authorization"] == "Bearer panel-token"


async def test_retries_on_server_error_then_succeeds() -> None:
    calls = {"count": 0}

    def handle(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"response": {"ok": True}})

    client = _client(httpx.MockTransport(handle))
    response = await client.request("GET", "/api/system/health")
    await client.aclose()

    assert calls["count"] == 3
    assert response.json()["response"]["ok"] is True


async def test_raises_unavailable_after_exhausting_retries() -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    client = _client(httpx.MockTransport(handle))
    with pytest.raises(RemnawaveUnavailable):
        await client.request("GET", "/api/system/health")
    await client.aclose()


async def test_client_errors_are_not_retried() -> None:
    """Повторять запрос, на который панель ответила «нет такого пользователя», бессмысленно."""
    calls = {"count": 0}

    def handle(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404, json={"message": "not found"})

    client = _client(httpx.MockTransport(handle))
    response = await client.request("GET", "/api/users/by-uuid/unknown")
    await client.aclose()

    assert calls["count"] == 1
    assert response.status_code == 404


async def test_connection_error_is_wrapped() -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("нет маршрута до панели")

    client = _client(httpx.MockTransport(handle))
    with pytest.raises(RemnawaveUnavailable):
        await client.request("GET", "/api/system/health")
    await client.aclose()
```

- [ ] **Шаг 7: Запустить тест и убедиться, что он падает**

Выполнить: `uv run pytest backend/core/tests/test_remnawave_client.py -v`
Ожидается: FAIL — `ModuleNotFoundError: No module named 'repibot_core.integrations'`

- [ ] **Шаг 8: Написать `client.py`**

```python
"""HTTP-клиент панели Remnawave.

Бизнес-методов здесь нет: только транспорт, авторизация и поведение при
отказах. Методы появятся в подпроекте 2 и будут возвращать модели из models.py.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class RemnawaveError(Exception):
    """Базовая ошибка взаимодействия с панелью."""


class RemnawaveUnavailable(RemnawaveError):
    """Панель недоступна или отвечает ошибкой сервера после всех попыток."""


class _RetryableResponse(Exception):  # noqa: N818
    """Внутренний сигнал для tenacity: ответ получен, но его стоит повторить."""

    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"статус {response.status_code}")
        self.response = response


class RemnawaveClient:
    """Тонкая обёртка над httpx с ретраями на временных отказах.

    Повторяются только сетевые ошибки и коды 429 и 5xx. Ответы 4xx
    возвращаются как есть: повторять запрос, на который панель ответила
    осмысленным отказом, бессмысленно и вредно.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 10.0,
        max_retries: int = 3,
    ) -> None:
        self.max_retries = max_retries
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
        )

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:  # noqa: ANN401
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=0.5, max=5),
                retry=retry_if_exception_type((httpx.TransportError, _RetryableResponse)),
            ):
                with attempt:
                    response = await self._http.request(method, path, **kwargs)
                    if response.status_code in _RETRYABLE_STATUSES:
                        raise _RetryableResponse(response)
                    return response
        except RetryError as error:
            logger.warning("панель Remnawave недоступна: %s %s", method, path)
            raise RemnawaveUnavailable(f"{method} {path}") from error
        raise RemnawaveUnavailable(f"{method} {path}")  # pragma: no cover

    async def aclose(self) -> None:
        await self._http.aclose()
```

Создать `backend/core/src/repibot_core/integrations/__init__.py` и `remnawave/__init__.py` с docstring-заглушками.

- [ ] **Шаг 9: Запустить тесты и убедиться, что они проходят**

Выполнить: `uv run pytest backend/core/tests/test_remnawave_client.py -v`
Ожидается: PASS, пять тестов.

- [ ] **Шаг 10: Исключить сгенерированный файл из проверок стиля**

В корневом `pyproject.toml`, в секцию `[tool.ruff]` добавить:

```toml
extend-exclude = ["**/integrations/remnawave/models.py"]
```

В `[tool.mypy]` заменить строку `exclude` на:

```toml
exclude = "(migrations|integrations/remnawave/models\\.py)"
```

- [ ] **Шаг 11: Прогнать полную проверку и закоммитить**

Выполнить: `uv run check`
Ожидается: код выхода 0.

```bash
git add backend/core tools pyproject.toml uv.lock
git commit -m "feat: транспортный клиент панели Remnawave и генерация её моделей"
```

---

### Задача 9: Рабочее пространство фронтенда и общие настройки инструментов

**Файлы:**
- Создать: `frontend/package.json`, `frontend/pnpm-workspace.yaml`, `frontend/.npmrc`
- Создать: `frontend/packages/config/package.json`, `tsconfig.base.json`, `biome.json`
- Изменить: `tools/check.py` (добавить проверки фронтенда)
- Тест: `tools/tests/test_check.py` (дополнить)

**Интерфейсы:**
- Отдаёт: пакет `@repibot/config` с файлами `tsconfig.base.json` и `biome.json`; расширенный `CHECKS` в `tools/check.py`, включающий `biome`, `typecheck`, `vitest`.

- [ ] **Шаг 1: Создать рабочее пространство**

`frontend/pnpm-workspace.yaml`:

```yaml
packages:
  - "apps/*"
  - "packages/*"
```

`frontend/package.json`:

```json
{
  "name": "repibot-frontend",
  "private": true,
  "packageManager": "pnpm@10.0.0",
  "engines": { "node": ">=24" },
  "scripts": {
    "lint": "biome ci .",
    "format": "biome format --write .",
    "typecheck": "pnpm -r --parallel typecheck",
    "test": "pnpm -r --parallel test",
    "build": "pnpm -r build"
  },
  "devDependencies": {
    "@biomejs/biome": "^2.0.0",
    "typescript": "^6.0.0"
  }
}
```

`frontend/.npmrc`:

```
strict-peer-dependencies=false
auto-install-peers=true
```

- [ ] **Шаг 2: Создать пакет `@repibot/config`**

`frontend/packages/config/package.json`:

```json
{
  "name": "@repibot/config",
  "version": "0.1.0",
  "private": true,
  "files": ["tsconfig.base.json", "biome.json"]
}
```

`frontend/packages/config/tsconfig.base.json`:

```json
{
  "compilerOptions": {
    "target": "ES2023",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "exactOptionalPropertyTypes": true,
    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "noEmit": true
  }
}
```

`frontend/packages/config/biome.json`:

```json
{
  "$schema": "https://biomejs.dev/schemas/2.0.0/schema.json",
  "files": {
    "includes": ["**", "!**/dist", "!**/.next", "!**/node_modules", "!**/schema.d.ts"]
  },
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2,
    "lineWidth": 100
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true,
      "correctness": { "noUnusedImports": "error", "noUnusedVariables": "error" },
      "style": { "useConst": "error", "noNonNullAssertion": "error" },
      "suspicious": { "noExplicitAny": "error" }
    }
  },
  "javascript": {
    "formatter": { "quoteStyle": "single", "semicolons": "asNeeded" }
  }
}
```

Корневой `frontend/biome.json`:

```json
{
  "$schema": "https://biomejs.dev/schemas/2.0.0/schema.json",
  "extends": ["./packages/config/biome.json"]
}
```

- [ ] **Шаг 3: Написать падающий тест на состав проверок**

Дополнить `tools/tests/test_check.py`:

```python
def test_checks_cover_backend_and_frontend() -> None:
    """Проверка, которой нет в списке, не выполняется ни локально, ни в CI."""
    from tools.check import CHECKS

    names = {check.name for check in CHECKS}

    assert {"ruff-lint", "ruff-format", "mypy", "pytest"} <= names
    assert {"biome", "typecheck", "vitest"} <= names


def test_frontend_checks_run_in_frontend_directory() -> None:
    from tools.check import CHECKS, ROOT

    frontend_checks = [c for c in CHECKS if c.name in {"biome", "typecheck", "vitest"}]

    assert frontend_checks
    for check in frontend_checks:
        assert check.cwd == ROOT / "frontend"
```

- [ ] **Шаг 4: Запустить тест и убедиться, что он падает**

Выполнить: `uv run pytest tools/tests/test_check.py -v`
Ожидается: FAIL — в `CHECKS` нет `biome`.

- [ ] **Шаг 5: Расширить `tools/check.py`**

Заменить список `CHECKS`:

```python
FRONTEND = ROOT / "frontend"

CHECKS: list[Check] = [
    Check(name="ruff-lint", command=["uv", "run", "ruff", "check", "."], cwd=ROOT),
    Check(name="ruff-format", command=["uv", "run", "ruff", "format", "--check", "."], cwd=ROOT),
    Check(name="mypy", command=["uv", "run", "mypy"], cwd=ROOT),
    Check(name="pytest", command=["uv", "run", "pytest", "-q"], cwd=ROOT),
    Check(name="biome", command=["pnpm", "lint"], cwd=FRONTEND),
    Check(name="typecheck", command=["pnpm", "typecheck"], cwd=FRONTEND),
    Check(name="vitest", command=["pnpm", "test"], cwd=FRONTEND),
]
```

На Windows `pnpm` — это `pnpm.cmd`. Чтобы не разбираться с этим в каждой проверке, обернуть команду:

```python
import shutil

def _resolve(command: list[str]) -> list[str]:
    """Windows не запускает pnpm без расширения — ищем реальный исполняемый файл."""
    executable = shutil.which(command[0])
    if executable is None:
        return command
    return [executable, *command[1:]]
```

И применить `_resolve(check.command)` внутри `run_checks` перед вызовом `subprocess.run`.

- [ ] **Шаг 6: Запустить тест и убедиться, что он проходит**

Выполнить: `uv run pytest tools/tests/test_check.py -v`
Ожидается: PASS, шесть тестов.

Проверки фронтенда пока упадут при реальном запуске `uv run check` — рабочих пакетов ещё нет. Это ожидаемо и исправляется следующими тремя задачами.

- [ ] **Шаг 7: Коммит**

```bash
git add frontend tools
git commit -m "feat: рабочее пространство pnpm и общие настройки инструментов фронтенда"
```

---

### Задача 10: Пакет `@repibot/ui` — токены бренда и базовые компоненты

Здесь оседает бренд-бук. Если цвета разъедутся с ним, разъедутся везде сразу.

**Файлы:**
- Создать: `frontend/packages/ui/package.json`, `tsconfig.json`, `vitest.config.ts`
- Создать: `frontend/packages/ui/src/theme.css`
- Создать: `frontend/packages/ui/src/lib/cn.ts`
- Создать: `frontend/packages/ui/src/components/button.tsx`, `input.tsx`, `card.tsx`
- Создать: `frontend/packages/ui/src/index.ts`
- Тест: `frontend/packages/ui/src/theme.test.ts`, `src/components/button.test.tsx`

**Интерфейсы:**
- Отдаёт: `cn(...classes: ClassValue[]): string`; `Button` с пропсами `variant?: 'primary' | 'secondary' | 'ghost'`, `size?: 'sm' | 'md' | 'lg'`; `Input`; `Card`; CSS-файл `@repibot/ui/theme.css` с переменными `--rp-*` и токенами Tailwind `--color-*`.

- [ ] **Шаг 1: Создать пакет**

`frontend/packages/ui/package.json`:

```json
{
  "name": "@repibot/ui",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "exports": {
    ".": "./src/index.ts",
    "./theme.css": "./src/theme.css"
  },
  "scripts": {
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "@hugeicons/react": "^1.0.0",
    "@radix-ui/react-slot": "^1.1.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "tailwind-merge": "^3.0.0"
  },
  "peerDependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "tailwindcss": "^4.0.0"
  },
  "devDependencies": {
    "@repibot/config": "workspace:*",
    "@testing-library/jest-dom": "^6.6.0",
    "@testing-library/react": "^16.1.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "jsdom": "^26.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "tailwindcss": "^4.0.0",
    "vitest": "^3.0.0"
  }
}
```

`frontend/packages/ui/tsconfig.json`:

```json
{
  "extends": "@repibot/config/tsconfig.base.json",
  "include": ["src"]
}
```

`frontend/packages/ui/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
  },
})
```

`frontend/packages/ui/vitest.setup.ts`:

```ts
import '@testing-library/jest-dom/vitest'
```

- [ ] **Шаг 2: Написать падающий тест на токены**

`frontend/packages/ui/src/theme.test.ts`:

```ts
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/**
 * Значения взяты из docs/design/repibot-brandbook.md, раздел 3.
 * Тест существует ровно затем, чтобы правка «на глаз» в CSS не прошла молча.
 */
const LIGHT_TOKENS: Record<string, string> = {
  '--rp-ink': '#1A1A18',
  '--rp-paper': '#FAF9F7',
  '--rp-jade': '#17A67C',
  '--rp-jade-deep': '#0E6B50',
  '--rp-jade-mist': '#E4F5EE',
  '--rp-bg': '#FAF9F7',
  '--rp-surface': '#FFFFFF',
  '--rp-surface-sunken': '#F1F0EC',
  '--rp-border': '#E2E1DC',
  '--rp-border-strong': '#C9C7C0',
  '--rp-text': '#1A1A18',
  '--rp-text-secondary': '#575651',
  '--rp-text-muted': '#7A7873',
  '--rp-text-accent': '#0E6B50',
  '--rp-accent': '#17A67C',
  '--rp-accent-hover': '#128A67',
  '--rp-on-accent': '#FFFFFF',
  '--rp-success': '#2F9E44',
  '--rp-warning': '#B87A0B',
  '--rp-danger': '#C0392F',
  '--rp-info': '#2B72C4',
}

const DARK_TOKENS: Record<string, string> = {
  '--rp-bg': '#121311',
  '--rp-surface': '#1C1D1B',
  '--rp-surface-sunken': '#0D0E0C',
  '--rp-border': '#2E2F2C',
  '--rp-border-strong': '#43443F',
  '--rp-text': '#F2F1ED',
  '--rp-text-secondary': '#A3A19A',
  '--rp-text-muted': '#7A7873',
  '--rp-text-accent': '#2CC694',
  '--rp-accent': '#2CC694',
  '--rp-accent-hover': '#45D6A8',
  '--rp-on-accent': '#08150F',
  '--rp-jade-mist': '#10322A',
  '--rp-success': '#51CF66',
  '--rp-warning': '#E8A32C',
  '--rp-danger': '#E8615A',
  '--rp-info': '#5AA3E8',
}

const css = readFileSync(fileURLToPath(new URL('./theme.css', import.meta.url)), 'utf8')

function block(selector: string): string {
  const start = css.indexOf(selector)
  expect(start, `в theme.css нет блока ${selector}`).toBeGreaterThan(-1)
  const open = css.indexOf('{', start)
  const close = css.indexOf('}', open)
  return css.slice(open, close)
}

describe('токены бренда', () => {
  const light = block(':root')
  const dark = block('[data-theme="dark"]')

  it.each(Object.entries(LIGHT_TOKENS))('светлая тема: %s = %s', (token, value) => {
    expect(light).toContain(`${token}: ${value}`)
  })

  it.each(Object.entries(DARK_TOKENS))('тёмная тема: %s = %s', (token, value) => {
    expect(dark).toContain(`${token}: ${value}`)
  })

  it('в тёмной теме акцент не остаётся основным Jade', () => {
    expect(dark).not.toContain('--rp-accent: #17A67C')
  })

  it('вариант dark объявлен через атрибут data-theme, а не класс', () => {
    expect(css).toContain('@custom-variant dark')
    expect(css).toContain('[data-theme="dark"]')
  })

  it('токены Tailwind ссылаются на переменные, а не на значения', () => {
    expect(css).toContain('@theme inline')
    expect(css).toContain('--color-accent: var(--rp-accent)')
  })
})
```

- [ ] **Шаг 3: Запустить тест и убедиться, что он падает**

Выполнить: `cd frontend && pnpm install && pnpm --filter @repibot/ui test`
Ожидается: FAIL — файл `theme.css` не найден.

- [ ] **Шаг 4: Написать `theme.css`**

```css
@import 'tailwindcss';

/* Тёмная тема переключается атрибутом на корневом элементе: в MiniApp тему
   задаёт Telegram, и завязываться на класс там неудобно. */
@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));

:root {
  --rp-ink: #1A1A18;
  --rp-paper: #FAF9F7;
  --rp-jade: #17A67C;
  --rp-jade-deep: #0E6B50;
  --rp-jade-mist: #E4F5EE;

  --rp-bg: #FAF9F7;
  --rp-surface: #FFFFFF;
  --rp-surface-sunken: #F1F0EC;
  --rp-border: #E2E1DC;
  --rp-border-strong: #C9C7C0;

  --rp-text: #1A1A18;
  --rp-text-secondary: #575651;
  --rp-text-muted: #7A7873;
  --rp-text-accent: #0E6B50;

  --rp-accent: #17A67C;
  --rp-accent-hover: #128A67;
  --rp-on-accent: #FFFFFF;

  --rp-success: #2F9E44;
  --rp-warning: #B87A0B;
  --rp-danger: #C0392F;
  --rp-info: #2B72C4;

  --rp-radius-sm: 6px;
  --rp-radius: 10px;
  --rp-radius-lg: 16px;
  --rp-radius-full: 999px;

  --rp-shadow-sm: 0 1px 2px rgb(26 26 24 / 0.06);
  --rp-shadow: 0 4px 12px rgb(26 26 24 / 0.08);
  --rp-shadow-lg: 0 12px 32px rgb(26 26 24 / 0.12);
}

[data-theme="dark"] {
  --rp-ink: #F2F1ED;
  --rp-paper: #121311;

  --rp-bg: #121311;
  --rp-surface: #1C1D1B;
  --rp-surface-sunken: #0D0E0C;
  --rp-border: #2E2F2C;
  --rp-border-strong: #43443F;

  --rp-text: #F2F1ED;
  --rp-text-secondary: #A3A19A;
  --rp-text-muted: #7A7873;
  --rp-text-accent: #2CC694;

  --rp-accent: #2CC694;
  --rp-accent-hover: #45D6A8;
  --rp-on-accent: #08150F;

  --rp-jade-mist: #10322A;

  --rp-success: #51CF66;
  --rp-warning: #E8A32C;
  --rp-danger: #E8615A;
  --rp-info: #5AA3E8;

  /* В тёмной теме иерархию держат поверхность и граница, а не тень.
     Усиливать тень для компенсации не нужно — так задумано. */
  --rp-shadow-sm: 0 1px 2px rgb(0 0 0 / 0.4);
  --rp-shadow: 0 4px 12px rgb(0 0 0 / 0.5);
  --rp-shadow-lg: 0 12px 32px rgb(0 0 0 / 0.6);
}

/* inline обязателен: без него значения подставятся на этапе сборки
   и перестанут реагировать на смену темы. */
@theme inline {
  --color-bg: var(--rp-bg);
  --color-surface: var(--rp-surface);
  --color-surface-sunken: var(--rp-surface-sunken);
  --color-border-subtle: var(--rp-border);
  --color-border-strong: var(--rp-border-strong);

  --color-text: var(--rp-text);
  --color-text-secondary: var(--rp-text-secondary);
  --color-text-muted: var(--rp-text-muted);
  --color-text-accent: var(--rp-text-accent);

  --color-accent: var(--rp-accent);
  --color-accent-hover: var(--rp-accent-hover);
  --color-on-accent: var(--rp-on-accent);
  --color-jade-mist: var(--rp-jade-mist);

  --color-success: var(--rp-success);
  --color-warning: var(--rp-warning);
  --color-danger: var(--rp-danger);
  --color-info: var(--rp-info);

  --radius-sm: var(--rp-radius-sm);
  --radius-md: var(--rp-radius);
  --radius-lg: var(--rp-radius-lg);
  --radius-full: var(--rp-radius-full);

  --font-sans: 'Inter', system-ui, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}

body {
  background-color: var(--rp-bg);
  color: var(--rp-text);
  font-family: var(--font-sans);
}

/* Фокус всегда виден и всегда акцентного цвета — раздел 6 бренд-бука. */
:focus-visible {
  outline: 2px solid var(--rp-accent);
  outline-offset: 2px;
}
```

- [ ] **Шаг 5: Запустить тест токенов и убедиться, что он проходит**

Выполнить: `cd frontend && pnpm --filter @repibot/ui test`
Ожидается: PASS, 41 тест.

- [ ] **Шаг 6: Написать падающий тест кнопки**

`frontend/packages/ui/src/components/button.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Button } from './button'

describe('Button', () => {
  it('рендерит содержимое', () => {
    render(<Button>Купить</Button>)

    expect(screen.getByRole('button', { name: 'Купить' })).toBeInTheDocument()
  })

  it('основной вариант заливается акцентом', () => {
    render(<Button variant="primary">Купить</Button>)

    expect(screen.getByRole('button')).toHaveClass('bg-accent')
  })

  it('второстепенный вариант — без заливки, с границей', () => {
    render(<Button variant="secondary">Отмена</Button>)

    const button = screen.getByRole('button')
    expect(button).not.toHaveClass('bg-accent')
    expect(button.className).toContain('border')
  })

  it('мелкий размер использует тёмный текст на зелёном', () => {
    /* Белый на Jade даёт 3.4:1 и проходит только от 18-19 px.
       Для мелкой кнопки бренд-бук требует #08150F. */
    render(
      <Button variant="primary" size="sm">
        Ок
      </Button>,
    )

    expect(screen.getByRole('button').className).toContain('text-[#08150F]')
  })

  it('отключённая кнопка недоступна для нажатия', () => {
    render(<Button disabled>Купить</Button>)

    expect(screen.getByRole('button')).toBeDisabled()
  })
})
```

- [ ] **Шаг 7: Запустить тест и убедиться, что он падает**

Выполнить: `cd frontend && pnpm --filter @repibot/ui test`
Ожидается: FAIL — модуль `./button` не найден.

- [ ] **Шаг 8: Написать `lib/cn.ts` и компоненты**

`frontend/packages/ui/src/lib/cn.ts`:

```ts
import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...classes: ClassValue[]): string {
  return twMerge(clsx(classes))
}
```

`frontend/packages/ui/src/components/button.tsx`:

```tsx
import { Slot } from '@radix-ui/react-slot'
import { type VariantProps, cva } from 'class-variance-authority'
import type { ButtonHTMLAttributes } from 'react'

import { cn } from '../lib/cn'

const button = cva(
  'inline-flex items-center justify-center font-medium transition-colors disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        primary: 'bg-accent hover:bg-accent-hover',
        secondary: 'border border-border-strong text-text hover:bg-surface-sunken',
        ghost: 'text-text-accent hover:bg-jade-mist',
      },
      size: {
        // Мелкая кнопка получает тёмный текст: белый на Jade проходит
        // по контрасту только с 18-19 px. Раздел 7 бренд-бука.
        sm: 'h-8 px-3 text-sm rounded-sm text-[#08150F]',
        md: 'h-10 px-4 text-base rounded-md text-on-accent',
        lg: 'h-12 px-6 text-lg rounded-md text-on-accent',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof button> {
  asChild?: boolean
}

export function Button({ className, variant, size, asChild, ...props }: ButtonProps) {
  const Component = asChild ? Slot : 'button'
  return <Component className={cn(button({ variant, size }), className)} {...props} />
}
```

`frontend/packages/ui/src/components/input.tsx`:

```tsx
import type { InputHTMLAttributes } from 'react'

import { cn } from '../lib/cn'

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'h-10 w-full rounded-md border border-border-subtle bg-surface px-3 text-text',
        'placeholder:text-text-muted',
        // Кольцо от Jade Mist при фокусе — раздел 6 бренд-бука.
        'focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none',
        className,
      )}
      {...props}
    />
  )
}
```

`frontend/packages/ui/src/components/card.tsx`:

```tsx
import type { HTMLAttributes } from 'react'

import { cn } from '../lib/cn'

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-lg border border-border-subtle bg-surface p-6 shadow-[var(--rp-shadow-sm)]',
        className,
      )}
      {...props}
    />
  )
}
```

`frontend/packages/ui/src/index.ts`:

```ts
export { Button, type ButtonProps } from './components/button'
export { Card } from './components/card'
export { Input } from './components/input'
export { cn } from './lib/cn'
```

- [ ] **Шаг 9: Запустить тесты и убедиться, что они проходят**

Выполнить: `cd frontend && pnpm --filter @repibot/ui test && pnpm --filter @repibot/ui typecheck`
Ожидается: PASS, 46 тестов, typecheck без ошибок.

- [ ] **Шаг 10: Подключить шрифты локально**

Скачать шрифты в формате woff2 в `frontend/packages/ui/src/fonts/` и переименовать
по образцу ниже:

- Inter, начертания 400, 500, 600 — https://github.com/rsms/inter/releases (лицензия SIL OFL 1.1)
- JetBrains Mono, начертание 400 — https://github.com/JetBrains/JetBrainsMono/releases (лицензия SIL OFL 1.1)

Обе лицензии разрешают размещение файлов в репозитории открытого проекта.
Добавить в `theme.css` сразу после `@import 'tailwindcss';`:

```css
@font-face {
  font-family: 'Inter';
  src: url('./fonts/inter-400.woff2') format('woff2');
  font-weight: 400;
  font-display: swap;
}
@font-face {
  font-family: 'Inter';
  src: url('./fonts/inter-500.woff2') format('woff2');
  font-weight: 500;
  font-display: swap;
}
@font-face {
  font-family: 'Inter';
  src: url('./fonts/inter-600.woff2') format('woff2');
  font-weight: 600;
  font-display: swap;
}
@font-face {
  font-family: 'JetBrains Mono';
  src: url('./fonts/jetbrains-mono-400.woff2') format('woff2');
  font-weight: 400;
  font-display: swap;
}
```

Шрифты берутся локально, а не с внешнего CDN: у проекта аудитория, для которой обращение к стороннему домену на каждой загрузке нежелательно.

- [ ] **Шаг 11: Коммит**

```bash
git add frontend/packages/ui frontend/pnpm-lock.yaml
git commit -m "feat: пакет UI с токенами бренд-бука и базовыми компонентами"
```

---

### Задача 11: Пакет `@repibot/core` — клиент API, кэш запросов и переводы

**Файлы:**
- Создать: `frontend/packages/core/package.json`, `tsconfig.json`, `vitest.config.ts`
- Создать: `frontend/packages/core/src/api/client.ts`, `src/query.ts`
- Создать: `frontend/packages/core/src/i18n/{index.ts,ru.ts,en.ts,detect.ts}`
- Создать: `frontend/packages/core/src/index.ts`
- Создать: `tools/export_openapi.py`
- Создать генерацией: `frontend/packages/core/src/api/openapi.json`, `src/api/schema.d.ts`
- Тест: `frontend/packages/core/src/i18n/i18n.test.ts`, `src/api/client.test.ts`

**Интерфейсы:**
- Отдаёт: `createApiClient(baseUrl: string, getToken: () => string | null)` — клиент `openapi-fetch` с заголовком `Authorization`; `createQueryClient(): QueryClient`; `translate(language: Language, key: TranslationKey): string`; `detectLanguage(candidates: readonly string[]): Language`; тип `Language = 'ru' | 'en'`; тип `TranslationKey` — ключи словаря `ru`.

- [ ] **Шаг 1: Написать выгрузку схемы OpenAPI**

`tools/export_openapi.py`:

```python
"""Выгружает схему FastAPI в файл.

Генерация типов фронтенда не должна требовать поднятого бэкенда: в CI и при
сборке образа его нет. Схема коммитится, расхождение ловится отдельной проверкой.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "frontend/packages/core/src/api/openapi.json"


def main() -> int:
    from repibot_api.main import create_app

    schema = create_app().openapi()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Схема записана: {TARGET.relative_to(ROOT)}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Добавить в `[project.scripts]` корневого `pyproject.toml`:

```toml
export-openapi = "tools.export_openapi:main"
```

Выполнить: `uv run export-openapi`
Ожидается: файл `frontend/packages/core/src/api/openapi.json` создан.

- [ ] **Шаг 2: Создать пакет**

`frontend/packages/core/package.json`:

```json
{
  "name": "@repibot/core",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "exports": { ".": "./src/index.ts" },
  "scripts": {
    "gen:api": "openapi-typescript ./src/api/openapi.json -o ./src/api/schema.d.ts",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.66.0",
    "openapi-fetch": "^0.13.0",
    "zod": "^3.24.0"
  },
  "peerDependencies": { "react": "^19.0.0" },
  "devDependencies": {
    "@repibot/config": "workspace:*",
    "@types/react": "^19.0.0",
    "openapi-typescript": "^7.6.0",
    "react": "^19.0.0",
    "vitest": "^3.0.0"
  }
}
```

`frontend/packages/core/tsconfig.json`:

```json
{
  "extends": "@repibot/config/tsconfig.base.json",
  "include": ["src"]
}
```

`frontend/packages/core/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'

export default defineConfig({ test: { environment: 'node', globals: true } })
```

Выполнить: `cd frontend && pnpm install && pnpm --filter @repibot/core gen:api`
Ожидается: создан `src/api/schema.d.ts`.

- [ ] **Шаг 3: Написать падающие тесты**

`frontend/packages/core/src/i18n/i18n.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { detectLanguage, translate } from './index'
import { en } from './en'
import { ru } from './ru'

describe('переводы', () => {
  it('возвращает строку выбранного языка', () => {
    expect(translate('ru', 'common.loading')).toBe(ru['common.loading'])
    expect(translate('en', 'common.loading')).toBe(en['common.loading'])
  })

  it('английский словарь покрывает все ключи русского', () => {
    /* Пропущенный ключ иначе всплывёт у пользователя как строка вида
       common.loading вместо текста. */
    expect(Object.keys(en).sort()).toEqual(Object.keys(ru).sort())
  })

  it('ни одно значение не пустое', () => {
    for (const [key, value] of Object.entries({ ...ru, ...en })) {
      expect(value.trim(), `пустой перевод: ${key}`).not.toBe('')
    }
  })
})

describe('определение языка', () => {
  it('берёт первый поддерживаемый из списка', () => {
    expect(detectLanguage(['de-DE', 'en-US', 'ru'])).toBe('en')
  })

  it('понимает код с регионом', () => {
    expect(detectLanguage(['ru-RU'])).toBe('ru')
  })

  it('падает обратно на русский, когда ничего не подходит', () => {
    expect(detectLanguage(['de', 'fr'])).toBe('ru')
  })

  it('переживает пустой список', () => {
    expect(detectLanguage([])).toBe('ru')
  })
})
```

`frontend/packages/core/src/api/client.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createApiClient } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('клиент API', () => {
  it('добавляет заголовок авторизации, когда токен есть', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const client = createApiClient('https://example.org', () => 'token-123')
    await client.GET('/health')

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.headers.get('authorization')).toBe('Bearer token-123')
  })

  it('не добавляет заголовок, когда токена нет', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const client = createApiClient('https://example.org', () => null)
    await client.GET('/health')

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.headers.get('authorization')).toBeNull()
  })
})
```

- [ ] **Шаг 4: Запустить тесты и убедиться, что они падают**

Выполнить: `cd frontend && pnpm --filter @repibot/core test`
Ожидается: FAIL — модули не найдены.

- [ ] **Шаг 5: Написать словари и определение языка**

`frontend/packages/core/src/i18n/ru.ts`:

```ts
export const ru = {
  'common.loading': 'Загрузка',
  'common.error': 'Что-то пошло не так',
  'common.retry': 'Повторить',
  'common.language': 'Язык',
  'common.theme': 'Тема',
  'home.title': 'Re:Pibot',
  'home.subtitle': 'Магазин ещё готовится',
} as const

export type TranslationKey = keyof typeof ru
```

`frontend/packages/core/src/i18n/en.ts`:

```ts
import type { TranslationKey } from './ru'

export const en: Record<TranslationKey, string> = {
  'common.loading': 'Loading',
  'common.error': 'Something went wrong',
  'common.retry': 'Retry',
  'common.language': 'Language',
  'common.theme': 'Theme',
  'home.title': 'Re:Pibot',
  'home.subtitle': 'The shop is still being built',
}
```

`frontend/packages/core/src/i18n/index.ts`:

```ts
import { en } from './en'
import { type TranslationKey, ru } from './ru'

export type Language = 'ru' | 'en'
export type { TranslationKey }
export { en, ru }

const DICTIONARIES: Record<Language, Record<TranslationKey, string>> = { ru, en }
const SUPPORTED: readonly Language[] = ['ru', 'en']
const FALLBACK: Language = 'ru'

export function translate(language: Language, key: TranslationKey): string {
  return DICTIONARIES[language][key]
}

/**
 * Выбирает первый поддерживаемый язык из списка предпочтений.
 * Принимает коды как с регионом (ru-RU), так и без.
 */
export function detectLanguage(candidates: readonly string[]): Language {
  for (const candidate of candidates) {
    const code = candidate.toLowerCase().split('-')[0]
    const match = SUPPORTED.find((language) => language === code)
    if (match) return match
  }
  return FALLBACK
}
```

- [ ] **Шаг 6: Написать клиент API и настройки кэша**

`frontend/packages/core/src/api/client.ts`:

```ts
import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from './schema'

/**
 * Клиент нашего API. Токен читается функцией, а не передаётся значением:
 * в MiniApp он живёт в памяти и меняется при переоткрытии приложения.
 */
export function createApiClient(baseUrl: string, getToken: () => string | null) {
  const client = createClient<paths>({ baseUrl })

  const auth: Middleware = {
    async onRequest({ request }) {
      const token = getToken()
      if (token) request.headers.set('Authorization', `Bearer ${token}`)
      return request
    },
  }

  client.use(auth)
  return client
}
```

`frontend/packages/core/src/query.ts`:

```ts
import { QueryClient } from '@tanstack/react-query'

/**
 * Общие настройки кэша. Повторять запрос при ошибке авторизации бессмысленно —
 * токен от этого не появится.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failureCount, error) => {
          const status = (error as { status?: number }).status
          if (status === 401 || status === 403) return false
          return failureCount < 2
        },
      },
    },
  })
}
```

`frontend/packages/core/src/index.ts`:

```ts
export { createApiClient } from './api/client'
export {
  type Language,
  type TranslationKey,
  detectLanguage,
  en,
  ru,
  translate,
} from './i18n/index'
export { createQueryClient } from './query'
```

- [ ] **Шаг 7: Запустить тесты и убедиться, что они проходят**

Выполнить: `cd frontend && pnpm --filter @repibot/core test && pnpm --filter @repibot/core typecheck`
Ожидается: PASS, девять тестов.

- [ ] **Шаг 8: Коммит**

```bash
git add frontend/packages/core tools/export_openapi.py pyproject.toml frontend/pnpm-lock.yaml
git commit -m "feat: пакет core с клиентом API, кэшем запросов и переводами"
```

---

### Задача 12: MiniApp

**Файлы:**
- Создать: `frontend/apps/miniapp/package.json`, `vite.config.ts`, `tsconfig.json`, `vitest.config.ts`, `index.html`
- Создать: `frontend/apps/miniapp/src/{main.tsx,router.tsx,styles.css}`
- Создать: `frontend/apps/miniapp/src/telegram.ts`
- Создать: `frontend/apps/miniapp/src/routes/{root.tsx,index.tsx}`
- Тест: `frontend/apps/miniapp/src/telegram.test.ts`

**Интерфейсы:**
- Потребляет: `@repibot/ui` (`Button`, `Card`, `theme.css`), `@repibot/core` (`detectLanguage`, `translate`, `createQueryClient`).
- Отдаёт: `readInitData(): string | null`; `applyTelegramTheme(): void`; `isInsideTelegram(): boolean`.

- [ ] **Шаг 1: Создать приложение**

`frontend/apps/miniapp/package.json`:

```json
{
  "name": "@repibot/miniapp",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "@repibot/core": "workspace:*",
    "@repibot/ui": "workspace:*",
    "@tanstack/react-query": "^5.66.0",
    "@tanstack/react-router": "^1.95.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "zustand": "^5.0.0"
  },
  "devDependencies": {
    "@repibot/config": "workspace:*",
    "@tailwindcss/vite": "^4.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^5.0.0",
    "jsdom": "^26.0.0",
    "tailwindcss": "^4.0.0",
    "vite": "^8.0.0",
    "vitest": "^3.0.0"
  }
}
```

`frontend/apps/miniapp/vite.config.ts`:

```ts
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  // Приложение отдаётся Nginx по пути /app, а не с корня домена.
  base: '/app/',
  plugins: [react(), tailwindcss()],
  build: { outDir: 'dist', sourcemap: true },
})
```

`frontend/apps/miniapp/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'

export default defineConfig({ test: { environment: 'jsdom', globals: true } })
```

`frontend/apps/miniapp/tsconfig.json`:

```json
{
  "extends": "@repibot/config/tsconfig.base.json",
  "include": ["src", "vite.config.ts", "vitest.config.ts"]
}
```

`frontend/apps/miniapp/index.html`:

```html
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <title>Re:Pibot</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Скрипт Telegram — единственное внешнее подключение во всём проекте, и оно вынужденное: SDK обязан загружаться с домена Telegram, самостоятельная копия ломает работу внутри клиента. Атрибут `integrity` здесь не ставится осознанно: Telegram обновляет файл по тому же адресу без версионирования, и любой их выпуск немедленно уронил бы загрузку MiniApp. Компенсация — жёсткий `script-src` в CSP (задача 15), разрешающий ровно `telegram.org` и ничего больше.

- [ ] **Шаг 2: Написать падающий тест**

`frontend/apps/miniapp/src/telegram.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'

import { applyTelegramTheme, isInsideTelegram, readInitData } from './telegram'

afterEach(() => {
  vi.unstubAllGlobals()
  document.documentElement.removeAttribute('data-theme')
})

function stubTelegram(webApp: Record<string, unknown>): void {
  vi.stubGlobal('Telegram', { WebApp: webApp })
}

describe('интеграция с Telegram', () => {
  it('читает initData, когда приложение открыто внутри Telegram', () => {
    stubTelegram({ initData: 'query_id=AAA&user=%7B%22id%22%3A1%7D', ready: vi.fn() })

    expect(readInitData()).toBe('query_id=AAA&user=%7B%22id%22%3A1%7D')
  })

  it('возвращает null в обычном браузере', () => {
    expect(readInitData()).toBeNull()
  })

  it('пустую строку initData не выдаёт за валидную', () => {
    /* Telegram отдаёт пустую строку, когда приложение открыто не из бота —
       принять её за подтверждение личности нельзя. */
    stubTelegram({ initData: '', ready: vi.fn() })

    expect(readInitData()).toBeNull()
  })

  it('определяет запуск внутри Telegram', () => {
    stubTelegram({ initData: 'x', ready: vi.fn() })
    expect(isInsideTelegram()).toBe(true)
  })

  it('переносит тёмную тему Telegram на корневой элемент', () => {
    stubTelegram({ initData: 'x', colorScheme: 'dark', ready: vi.fn() })

    applyTelegramTheme()

    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('вне Telegram тему не трогает', () => {
    applyTelegramTheme()

    expect(document.documentElement.dataset.theme).toBeUndefined()
  })
})
```

- [ ] **Шаг 3: Запустить тест и убедиться, что он падает**

Выполнить: `cd frontend && pnpm --filter @repibot/miniapp test`
Ожидается: FAIL — модуль `./telegram` не найден.

- [ ] **Шаг 4: Написать `src/telegram.ts`**

```ts
/**
 * Тонкая обёртка над Telegram WebApp SDK.
 *
 * Обмен initData на токен появится в подпроекте 1. Здесь только чтение
 * и применение темы — этого достаточно, чтобы убедиться, что MiniApp
 * действительно открывается внутри Telegram.
 */

interface TelegramWebApp {
  initData?: string
  colorScheme?: 'light' | 'dark'
  ready?: () => void
  expand?: () => void
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

function webApp(): TelegramWebApp | undefined {
  return window.Telegram?.WebApp
}

export function readInitData(): string | null {
  const data = webApp()?.initData
  return data ? data : null
}

export function isInsideTelegram(): boolean {
  return readInitData() !== null
}

export function applyTelegramTheme(): void {
  const scheme = webApp()?.colorScheme
  if (!scheme) return
  document.documentElement.dataset.theme = scheme
}

export function initTelegram(): void {
  const app = webApp()
  app?.ready?.()
  app?.expand?.()
  applyTelegramTheme()
}
```

- [ ] **Шаг 5: Написать маршруты и точку входа**

`frontend/apps/miniapp/src/styles.css`:

```css
@import '@repibot/ui/theme.css';
```

`frontend/apps/miniapp/src/routes/root.tsx`:

```tsx
import { Outlet, createRootRoute } from '@tanstack/react-router'

export const rootRoute = createRootRoute({
  component: () => (
    <div className="min-h-dvh bg-bg p-4 text-text">
      <Outlet />
    </div>
  ),
})
```

`frontend/apps/miniapp/src/routes/index.tsx`:

```tsx
import { translate } from '@repibot/core'
import { Card } from '@repibot/ui'
import { createRoute } from '@tanstack/react-router'

import { isInsideTelegram } from '../telegram'
import { rootRoute } from './root'

export function Home() {
  return (
    <Card className="mx-auto max-w-md">
      <h1 className="text-2xl font-semibold">{translate('ru', 'home.title')}</h1>
      <p className="mt-2 text-text-secondary">{translate('ru', 'home.subtitle')}</p>
      <p className="mt-4 font-mono text-sm text-text-muted">
        {isInsideTelegram() ? 'Telegram: подключён' : 'Telegram: вне приложения'}
      </p>
    </Card>
  )
}

export const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: Home })
```

`frontend/apps/miniapp/src/router.tsx`:

```tsx
import { createRouter } from '@tanstack/react-router'

import { indexRoute } from './routes/index'
import { rootRoute } from './routes/root'

export const router = createRouter({
  routeTree: rootRoute.addChildren([indexRoute]),
  basepath: '/app',
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
```

`frontend/apps/miniapp/src/main.tsx`:

```tsx
import { createQueryClient } from '@repibot/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { router } from './router'
import './styles.css'
import { initTelegram } from './telegram'

initTelegram()

const container = document.getElementById('root')
if (!container) throw new Error('в разметке нет элемента #root')

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
```

- [ ] **Шаг 6: Написать тест рендера главной**

Нужны зависимости `@testing-library/react`, `@testing-library/jest-dom` и файл
`vitest.setup.ts` с содержимым `import '@testing-library/jest-dom/vitest'`;
подключить его в `vitest.config.ts` через `setupFiles: ['./vitest.setup.ts']`.

`frontend/apps/miniapp/src/routes/index.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Home } from './index'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('главная MiniApp', () => {
  it('показывает название и подзаголовок', () => {
    render(<Home />)

    expect(screen.getByRole('heading', { name: 'Re:Pibot' })).toBeInTheDocument()
    expect(screen.getByText('Магазин ещё готовится')).toBeInTheDocument()
  })

  it('сообщает, что открыт вне Telegram, когда SDK недоступен', () => {
    render(<Home />)

    expect(screen.getByText('Telegram: вне приложения')).toBeInTheDocument()
  })

  it('сообщает о подключении, когда initData получен', () => {
    vi.stubGlobal('Telegram', { WebApp: { initData: 'query_id=AAA' } })

    render(<Home />)

    expect(screen.getByText('Telegram: подключён')).toBeInTheDocument()
  })
})
```

- [ ] **Шаг 7: Запустить тесты и сборку**

Выполнить: `cd frontend && pnpm --filter @repibot/miniapp test && pnpm --filter @repibot/miniapp typecheck && pnpm --filter @repibot/miniapp build`
Ожидается: девять тестов PASS, typecheck чистый, сборка создаёт `dist/index.html`.

- [ ] **Шаг 8: Коммит**

```bash
git add frontend/apps/miniapp frontend/pnpm-lock.yaml
git commit -m "feat: каркас MiniApp на Vite с интеграцией Telegram WebApp"
```

---

### Задача 13: Веб-приложение и сквозной тест

**Файлы:**
- Создать: `frontend/apps/web/package.json`, `next.config.ts`, `tsconfig.json`, `postcss.config.mjs`, `playwright.config.ts`
- Создать: `frontend/apps/web/src/app/{layout.tsx,page.tsx,globals.css}`
- Создать: `frontend/apps/web/src/app/legal/[slug]/page.tsx`
- Создать: `frontend/apps/web/src/app/admin/{layout.tsx,page.tsx}`
- Создать: `frontend/apps/web/src/components/{theme-toggle.tsx,wordmark.tsx}`
- Тест: `frontend/apps/web/src/components/wordmark.test.tsx`, `frontend/apps/web/e2e/smoke.spec.ts`

**Интерфейсы:**
- Потребляет: `@repibot/ui` (`Button`, `Card`, `theme.css`), `@repibot/core` (`translate`).
- Отдаёт: `Wordmark` — компонент вордмарка; `ThemeToggle` — переключатель темы, пишущий `data-theme` на `<html>`.

- [ ] **Шаг 1: Создать приложение**

`frontend/apps/web/package.json`:

```json
{
  "name": "@repibot/web",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "e2e": "playwright test"
  },
  "dependencies": {
    "@repibot/core": "workspace:*",
    "@repibot/ui": "workspace:*",
    "@tanstack/react-query": "^5.66.0",
    "next": "^16.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.50.0",
    "@repibot/config": "workspace:*",
    "@tailwindcss/postcss": "^4.0.0",
    "@testing-library/jest-dom": "^6.6.0",
    "@testing-library/react": "^16.1.0",
    "@types/node": "^24.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "jsdom": "^26.0.0",
    "tailwindcss": "^4.0.0",
    "vitest": "^3.0.0"
  }
}
```

`frontend/apps/web/next.config.ts`:

```ts
import type { NextConfig } from 'next'

const config: NextConfig = {
  // standalone нужен образу: он забирает только необходимое,
  // а не весь node_modules размером в сотни мегабайт.
  output: 'standalone',
  transpilePackages: ['@repibot/ui', '@repibot/core'],
}

export default config
```

`frontend/apps/web/postcss.config.mjs`:

```js
export default { plugins: { '@tailwindcss/postcss': {} } }
```

`frontend/apps/web/tsconfig.json`:

```json
{
  "extends": "@repibot/config/tsconfig.base.json",
  "compilerOptions": {
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src", "next-env.d.ts", ".next/types/**/*.ts"]
}
```

`frontend/apps/web/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: { environment: 'jsdom', globals: true, setupFiles: ['./vitest.setup.ts'], include: ['src/**/*.test.tsx'] },
})
```

`frontend/apps/web/vitest.setup.ts`:

```ts
import '@testing-library/jest-dom/vitest'
```

- [ ] **Шаг 2: Написать падающий тест вордмарка**

`frontend/apps/web/src/components/wordmark.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Wordmark } from './wordmark'

describe('Wordmark', () => {
  it('пишется строчными', () => {
    render(<Wordmark />)

    expect(screen.getByText(/re/).textContent).toBe('re')
  })

  it('двоеточие вынесено отдельным элементом в цвете акцента', () => {
    /* Двоеточие — часть марки, а не пунктуация: раздел 5 бренд-бука
       запрещает убирать его или красить в основной цвет. */
    render(<Wordmark />)

    const colon = screen.getByText(':')
    expect(colon).toBeInTheDocument()
    expect(colon.className).toContain('text-accent')
  })

  it('целиком читается как re:pibot', () => {
    const { container } = render(<Wordmark />)

    expect(container.textContent).toBe('re:pibot')
  })
})
```

- [ ] **Шаг 3: Запустить тест и убедиться, что он падает**

Выполнить: `cd frontend && pnpm --filter @repibot/web test`
Ожидается: FAIL — модуль `./wordmark` не найден.

- [ ] **Шаг 4: Написать компоненты**

`frontend/apps/web/src/components/wordmark.tsx`:

```tsx
/**
 * Вордмарк. Двоеточие — отдельный элемент в цвете Jade: по бренд-буку это
 * часть марки, его нельзя убрать, заменить дефисом или перекрасить.
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={`font-medium tracking-[-0.03em] lowercase ${className ?? ''}`}>
      <span>re</span>
      <span className="text-accent">:</span>
      <span>pibot</span>
    </span>
  )
}
```

`frontend/apps/web/src/components/theme-toggle.tsx`:

```tsx
'use client'

import { Button } from '@repibot/ui'
import { useEffect, useState } from 'react'

type Theme = 'light' | 'dark'

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>('light')

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  return (
    <Button
      variant="secondary"
      size="md"
      onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
    >
      {theme === 'light' ? 'Тёмная тема' : 'Светлая тема'}
    </Button>
  )
}
```

- [ ] **Шаг 5: Написать страницы**

`frontend/apps/web/src/app/globals.css`:

```css
@import '@repibot/ui/theme.css';
```

`frontend/apps/web/src/app/layout.tsx`:

```tsx
import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import './globals.css'

export const metadata: Metadata = {
  title: 'Re:Pibot',
  description: 'Магазин VPN-подписок',
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru" data-theme="light">
      <body>{children}</body>
    </html>
  )
}
```

`frontend/apps/web/src/app/page.tsx`:

```tsx
import { Card } from '@repibot/ui'

import { ThemeToggle } from '@/components/theme-toggle'
import { Wordmark } from '@/components/wordmark'

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-6 p-6">
      <Wordmark className="text-5xl" />
      <Card>
        <h1 className="text-2xl font-semibold">Магазин ещё готовится</h1>
        <p className="mt-2 text-text-secondary">
          Здесь появятся тарифы, подписка и личный кабинет.
        </p>
      </Card>
      <ThemeToggle />
    </main>
  )
}
```

`frontend/apps/web/src/app/legal/[slug]/page.tsx`:

```tsx
import { Card } from '@repibot/ui'

/**
 * Юридические документы. В подпроекте 4 содержимое поедет из таблицы
 * legal_documents; сейчас маршрут существует, чтобы ссылки в подвале не вели в 404.
 */
export default async function LegalPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params

  return (
    <main className="mx-auto max-w-2xl p-6">
      <Card>
        <h1 className="text-2xl font-semibold">Документ: {slug}</h1>
        <p className="mt-2 text-text-secondary">Текст документа появится позже.</p>
      </Card>
    </main>
  )
}
```

`frontend/apps/web/src/app/admin/layout.tsx`:

```tsx
import type { ReactNode } from 'react'

/**
 * Отдельный сегмент админки. Проверка роли появится в подпроекте 1 —
 * сейчас это только каркас, и снаружи он не опубликован.
 */
export default function AdminLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-dvh bg-surface-sunken">{children}</div>
}
```

`frontend/apps/web/src/app/admin/page.tsx`:

```tsx
export default function AdminPage() {
  return <main className="p-6 text-text">Админка появится в подпроекте 5.</main>
}
```

- [ ] **Шаг 6: Подключить фирменные изображения**

Скопировать плашки в статику обоих приложений:

```bash
mkdir -p frontend/apps/web/public/brand frontend/apps/miniapp/public/brand
cp docs/design/logo-light.png frontend/apps/web/public/brand/
cp docs/design/logo-dark.png frontend/apps/web/public/brand/
cp docs/design/logo-light.png frontend/apps/miniapp/public/brand/
cp docs/design/logo-dark.png frontend/apps/miniapp/public/brand/
cp docs/design/logo-light.png frontend/apps/web/public/favicon.png
```

Лок-ап собирается из плашки и текстового вордмарка, а не берётся готовым
растром: `lock-up-dark.png` существует только для светлого фона, а версии для
тёмной темы в бренд-паке нет — `lock-up-light.png` целиком в Jade и на тёмном
даёт мутное пятно. Текстовый вордмарк решает это сам: он наследует цвет темы,
а двоеточие остаётся акцентным в обоих случаях.

`frontend/apps/web/src/components/lockup.tsx`:

```tsx
import { Wordmark } from './wordmark'

/**
 * Горизонтальный лок-ап: знак слева, вордмарк справа.
 * Просвет равен высоте строчной буквы — раздел 5 бренд-бука.
 * Плашка меняется вместе с темой: на светлой — Jade, на тёмной — Ink.
 */
export function Lockup({ size = 40 }: { size?: number }) {
  return (
    <div className="flex items-center gap-[0.5em]">
      <img
        src="/brand/logo-light.png"
        alt=""
        width={size}
        height={size}
        className="rounded-lg dark:hidden"
      />
      <img
        src="/brand/logo-dark.png"
        alt=""
        width={size}
        height={size}
        className="hidden rounded-lg dark:block"
      />
      <Wordmark className="text-3xl" />
    </div>
  )
}
```

В `frontend/apps/web/src/app/layout.tsx` добавить иконку в метаданные:

```tsx
export const metadata: Metadata = {
  title: 'Re:Pibot',
  description: 'Магазин VPN-подписок',
  icons: { icon: '/favicon.png' },
}
```

В `frontend/apps/web/src/app/page.tsx` заменить строку `<Wordmark className="text-5xl" />`
на `<Lockup size={48} />` и добавить импорт `import { Lockup } from '@/components/lockup'`.

- [ ] **Шаг 7: Написать сквозной тест**

`frontend/apps/web/playwright.config.ts`:

```ts
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://127.0.0.1:3000' },
  webServer: {
    command: 'pnpm build && pnpm start',
    url: 'http://127.0.0.1:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
})
```

`frontend/apps/web/e2e/smoke.spec.ts`:

```ts
import { expect, test } from '@playwright/test'

/**
 * Единственный сквозной сценарий этого подпроекта: страница собирается,
 * отдаётся и переключает тему. Сценарии регистрации и покупки появятся,
 * когда появятся регистрация и покупка.
 */
test('главная открывается и переключает тему', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByText('Магазин ещё готовится')).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')

  await page.getByRole('button', { name: 'Тёмная тема' }).click()

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})

test('страница юридического документа не отдаёт 404', async ({ page }) => {
  const response = await page.goto('/legal/terms')

  expect(response?.status()).toBe(200)
  await expect(page.getByText('Документ: terms')).toBeVisible()
})
```

- [ ] **Шаг 8: Запустить проверки**

Выполнить:
```bash
cd frontend
pnpm --filter @repibot/web test
pnpm --filter @repibot/web typecheck
pnpm --filter @repibot/web exec playwright install --with-deps chromium
pnpm --filter @repibot/web e2e
```
Ожидается: три модульных теста PASS, typecheck чистый, два сквозных сценария PASS.

Сквозные тесты в общую команду `uv run check` не добавляются: они поднимают сборку и занимают минуты. Их место — отдельный шаг CI.

- [ ] **Шаг 9: Прогнать общую проверку и закоммитить**

Выполнить: `uv run check`
Ожидается: код выхода 0 — теперь все семь проверок проходят.

```bash
git add frontend/apps/web frontend/pnpm-lock.yaml
git commit -m "feat: веб-приложение на Next.js с вордмарком, темой и сквозным тестом"
```

---

### Задача 14: Образы Docker

**Файлы:**
- Создать: `docker/backend.Dockerfile`, `docker/web.Dockerfile`, `docker/nginx.Dockerfile`
- Создать: `.dockerignore`
- Тест: `tools/tests/test_dockerfiles.py`

**Интерфейсы:**
- Отдаёт: образ `backend` с виртуальным окружением в `/app/.venv` и точками входа `repibot-api`, `repibot-bot`, `repibot-worker`, `alembic`; образ `web` со standalone-сборкой Next.js на порту 3000; образ `nginx` со встроенной статикой MiniApp в `/usr/share/nginx/html/app`.

- [ ] **Шаг 1: Написать падающий тест**

`tools/tests/test_dockerfiles.py`:

```python
"""Инварианты образов проверяются чтением файлов: сборка в тестах слишком дорога.

Эти проверки ловят ровно те ошибки, которые иначе всплывают на продакшене:
образ от root, отсутствие кеша слоёв, забытый .dockerignore.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKER = ROOT / "docker"


@pytest.fixture(scope="module")
def backend() -> str:
    return (DOCKER / "backend.Dockerfile").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def web() -> str:
    return (DOCKER / "web.Dockerfile").read_text(encoding="utf-8")


def test_backend_is_multi_stage(backend: str) -> None:
    assert backend.count("FROM ") >= 2


def test_backend_installs_dependencies_before_copying_sources(backend: str) -> None:
    """Иначе правка одной строки кода пересобирает все зависимости заново."""
    deps_install = backend.index("--no-install-project")
    full_copy = backend.index("COPY . .")

    assert deps_install < full_copy


def test_backend_does_not_install_dev_dependencies(backend: str) -> None:
    assert "--no-dev" in backend


def test_backend_runs_as_non_root(backend: str) -> None:
    assert "USER " in backend
    assert "USER root" not in backend


def test_web_uses_standalone_output(web: str) -> None:
    assert ".next/standalone" in web


def test_web_runs_as_non_root(web: str) -> None:
    assert "USER " in web


def test_dockerignore_excludes_heavy_and_secret_paths() -> None:
    ignored = set((ROOT / ".dockerignore").read_text(encoding="utf-8").split())

    for entry in (".git", ".venv", "node_modules", ".env", "docs"):
        assert entry in ignored, f"{entry} не исключён из контекста сборки"
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Выполнить: `uv run pytest tools/tests/test_dockerfiles.py -v`
Ожидается: FAIL — `FileNotFoundError` на `docker/backend.Dockerfile`.

- [ ] **Шаг 3: Написать `.dockerignore`**

```
.git
.github
.venv
node_modules
**/node_modules
**/dist
**/.next
.env
.env.*
docs
**/__pycache__
**/.pytest_cache
**/.ruff_cache
**/.mypy_cache
**/test-results
**/playwright-report
```

- [ ] **Шаг 4: Написать `docker/backend.Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1

# Один образ на три процесса: api, bot и worker различаются только командой.
# Пересборка одна, поведение предсказуемое.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Сначала только манифесты: слой с зависимостями переживает правку кода.
COPY pyproject.toml uv.lock ./
COPY backend/core/pyproject.toml backend/core/
COPY backend/api/pyproject.toml backend/api/
COPY backend/bot/pyproject.toml backend/bot/
COPY backend/worker/pyproject.toml backend/worker/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.13-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --system repibot && useradd --system --gid repibot --home /app repibot

WORKDIR /app

COPY --from=builder --chown=repibot:repibot /app /app

USER repibot

# Команда задаётся в compose: uvicorn для api, python -m для бота,
# taskiq worker и scheduler для воркера, alembic для миграций.
CMD ["uvicorn", "repibot_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Шаг 5: Написать `docker/web.Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1

FROM node:24-alpine AS builder

ENV PNPM_HOME=/pnpm
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

WORKDIR /repo

COPY frontend/pnpm-workspace.yaml frontend/pnpm-lock.yaml frontend/package.json frontend/.npmrc ./
COPY frontend/packages/config/package.json packages/config/
COPY frontend/packages/core/package.json packages/core/
COPY frontend/packages/ui/package.json packages/ui/
COPY frontend/apps/web/package.json apps/web/

RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --filter @repibot/web...

COPY frontend/ ./

RUN pnpm --filter @repibot/web build


FROM node:24-alpine AS runtime

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app

# standalone забирает только реально нужные модули вместо всего node_modules.
COPY --from=builder --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=node:node /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=node:node /repo/apps/web/public ./apps/web/public

USER node

EXPOSE 3000

CMD ["node", "apps/web/server.js"]
```

Создать пустую директорию `frontend/apps/web/public/.gitkeep` — без неё последняя команда COPY упадёт.

- [ ] **Шаг 6: Написать `docker/nginx.Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1

# Статика MiniApp собирается здесь же и уезжает внутрь образа nginx:
# отдельный контейнер ради набора файлов не нужен.
FROM node:24-alpine AS miniapp

ENV PNPM_HOME=/pnpm
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

WORKDIR /repo

COPY frontend/pnpm-workspace.yaml frontend/pnpm-lock.yaml frontend/package.json frontend/.npmrc ./
COPY frontend/packages/config/package.json packages/config/
COPY frontend/packages/core/package.json packages/core/
COPY frontend/packages/ui/package.json packages/ui/
COPY frontend/apps/miniapp/package.json apps/miniapp/

RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --filter @repibot/miniapp...

COPY frontend/ ./

RUN pnpm --filter @repibot/miniapp build


FROM nginx:1.27-alpine AS runtime

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=miniapp /repo/apps/miniapp/dist /usr/share/nginx/html/app

EXPOSE 80
```

- [ ] **Шаг 7: Запустить тесты и убедиться, что они проходят**

Выполнить: `uv run pytest tools/tests/test_dockerfiles.py -v`
Ожидается: PASS, семь тестов.

- [ ] **Шаг 8: Коммит**

```bash
git add docker .dockerignore tools/tests/test_dockerfiles.py frontend/apps/web/public
git commit -m "feat: образы Docker для бэкенда, веба и nginx со статикой MiniApp"
```

---

### Задача 15: Nginx, Compose и переменные окружения

**Файлы:**
- Создать: `docker/nginx.conf`
- Создать: `compose.yml`, `compose.local-panel.yml`
- Создать: `.env.example`
- Тест: `tools/tests/test_compose.py`, `tools/tests/test_nginx_conf.py`

**Интерфейсы:**
- Отдаёт: сервисы `nginx`, `web`, `api`, `bot`, `worker`, `scheduler`, `migrate`, `postgres`, `valkey`; маршруты `/`, `/app`, `/api`, `/tg/webhook`.

- [ ] **Шаг 1: Написать падающие тесты**

`tools/tests/test_compose.py`:

```python
"""Инварианты развёртывания. Проверяются разбором compose.yml.

Ошибки в этом файле дают самые дорогие отказы: миграции наперегонки,
сервис без ограничения перезапуска, секрет, попавший в репозиторий.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yml").read_text(encoding="utf-8"))


def test_all_expected_services_are_declared(compose: dict) -> None:
    expected = {
        "nginx", "web", "api", "bot", "worker", "scheduler", "migrate", "postgres", "valkey"
    }

    assert expected <= set(compose["services"])


def test_application_services_wait_for_migrations(compose: dict) -> None:
    """Три процесса, стартующие одновременно, иначе дерутся за блокировку Alembic."""
    for service in ("api", "bot", "worker"):
        depends = compose["services"][service]["depends_on"]
        assert depends["migrate"]["condition"] == "service_completed_successfully"


def test_migrate_waits_for_healthy_database(compose: dict) -> None:
    depends = compose["services"]["migrate"]["depends_on"]

    assert depends["postgres"]["condition"] == "service_healthy"


def test_database_and_cache_have_healthchecks(compose: dict) -> None:
    for service in ("postgres", "valkey"):
        assert "healthcheck" in compose["services"][service]


def test_migrate_does_not_restart(compose: dict) -> None:
    """Одноразовый сервис с restart: always уходит в вечный цикл."""
    assert compose["services"]["migrate"].get("restart", "no") == "no"


def test_only_nginx_publishes_ports(compose: dict) -> None:
    """Открытый наружу порт базы — самый частый способ потерять данные."""
    with_ports = {
        name for name, service in compose["services"].items() if service.get("ports")
    }

    assert with_ports == {"nginx"}


def test_no_literal_secrets_in_compose() -> None:
    text = (ROOT / "compose.yml").read_text(encoding="utf-8")

    for marker in ("password:", "secret:", "token:"):
        for line in text.splitlines():
            if marker in line.lower() and "${" not in line:
                pytest.fail(f"похоже на секрет в открытом виде: {line.strip()}")


def test_env_example_covers_every_variable_used_in_compose() -> None:
    """Переменная, которой нет в .env.example, обнаружится только на чужом сервере."""
    import re

    compose_text = (ROOT / "compose.yml").read_text(encoding="utf-8")
    used = set(re.findall(r"\$\{([A-Z0-9_]+)", compose_text))
    documented = {
        line.split("=", 1)[0].strip()
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#") and "=" in line
    }

    assert used <= documented, f"не описаны в .env.example: {sorted(used - documented)}"
```

`tools/tests/test_nginx_conf.py`:

```python
"""Маршрутизация и заголовки безопасности."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def conf() -> str:
    return (ROOT / "docker" / "nginx.conf").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("location", "upstream"),
    [("/api", "api"), ("/app", None), ("/tg/webhook", "bot"), ("/", "web")],
)
def test_routes_are_declared(conf: str, location: str, upstream: str | None) -> None:
    assert f"location {location}" in conf
    if upstream:
        assert f"http://{upstream}:" in conf


def test_miniapp_falls_back_to_index_for_client_routing(conf: str) -> None:
    assert "/app/index.html" in conf


def test_miniapp_allows_framing_by_telegram(conf: str) -> None:
    """MiniApp обязан открываться во фрейме клиента — X-Frame-Options его сломает."""
    assert "frame-ancestors" in conf
    assert "telegram.org" in conf


def test_script_source_is_restricted_to_telegram(conf: str) -> None:
    """SDK Telegram нельзя подписать через integrity, поэтому источник ограничен здесь."""
    assert "script-src 'self' https://telegram.org" in conf


def test_security_headers_are_present(conf: str) -> None:
    for header in ("X-Content-Type-Options", "Referrer-Policy", "Strict-Transport-Security"):
        assert header in conf
```

Добавить `"pyyaml>=6.0"` в группу `dev` корневого `pyproject.toml`.

- [ ] **Шаг 2: Запустить тесты и убедиться, что они падают**

Выполнить: `uv run pytest tools/tests/test_compose.py tools/tests/test_nginx_conf.py -v`
Ожидается: FAIL — файлы не найдены.

- [ ] **Шаг 3: Написать `docker/nginx.conf`**

```nginx
upstream api_upstream { server api:8000; }
upstream bot_upstream { server bot:8080; }
upstream web_upstream { server web:3000; }

server {
    listen 80;
    server_name _;

    client_max_body_size 8m;

    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # MiniApp. Внутри Telegram страница открывается во фрейме клиента,
    # поэтому X-Frame-Options здесь неприменим — ограничение задаётся
    # через frame-ancestors. script-src сужен до telegram.org: SDK
    # загружается оттуда и подписать его через integrity нельзя.
    location /app {
        alias /usr/share/nginx/html/app;
        try_files $uri $uri/ /app/index.html;

        add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://telegram.org; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'; frame-ancestors https://web.telegram.org https://*.telegram.org" always;
        add_header X-Content-Type-Options "nosniff" always;
    }

    location /api {
        proxy_pass http://api_upstream;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }

    # Секрет бота уже содержится в самом пути — сюда попадают только
    # запросы, знающие его. Подпись заголовка проверяет aiogram.
    location /tg/webhook {
        proxy_pass http://bot_upstream;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location / {
        proxy_pass http://web_upstream;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        add_header X-Frame-Options "DENY" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    }
}
```

TLS в этом файле не настраивается: сертификаты выпускаются на конкретный домен и описываются в `docs/deployment.md` (задача 17). Держать в репозитории конфиг с чужим доменом бессмысленно.

- [ ] **Шаг 4: Написать `.env.example`**

```dotenv
# Скопируйте в .env и заполните. Файл .env в репозиторий не попадает.

ENVIRONMENT=local
LOG_LEVEL=INFO

# --- База данных ---
POSTGRES_USER=repibot
POSTGRES_PASSWORD=смените-меня
POSTGRES_DB=repibot
DATABASE_URL=postgresql+asyncpg://repibot:смените-меня@postgres:5432/repibot

# --- Кэш и очередь ---
VALKEY_URL=redis://valkey:6379/0

# --- Telegram ---
# Токен бота выдаёт @BotFather.
BOT_TOKEN=
# Случайная строка: используется и в пути вебхука, и в заголовке подписи.
# Сгенерировать: openssl rand -hex 32
BOT_WEBHOOK_SECRET=
BOT_WEBHOOK_BASE_URL=https://example.org
# true — long polling для локальной разработки без внешнего адреса.
BOT_USE_POLLING=false

# --- Панель Remnawave ---
# При развёртывании рядом с панелью: http://remnawave:3000
REMNAWAVE_BASE_URL=https://panel.example.org
REMNAWAVE_TOKEN=

# --- Секреты приложения ---
# Обе строки сгенерировать: openssl rand -hex 32
JWT_SECRET=
ENCRYPTION_KEY=

# --- Публичные адреса ---
PUBLIC_WEB_URL=https://example.org
PUBLIC_APP_URL=https://example.org/app

# --- Локализация ---
DEFAULT_LANGUAGE=ru
```

- [ ] **Шаг 5: Написать `compose.yml`**

```yaml
name: repibot

x-backend: &backend
  build:
    context: .
    dockerfile: docker/backend.Dockerfile
  env_file: [.env]
  restart: unless-stopped

services:
  postgres:
    image: postgres:18-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes: [postgres-data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  valkey:
    image: valkey/valkey:8-alpine
    command: ["valkey-server", "--save", "60", "1", "--appendonly", "no"]
    volumes: [valkey-data:/data]
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped

  # Одноразовый сервис. Отрабатывает до старта остальных, чтобы три
  # процесса не боролись за блокировку миграций.
  migrate:
    <<: *backend
    command: ["alembic", "upgrade", "head"]
    restart: "no"
    depends_on:
      postgres:
        condition: service_healthy

  api:
    <<: *backend
    command: ["uvicorn", "repibot_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
    depends_on:
      migrate:
        condition: service_completed_successfully
      valkey:
        condition: service_healthy

  bot:
    <<: *backend
    command: ["python", "-m", "repibot_bot.main"]
    depends_on:
      migrate:
        condition: service_completed_successfully
      valkey:
        condition: service_healthy

  worker:
    <<: *backend
    command: ["taskiq", "worker", "repibot_worker.broker:broker", "repibot_worker.tasks"]
    depends_on:
      migrate:
        condition: service_completed_successfully
      valkey:
        condition: service_healthy

  scheduler:
    <<: *backend
    command: ["taskiq", "scheduler", "repibot_worker.broker:scheduler", "repibot_worker.tasks"]
    depends_on:
      migrate:
        condition: service_completed_successfully
      valkey:
        condition: service_healthy

  web:
    build:
      context: .
      dockerfile: docker/web.Dockerfile
    restart: unless-stopped
    depends_on: [api]

  nginx:
    build:
      context: .
      dockerfile: docker/nginx.Dockerfile
    ports: ["80:80"]
    restart: unless-stopped
    depends_on: [api, web, bot]

volumes:
  postgres-data:
  valkey-data:
```

- [ ] **Шаг 6: Написать `compose.local-panel.yml`**

```yaml
# Оверлей для случая, когда панель Remnawave развёрнута на этом же сервере.
#
# Запуск:
#   docker compose -f compose.yml -f compose.local-panel.yml up -d
#
# В .env при этом указывается внутренний адрес:
#   REMNAWAVE_BASE_URL=http://remnawave:3000

services:
  api:
    networks: [default, remnawave-network]
  worker:
    networks: [default, remnawave-network]
  scheduler:
    networks: [default, remnawave-network]

networks:
  remnawave-network:
    external: true
```

- [ ] **Шаг 7: Запустить тесты и убедиться, что они проходят**

Выполнить: `uv run pytest tools/tests/test_compose.py tools/tests/test_nginx_conf.py -v`
Ожидается: PASS, 16 тестов.

- [ ] **Шаг 8: Проверить, что стек действительно поднимается**

```bash
cp .env.example .env
# заполнить BOT_TOKEN, BOT_WEBHOOK_SECRET, REMNAWAVE_TOKEN, JWT_SECRET, ENCRYPTION_KEY
docker compose build
docker compose up -d
docker compose ps
curl -i http://localhost/health
curl -i http://localhost/
curl -i http://localhost/app/
docker compose logs scheduler --tail 20
```

Ожидается: все сервисы, кроме `migrate`, в состоянии `running`, `migrate` — `exited (0)`. `/health` отдаёт `{"status":"ok","database":true,"valkey":true}`. Главная и MiniApp возвращают 200.

Повторный `docker compose up -d` не должен приводить к повторному применению миграций — Alembic видит текущую ревизию и завершается без изменений.

- [ ] **Шаг 9: Коммит**

```bash
git add compose.yml compose.local-panel.yml .env.example docker/nginx.conf tools/tests pyproject.toml uv.lock
git commit -m "feat: nginx, compose и переменные окружения для развёртывания"
```

---

### Задача 16: Непрерывная интеграция

**Файлы:**
- Создать: `.github/workflows/ci.yml`
- Создать: `tools/verify_generated.py`
- Изменить: `tools/check.py`
- Тест: `tools/tests/test_verify_generated.py`

**Интерфейсы:**
- Отдаёт: `verify_generated() -> list[str]` — возвращает пути файлов, отличающихся от результата перегенерации; `main() -> int`; проверка `generated` в `CHECKS`.

- [ ] **Шаг 1: Написать падающий тест**

`tools/tests/test_verify_generated.py`:

```python
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
    target.write_bytes(b"строка\r\n")

    assert compare(target, "строка\n") is True


def test_compare_reports_missing_file_as_difference(tmp_path: Path) -> None:
    assert compare(tmp_path / "нет-такого", "что угодно") is False
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Выполнить: `uv run pytest tools/tests/test_verify_generated.py -v`
Ожидается: FAIL — `ModuleNotFoundError: No module named 'tools.verify_generated'`

- [ ] **Шаг 3: Написать `tools/verify_generated.py`**

```python
"""Проверка синхронности сгенерированных файлов.

Перегенерирует их во временную копию и сравнивает с закоммиченным. Расхождение
означает, что кто-то поменял источник и забыл перегенерировать результат.
"""

from __future__ import annotations

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


def verify_generated() -> list[str]:
    """Перегенерирует файлы и возвращает пути тех, что разошлись."""
    stale: list[str] = []
    for entry in GENERATED:
        target = ROOT / entry.path
        before = target.read_text(encoding="utf-8") if target.exists() else ""
        subprocess.run(entry.command, cwd=entry.cwd, check=True)  # noqa: S603
        if not compare(target, before):
            stale.append(str(entry.path))
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
```

Добавить в `[project.scripts]` корневого `pyproject.toml`:

```toml
verify-generated = "tools.verify_generated:main"
```

- [ ] **Шаг 4: Добавить проверку в `CHECKS`**

В `tools/check.py`, после проверки `vitest`:

```python
    Check(name="generated", command=["uv", "run", "verify-generated"], cwd=ROOT),
```

- [ ] **Шаг 5: Запустить тесты и убедиться, что они проходят**

Выполнить: `uv run pytest tools/tests -v && uv run check`
Ожидается: все тесты PASS, `uv run check` завершается кодом 0 и печатает «Сгенерированные файлы актуальны».

- [ ] **Шаг 6: Написать workflow**

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  check:
    name: Проверки
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - uses: pnpm/action-setup@v4
        with:
          version: 10

      - uses: actions/setup-node@v4
        with:
          node-version: 24
          cache: pnpm
          cache-dependency-path: frontend/pnpm-lock.yaml

      - name: Установить зависимости бэкенда
        run: uv sync --frozen

      - name: Установить зависимости фронтенда
        run: pnpm install --frozen-lockfile
        working-directory: frontend

      # Тот же вход, что и локально: расхождение между CI и машиной
      # разработчика невозможно по построению.
      - name: Прогнать проверки
        run: uv run check

  e2e:
    name: Сквозные тесты
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 10

      - uses: actions/setup-node@v4
        with:
          node-version: 24
          cache: pnpm
          cache-dependency-path: frontend/pnpm-lock.yaml

      - run: pnpm install --frozen-lockfile
        working-directory: frontend

      - run: pnpm --filter @repibot/web exec playwright install --with-deps chromium
        working-directory: frontend

      - run: pnpm --filter @repibot/web e2e
        working-directory: frontend

      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: frontend/apps/web/playwright-report

  build:
    name: Сборка образов
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - name: Собрать образы
        run: |
          cp .env.example .env
          docker compose build
```

- [ ] **Шаг 7: Коммит**

```bash
git add .github tools pyproject.toml
git commit -m "feat: непрерывная интеграция и контроль синхронности генерации"
```

---

### Задача 17: Документация и лицензия

Проект открытый. Документация здесь — часть фундамента, а не украшение: без неё его никто не развернёт.

**Файлы:**
- Создать: `README.md`, `CONTRIBUTING.md`, `LICENSE`
- Создать: `docs/deployment.md`
- Тест: `tools/tests/test_docs.py`

**Интерфейсы:** нет — задача документационная.

- [ ] **Шаг 1: Написать падающий тест**

`tools/tests/test_docs.py`:

```python
"""Документация проверяется на полноту машинно: устаревшая инструкция
по развёртыванию хуже её отсутствия.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["README.md", "CONTRIBUTING.md", "LICENSE", "docs/deployment.md"])
def test_required_documents_exist(name: str) -> None:
    assert (ROOT / name).is_file()


def test_readme_covers_local_start() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for fragment in ("docker compose up", "uv run check", ".env.example"):
        assert fragment in readme


def test_deployment_covers_botfather_oidc_setup() -> None:
    """Redirect URI и Trusted Origins задаются в BotFather — забыть их
    невозможно обнаружить иначе, чем сломанным входом через Telegram."""
    deployment = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    for fragment in ("BotFather", "Redirect URI", "Trusted Origins", "REMNAWAVE_TOKEN"):
        assert fragment in deployment


def test_readme_documents_where_specs_live() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "docs/superpowers/specs" in readme
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Выполнить: `uv run pytest tools/tests/test_docs.py -v`
Ожидается: FAIL — файлы не найдены.

- [ ] **Шаг 3: Написать `README.md`**

````markdown
# Re:Pibot Shop

Магазин VPN-подписок поверх панели [Remnawave](https://remna.st) 2.8.1: Telegram-бот,
Telegram MiniApp и веб-кабинет. Открытый проект, разворачивается рядом со своей панелью.

Текущее состояние: подпроект 0 «Фундамент». Бизнес-функций пока нет — есть работающий
каркас, на который они встают.

## Что внутри

| Каталог | Что там |
|---|---|
| `backend/core` | Бизнес-логика: домен, база, интеграции, сценарии |
| `backend/api` | FastAPI: REST и вебхуки |
| `backend/bot` | Бот на aiogram |
| `backend/worker` | Фоновые задачи и расписание на TaskIQ |
| `frontend/apps/miniapp` | MiniApp: React 19 и Vite |
| `frontend/apps/web` | Сайт, кабинет и админка: Next.js 16 |
| `frontend/packages` | Общие пакеты: логика, компоненты, настройки инструментов |
| `docs/superpowers/specs` | Спецификации: архитектура платформы и подпроекты |

## Быстрый старт

Нужны Docker, [uv](https://docs.astral.sh/uv/), Node 24 и pnpm 10.

```bash
cp .env.example .env
# заполнить BOT_TOKEN, BOT_WEBHOOK_SECRET, REMNAWAVE_TOKEN, JWT_SECRET, ENCRYPTION_KEY
docker compose up -d
curl http://localhost/health
```

Сайт откроется на `http://localhost/`, MiniApp — на `http://localhost/app/`.

## Разработка

```bash
uv sync
cd frontend && pnpm install && cd ..
uv run check
```

`uv run check` — единственная команда проверки: линтеры, типы и тесты обоих языков.
Ровно её же выполняет CI, поэтому «локально проходило» не бывает.

Локально бот удобнее запускать в режиме long polling: `BOT_USE_POLLING=true` в `.env`.

## Документация

- [Архитектура платформы](docs/superpowers/specs/2026-08-04-platform-architecture-design.md)
- [Спецификация фундамента](docs/superpowers/specs/2026-08-04-foundation-design.md)
- [Развёртывание](docs/deployment.md)
- [Бренд-бук](docs/design/repibot-brandbook.md)

## Лицензия

AGPL-3.0. См. [LICENSE](LICENSE).
````

- [ ] **Шаг 4: Написать `docs/deployment.md`**

````markdown
# Развёртывание

## Что понадобится

- Сервер с Docker и Docker Compose.
- Домен с сертификатом TLS.
- Панель Remnawave 2.8.1 — на этом же сервере или на другом.
- Бот, созданный в @BotFather.

## 1. Панель Remnawave

Создайте в панели API-токен (раздел API Tokens) и запишите его в `REMNAWAVE_TOKEN`.

Адрес панели зависит от размещения:

- Панель на другом сервере: `REMNAWAVE_BASE_URL=https://panel.example.org`
- Панель рядом: `REMNAWAVE_BASE_URL=http://remnawave:3000`, запуск с оверлеем
  `docker compose -f compose.yml -f compose.local-panel.yml up -d`. Имя внешней сети
  в `compose.local-panel.yml` должно совпадать с сетью вашей панели.

## 2. Бот и вход через Telegram

В @BotFather получите токен бота — это `BOT_TOKEN`.

Вход через Telegram на сайте работает по OpenID Connect. Настройки задаются
**в мини-приложении @BotFather**, через обычный чат этот раздел недоступен:

1. Откройте мини-приложение BotFather, выберите бота.
2. Bot Settings → Web Login.
3. Скопируйте **Client ID** и **Client Secret**.
4. В **Redirect URIs** добавьте `https://ваш-домен/auth/telegram/callback`.
5. В **Trusted Origins** добавьте `https://ваш-домен/`.

Адреса должны совпадать точно, включая протокол и завершающий слеш. Расхождение
проявляется отказом на этапе обмена кода на токен.

Client ID и Client Secret понадобятся начиная с подпроекта 1 — в фундаменте
аутентификации ещё нет, но настроить их удобно сразу.

## 3. Переменные окружения

```bash
cp .env.example .env
```

Обязательно заполнить: `BOT_TOKEN`, `BOT_WEBHOOK_SECRET`, `BOT_WEBHOOK_BASE_URL`,
`REMNAWAVE_BASE_URL`, `REMNAWAVE_TOKEN`, `JWT_SECRET`, `ENCRYPTION_KEY`,
`POSTGRES_PASSWORD`, `PUBLIC_WEB_URL`, `PUBLIC_APP_URL`.

Секреты генерируются так:

```bash
openssl rand -hex 32
```

`BOT_WEBHOOK_SECRET` используется дважды: как часть пути вебхука и как заголовок
подписи. Меняя его, перезапустите бота — вебхук переустанавливается на старте.

## 4. TLS

Конфигурация Nginx в репозитории слушает только 80 порт: сертификаты выпускаются
на конкретный домен, и держать в открытом проекте чужой домен бессмысленно.

Варианты:

- Внешний обратный прокси (Caddy, Traefik) перед контейнером `nginx`.
- Certbot и монтирование сертификатов в контейнер `nginx` с добавлением
  секции `listen 443 ssl` в `docker/nginx.conf`.

Telegram принимает вебхуки только по HTTPS — без TLS бот работать не будет.

## 5. Запуск

```bash
docker compose build
docker compose up -d
docker compose ps
curl https://ваш-домен/health
```

Ожидаемо: все сервисы в состоянии `running`, кроме `migrate` — он одноразовый
и завершается кодом 0. Проверка живости возвращает
`{"status":"ok","database":true,"valkey":true}`.

## 6. Обновление

```bash
git pull
docker compose build
docker compose up -d
```

Миграции применяет сервис `migrate` до старта остальных — вручную ничего запускать
не нужно.

## Диагностика

| Симптом | Причина |
|---|---|
| `migrate` завершается с ошибкой | Недоступен Postgres или неверный `DATABASE_URL` |
| `/health` отдаёт `database: false` | Контейнер базы не поднялся, смотрите `docker compose logs postgres` |
| Бот не отвечает | Проверьте `BOT_WEBHOOK_BASE_URL`, TLS и `docker compose logs bot` |
| Задачи не выполняются | Работать должны оба сервиса: `worker` и `scheduler` |
| Панель не отвечает | Проверьте `REMNAWAVE_TOKEN` и сетевую доступность из контейнера `api` |
````

- [ ] **Шаг 5: Написать `CONTRIBUTING.md`**

```markdown
# Как участвовать

## Порядок работы

1. Ветка от `main`.
2. Изменение с тестом. Тест пишется первым и должен падать до реализации.
3. `uv run check` проходит целиком.
4. Pull request с описанием того, что меняется и почему.

## Договорённости

- Сообщения коммитов на русском: `тип: краткое описание` (`feat`, `fix`, `docs`,
  `refactor`, `test`, `chore`).
- Бизнес-логика живёт в `backend/core/services` и `backend/core/domain`.
  В роутерах FastAPI и хендлерах aiogram её быть не должно — иначе бот и сайт
  начинают вести себя по-разному.
- Цвета, отступы и типографика берутся из `docs/design/repibot-brandbook.md`.
  Значений «на глаз» в коде нет; токены проверяются тестом.
- Сгенерированные файлы правятся только через генератор. Проверка `generated`
  в `uv run check` отследит расхождение.
- Секреты в репозиторий не попадают. Новая переменная окружения добавляется
  одновременно в `Settings`, `.env.example` и `docs/deployment.md`.

## Крупные изменения

Перед крупной работой заводится спецификация в `docs/superpowers/specs/`, затем
план в `docs/superpowers/plans/`. Так обсуждение замысла происходит до того,
как написан код, а не после.
```

- [ ] **Шаг 6: Добавить `LICENSE`**

Поместить полный текст лицензии GNU Affero General Public License v3.0
с сайта https://www.gnu.org/licenses/agpl-3.0.txt.

Выбор AGPL-3.0 согласуется с лицензией самой панели Remnawave.

- [ ] **Шаг 7: Запустить тесты и полную проверку**

Выполнить: `uv run pytest tools/tests/test_docs.py -v && uv run check`
Ожидается: семь тестов PASS, `uv run check` завершается кодом 0.

- [ ] **Шаг 8: Пройти приёмку целиком**

Проверить каждый критерий из раздела 8 спецификации:

```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
docker compose ps                      # 1: всё running, migrate — exited (0)
curl -s http://localhost/health        # 1: status ok
                                       # 2: написать боту /start
docker compose logs scheduler --tail 30 # 3: heartbeat в логах
curl -s http://localhost/ | head        # 4: страница отдаётся
curl -s http://localhost/app/ | head    # 4: MiniApp отдаётся
                                       # 5: открыть MiniApp в Telegram
uv run check                            # 6: все проверки зелёные
docker compose up -d                    # 8: миграции не применяются повторно
```

Отдельно проверить критерий 7: убрать `JWT_SECRET` из `.env`, выполнить
`docker compose up api`, убедиться, что в логе есть имя недостающей переменной,
вернуть значение обратно.

- [ ] **Шаг 9: Коммит**

```bash
git add README.md CONTRIBUTING.md LICENSE docs/deployment.md tools/tests/test_docs.py
git commit -m "docs: README, инструкция по развёртыванию, правила участия и лицензия"
```

---

## Порядок и зависимости

Задачи 1–4 строго последовательны: каждая опирается на предыдущую.

Задачи 5, 6, 7 зависят только от 1–4 и между собой не связаны — их можно вести параллельно.

Задача 8 зависит от 1–2.

Задача 9 зависит от 1. Задачи 10 и 11 зависят от 9; задача 11 дополнительно требует
задачу 5 (схема OpenAPI выгружается из работающего приложения). Задачи 12 и 13
зависят от 10 и 11.

Задача 14 зависит от 5–7 и 12–13. Задача 15 — от 14. Задача 16 — от 15.
Задача 17 закрывает подпроект.

## Что осталось за границей

Аутентификация, тарифы, платежи, вызовы бизнес-методов панели, отправка писем,
реальные экраны кабинета, векторный логотип и производные от него файлы. Всё это —
следующие подпроекты, каждый со своей спецификацией.
