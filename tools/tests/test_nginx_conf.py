"""Маршрутизация и заголовки безопасности."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

COMMON_SECURITY_HEADERS = (
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Strict-Transport-Security",
)


@pytest.fixture(scope="module")
def conf() -> str:
    return (ROOT / "docker" / "nginx.conf").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def snippet() -> str:
    return (ROOT / "docker" / "security-headers.conf").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def locations(conf: str) -> dict[str, str]:
    """Тело каждой локации отдельно: заголовки действуют поблочно, а не на файл."""
    blocks: dict[str, str] = {}
    for match in re.finditer(r"location\s+(=\s*)?(\S+)\s*\{", conf):
        name = f"= {match.group(2)}" if match.group(1) else match.group(2)
        depth, index = 1, match.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(conf[index], 0)
            index += 1
        blocks[name] = conf[match.end() : index - 1]
    return blocks


@pytest.mark.parametrize(
    ("location", "upstream"),
    [
        ("/api", "api"),
        ("/app/", None),
        ("= /webhook/telegram", "bot"),
        ("= /webhook/remnawave", "api"),
        ("/", "web"),
    ],
)
def test_routes_are_declared(
    locations: dict[str, str], conf: str, location: str, upstream: str | None
) -> None:
    assert location in locations
    if upstream:
        assert f"proxy_pass http://{upstream}_upstream" in locations[location]
        assert f"upstream {upstream}_upstream {{ server {upstream}:" in conf


def test_webhook_route_matches_the_path_bot_registers(conf: str) -> None:
    """Разъехавшиеся пути дают молчаливый 404 на каждый апдейт от Telegram."""
    from repibot_bot.main import WEBHOOK_PATH

    assert f"location = {WEBHOOK_PATH}" in conf


def test_health_is_routed_to_api(locations: dict[str, str]) -> None:
    """Без отдельного маршрута /health уходит в веб-приложение и отдаёт 404."""
    assert "proxy_pass http://api_upstream" in locations["= /health"]


def test_miniapp_falls_back_to_index_for_client_routing(locations: dict[str, str]) -> None:
    assert "/app/index.html" in locations["/app/"]


def test_miniapp_location_does_not_swallow_neighbouring_paths(
    locations: dict[str, str],
) -> None:
    """Префикс без слеша ловил бы и /appfoo, затеняя будущие маршруты веба."""
    assert "/app" not in locations
    assert "/app/" in locations


def test_miniapp_root_redirects_to_the_directory(locations: dict[str, str]) -> None:
    """Иначе /app обслуживает location / и отдаёт страницу веб-приложения."""
    assert "return 301 /app/" in locations["= /app"]


def test_redirects_keep_the_external_scheme(conf: str) -> None:
    """absolute_redirect on собрал бы http://... и увёл пользователя с https."""
    assert "absolute_redirect off" in conf


def test_snippet_carries_the_common_security_headers(snippet: str) -> None:
    for header in COMMON_SECURITY_HEADERS:
        assert f'add_header {header} "' in snippet


def test_every_location_with_own_headers_reincludes_the_common_set(
    locations: dict[str, str],
) -> None:
    """add_header в location заменяет унаследованный от server набор целиком.

    Локация, объявившая свой заголовок и не подключившая общий файл, молча
    теряет HSTS и Referrer-Policy — проверка по всему файлу этого не увидит.
    """
    for name, body in locations.items():
        if "add_header" not in body:
            continue
        assert "include /etc/nginx/snippets/security-headers.conf;" in body, (
            f"локация {name} объявляет свои заголовки и теряет общий набор"
        )


def test_server_level_headers_cover_locations_without_their_own(conf: str) -> None:
    server_body = conf[conf.index("server {") : conf.index("location")]

    assert "include /etc/nginx/snippets/security-headers.conf;" in server_body


def test_snippet_is_copied_into_the_image() -> None:
    dockerfile = (ROOT / "docker" / "nginx.Dockerfile").read_text(encoding="utf-8")

    assert "security-headers.conf /etc/nginx/snippets/security-headers.conf" in dockerfile


def test_miniapp_allows_framing_by_telegram(locations: dict[str, str]) -> None:
    """MiniApp обязан открываться во фрейме клиента — X-Frame-Options его сломает."""
    assert "frame-ancestors" in locations["/app/"]
    assert "X-Frame-Options" not in locations["/app/"]


def test_miniapp_entry_is_revalidated_on_every_open(locations: dict[str, str]) -> None:
    """Без явного запрета точка входа кешируется на усмотрение браузера.

    index.html называет файлы сборки по именам с хешем, поэтому пережившая
    обновление копия неделями открывает старую сборку — а внутри Telegram это
    не лечится ни перезаходом, ни обычным обновлением страницы.
    """
    assert 'Cache-Control "no-cache"' in locations["/app/"]


def test_miniapp_assets_are_kept_as_long_as_possible(locations: dict[str, str]) -> None:
    """Имя файла содержит хеш содержимого: новая сборка — новое имя."""
    assert "immutable" in locations["/app/assets/"]


def test_script_source_is_restricted_to_telegram(locations: dict[str, str]) -> None:
    """SDK Telegram нельзя подписать через integrity, поэтому источник ограничен здесь."""
    assert "script-src 'self' https://telegram.org" in locations["/app/"]
