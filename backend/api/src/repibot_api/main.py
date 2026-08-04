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
