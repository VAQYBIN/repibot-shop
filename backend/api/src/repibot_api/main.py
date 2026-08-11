"""Сборка приложения FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from repibot_api.deps import get_redis
from repibot_api.errors import register_error_handlers
from repibot_api.health import router as health_router
from repibot_api.middleware import register_request_id_middleware
from repibot_api.origins import allowed_origins
from repibot_api.routers.admin import router as admin_router
from repibot_api.routers.auth import router as auth_router
from repibot_api.routers.me import router as me_router
from repibot_api.routers.subscription import router as subscription_router
from repibot_api.routers.support import router as support_router
from repibot_api.routers.unsubscribe import router as unsubscribe_router
from repibot_api.routers.webhooks import router as webhooks_router
from repibot_api.routers.winback import router as winback_router
from repibot_core.logging import configure_logging
from repibot_core.queue import broker
from repibot_core.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Брокер поднимается вместе с приложением.

    api ставит задачу разбора outbox сразу после регистрации, а для этого
    брокеру нужно установленное соединение.
    """
    await broker.startup()
    try:
        yield
    finally:
        await broker.shutdown()
        await get_redis().aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Re:Pibot Shop API",
        version="0.1.0",
        docs_url="/api/docs" if settings.environment == "local" else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(settings.public_web_url, settings.public_app_url),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_request_id_middleware(app)
    register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(unsubscribe_router)
    app.include_router(subscription_router)
    app.include_router(winback_router)
    app.include_router(support_router)
    app.include_router(admin_router)
    app.include_router(webhooks_router)
    return app


app = create_app()
