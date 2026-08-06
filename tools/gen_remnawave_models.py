"""Генерация Pydantic-моделей панели Remnawave.

Схема панели — 146 эндпоинтов и полтора мегабайта JSON. Генерировать всё
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

ROOT_SCHEMAS: tuple[str, ...] = (
    "CreateUserBodyDto",
    "DeleteUserHwidDeviceBodyDto",
    "GetInternalSquadsResponseDto",
    "GetStatsUserUsageResponseDto",
    "GetUserHwidDevicesResponseDto",
    "ResolveUserBodyDto",
    "UpdateUserBodyDto",
    "UserResponseDto",
)


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
                # Через sys.executable, а не «uv run»: скрипт уже выполняется внутри
                # окружения проекта, а полный путь снимает зависимость от PATH.
                sys.executable,
                "-m",
                "datamodel_code_generator",
                "--input",
                str(temp_path),
                "--input-file-type",
                "openapi",
                "--output",
                str(TARGET),
                "--output-model-type",
                "pydantic_v2.BaseModel",
                "--target-python-version",
                "3.13",
                "--use-standard-collections",
                "--use-union-operator",
                # Без этого флага поле с "nullable": true генерируется обязательным
                # и разбор ответа падает на первом же пользователе панели без тега.
                "--strict-nullable",
                # Флага --use-annotated здесь намеренно нет. Он переносит
                # ограничения схемы в Annotated, и тогда pattern из описания
                # даты применяется к полю типа AwareDatetime как строковый —
                # разбор любого ответа панели падает на expireAt. Слепоту mypy
                # к позиционному Field(None, ...) лечит плагин pydantic.mypy,
                # подключённый в pyproject.toml.
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
