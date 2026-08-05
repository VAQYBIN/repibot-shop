"""Список разрешённых источников — это origin, а не адрес страницы.

Браузер присылает в Origin только схему, хост и порт. Запись с путём
(`https://example.org/app`) не совпадёт с ним никогда и просто мертва.
"""

from repibot_api.main import allowed_origins


def test_url_with_path_is_reduced_to_origin() -> None:
    origins = allowed_origins("https://example.org", "https://example.org/app")

    assert "https://example.org/app" not in origins
    assert origins == ["https://example.org"]


def test_separate_hosts_are_both_allowed() -> None:
    """MiniApp на своём домене — обычный случай, и он не должен отваливаться."""
    origins = allowed_origins("https://example.org", "https://app.example.org/miniapp")

    assert origins == ["https://example.org", "https://app.example.org"]


def test_port_is_part_of_the_origin() -> None:
    origins = allowed_origins("http://localhost:3000", "http://localhost:5173/app")

    assert origins == ["http://localhost:3000", "http://localhost:5173"]
