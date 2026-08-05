"""Инварианты знака. Проверяются арифметикой по параметрам, а не глазами.

Бренд-бук задаёт зазор, толщину обводки и минимальные размеры числами —
значит, их можно и нужно проверять машинно. Глазами проверяется только то,
что бренд-бук прямо называет оптическим.
"""

import re
from pathlib import Path

import pytest

from tools.brand.build import FILES, LOGO_DIR
from tools.brand.geometry import (
    CURRENT,
    FULL,
    JADE,
    PALETTE,
    SMALL,
    Mark,
    badge_svg,
    mark_svg,
)


@pytest.mark.parametrize("mark", [FULL, SMALL], ids=["full", "small"])
def test_gap_between_core_and_coil_meets_the_brandbook(mark: Mark) -> None:
    """Зазор — несущий элемент знака, раздел 1. Минимум 0.5x, раздел 4."""
    assert mark.gap >= 0.5 * mark.unit


def test_small_mark_is_one_turn_with_a_bigger_core() -> None:
    """Раздел 4: один виток вместо полутора, ядро 1.3x, обводка толще."""
    assert FULL.arcs == 3
    assert SMALL.arcs == 2
    assert SMALL.core[2] == pytest.approx(1.3 * FULL.core[2], abs=0.15)
    assert SMALL.stroke > FULL.stroke


def test_small_mark_survives_sixteen_pixels() -> None:
    """Ради этого упрощённая версия и существует: полный знак здесь слипается."""
    scale = 16 / SMALL.height

    assert SMALL.stroke * scale >= 2.0
    assert SMALL.gap * scale >= 1.5


@pytest.mark.parametrize("mark", [FULL, SMALL], ids=["full", "small"])
def test_break_stays_on_the_left(mark: Mark) -> None:
    """Направление разрыва — часть узнаваемости, раздел 4."""
    assert mark.terminus < mark.core[0]


@pytest.mark.parametrize("mark", [FULL, SMALL], ids=["full", "small"])
def test_declared_arc_count_matches_the_path(mark: Mark) -> None:
    assert mark.path.count("A") == mark.arcs


def test_mark_svg_uses_only_the_given_colors() -> None:
    svg = mark_svg(FULL, CURRENT, CURRENT)

    assert re.search(r"#[0-9A-Fa-f]{6}", svg) is None


def test_badge_shifts_the_mark_optically() -> None:
    """Раздел 4: при врезке в квадрат знак смещается вправо и вверх."""
    svg = badge_svg(FULL, 96, JADE, "#FFFFFF", "#FFFFFF")
    match = re.search(r"translate\(([\d.-]+) ([\d.-]+)\)", svg)
    assert match is not None
    x, y = float(match.group(1)), float(match.group(2))

    # Куда попал бы знак, если бы его просто центрировали по габариту.
    factor = 96 * 0.7 / max(FULL.width, FULL.height)
    assert x > (96 - FULL.width * factor) / 2
    assert y < (96 - FULL.height * factor) / 2


def test_palette_holds_only_brandbook_colors() -> None:
    """Раздел 2. Посторонний цвет в палитре разошёлся бы по всем файлам сразу."""
    canonical = {
        "#1A1A18",
        "#FAF9F7",
        "#17A67C",
        "#2CC694",
        "#E4F5EE",
        "#F2F1ED",
        "#FFFFFF",
    }

    assert set(PALETTE) == canonical


ROOT = Path(__file__).resolve().parents[2]

BRANDBOOK_FILES = (
    "logo-mark.svg",
    "logo-mark-mono.svg",
    "logo-mark-small.svg",
    "logo-lockup-h.svg",
    "logo-lockup-v.svg",
    "favicon.svg",
)


@pytest.mark.parametrize("name", BRANDBOOK_FILES)
def test_brandbook_files_exist(name: str) -> None:
    """Раздел 8 бренд-бука перечисляет их поимённо."""
    assert (LOGO_DIR / name).is_file()


@pytest.mark.parametrize("name", sorted(FILES))
def test_every_file_uses_only_brandbook_colors(name: str) -> None:
    content = (LOGO_DIR / name).read_text(encoding="utf-8")

    for colour in re.findall(r"#[0-9A-Fa-f]{6}", content):
        assert colour.upper() in PALETTE, f"{name}: посторонний цвет {colour}"


def test_mono_version_has_no_colors_at_all() -> None:
    """Одноцветная версия красится текстом вокруг: тиснение, гравировка, факс."""
    content = (LOGO_DIR / "logo-mark-mono.svg").read_text(encoding="utf-8")

    assert re.search(r"#[0-9A-Fa-f]{6}", content) is None
    assert content.count("currentColor") == 2


def test_spiral_path_is_identical_everywhere() -> None:
    """Расхождение геометрии между файлами — то, о чём предупреждает раздел 8."""
    for name in ("logo-mark.svg", "logo-mark-mono.svg", "logo-lockup-h.svg", "badge.svg"):
        assert FULL.path in (LOGO_DIR / name).read_text(encoding="utf-8")

    for name in ("logo-mark-small.svg", "favicon.svg"):
        assert SMALL.path in (LOGO_DIR / name).read_text(encoding="utf-8")


def test_favicon_is_copied_to_both_applications() -> None:
    original = (LOGO_DIR / "favicon.svg").read_bytes()

    assert (ROOT / "frontend/apps/web/public/favicon.svg").read_bytes() == original
    assert (ROOT / "frontend/apps/miniapp/public/favicon.svg").read_bytes() == original


RASTER = (
    ("favicon-16.png", 16),
    ("favicon-32.png", 32),
    ("icon-192.png", 192),
    ("icon-512.png", 512),
    ("avatar-512.png", 512),
)


@pytest.mark.parametrize(("name", "side"), RASTER)
def test_raster_file_has_the_declared_size(name: str, side: int) -> None:
    """Ширина и высота PNG лежат в заголовке IHDR, отдельная библиотека не нужна."""
    header = (LOGO_DIR / "raster" / name).read_bytes()[16:24]
    width = int.from_bytes(header[:4], "big")
    height = int.from_bytes(header[4:], "big")

    assert (width, height) == (side, side)


def test_open_graph_image_is_twelve_hundred_by_six_thirty() -> None:
    header = (LOGO_DIR / "raster" / "og-image.png").read_bytes()[16:24]

    assert int.from_bytes(header[:4], "big") == 1200
    assert int.from_bytes(header[4:], "big") == 630


@pytest.mark.parametrize(
    "name", ["favicon-16.png", "favicon-32.png", "icon-192.png", "icon-512.png"]
)
def test_public_raster_matches_the_brand_kit(name: str) -> None:
    """Копии в public — именно копии. Разошедшиеся иконки заметит только пользователь."""
    original = (LOGO_DIR / "raster" / name).read_bytes()

    assert (ROOT / "frontend/apps/web/public" / name).read_bytes() == original


def test_component_draws_the_same_spiral_as_the_files() -> None:
    """Знак на странице и знак в файле обязаны быть одной фигурой."""
    component = (ROOT / "frontend/packages/ui/src/components/logo-mark.tsx").read_text(
        encoding="utf-8"
    )

    assert FULL.path in component
    assert SMALL.path in component
    assert f"strokeWidth: {FULL.stroke:g}" in component
    assert f"strokeWidth: {SMALL.stroke:g}" in component
