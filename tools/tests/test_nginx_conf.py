"""Маршрутизация и заголовки безопасности."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def conf() -> str:
    return (ROOT / "docker" / "nginx.conf").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("location", "upstream"),
    [("/api", "api"), ("/app", None), ("/webhook/telegram", "bot"), ("/", "web")],
)
def test_routes_are_declared(conf: str, location: str, upstream: str | None) -> None:
    # Точное совпадение (location = /путь) объявляется наравне с префиксным.
    assert re.search(rf"location\s+=?\s*{re.escape(location)}\s", conf)
    if upstream:
        # Маршрут ведёт в именованный upstream, а тот — в нужный сервис compose.
        assert f"proxy_pass http://{upstream}_upstream" in conf
        assert f"upstream {upstream}_upstream {{ server {upstream}:" in conf


def test_webhook_route_matches_the_path_bot_registers(conf: str) -> None:
    """Разъехавшиеся пути дают молчаливый 404 на каждый апдейт от Telegram."""
    from repibot_bot.main import WEBHOOK_PATH

    assert f"location = {WEBHOOK_PATH}" in conf


def test_health_is_routed_to_api(conf: str) -> None:
    """Без отдельного маршрута /health уходит в веб-приложение и отдаёт 404."""
    assert "location = /health" in conf


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
