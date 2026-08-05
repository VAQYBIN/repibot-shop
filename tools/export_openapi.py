"""Выгружает схему FastAPI в файл.

Генерация типов фронтенда не должна требовать поднятого бэкенда: в CI и при
сборке образа его нет. Схема коммитится, расхождение ловится отдельной проверкой.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "frontend/packages/core/src/api/openapi.json"

# Заглушки на случай, когда настроек нет: в CI и при сборке образа .env отсутствует.
# Состав схемы от этих значений не зависит, а обязательные поля Settings — да.
_PLACEHOLDERS = {
    "DATABASE_URL": "postgresql+asyncpg://schema:schema@localhost:5432/schema",
    "VALKEY_URL": "redis://localhost:6379/0",
    "BOT_TOKEN": "0:schema-export-placeholder",
    "BOT_WEBHOOK_SECRET": "schema-export-placeholder",
    "BOT_WEBHOOK_BASE_URL": "https://example.invalid",
    "REMNAWAVE_BASE_URL": "https://example.invalid",
    "REMNAWAVE_TOKEN": "schema-export-placeholder",
    # Не короче 32 символов: настройки отвергают слабый ключ подписи, и заглушка
    # обязана проходить ту же проверку, что реальное значение.
    "JWT_SECRET": "schema-export-placeholder-key-32b",
    "ENCRYPTION_KEY": "schema-export-placeholder",
    "PUBLIC_WEB_URL": "https://example.invalid",
    "PUBLIC_APP_URL": "https://example.invalid/app",
}


def main() -> int:
    for key, value in _PLACEHOLDERS.items():
        os.environ.setdefault(key, value)

    from repibot_api.main import create_app

    schema = create_app().openapi()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Схема записана: {TARGET.relative_to(ROOT)}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
