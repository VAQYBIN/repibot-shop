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
