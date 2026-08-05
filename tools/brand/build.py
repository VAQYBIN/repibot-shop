"""Сборка всех файлов бренд-набора.

Одиннадцать SVG выводятся из одного описания геометрии и одних контуров
вордмарка. Растеризация живёт отдельно: она требует браузера и в проверку
не входит.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tools.brand.geometry import (
    CURRENT,
    FULL,
    INK,
    JADE,
    JADE_BRIGHT,
    JADE_MIST,
    LIGHT,
    SMALL,
    WHITE,
    Mark,
    badge_svg,
    mark_markup,
    mark_svg,
    open_svg,
)
from tools.brand.wordmark_paths import ADVANCE, COLON, LETTERS, UNITS_PER_EM, X_HEIGHT

ROOT = Path(__file__).resolve().parents[2]
LOGO_DIR = ROOT / "docs" / "design" / "logo"

# Кегль вордмарка относительно высоты знака — из утверждённого оригинала.
FONT_RATIO = 0.485

OG_WIDTH = 1200
OG_HEIGHT = 630


def _wordmark_group(scale: float, x: float, baseline: float, letters: str, colon: str) -> str:
    return (
        f'<g transform="translate({x:.2f} {baseline:.2f}) scale({scale:.6f})">'
        f'<path d="{LETTERS}" fill="{letters}"/>'
        f'<path d="{COLON}" fill="{colon}"/></g>'
    )


def wordmark_svg(letters: str = INK, colon: str = JADE, size: float = 100.0) -> str:
    """Только надпись. Габарит — по ширине строки и полосе прописных."""
    scale = size / UNITS_PER_EM
    opening = open_svg(ADVANCE * scale, size, "re:pibot")
    return f"{opening}{_wordmark_group(scale, 0, size * 0.78, letters, colon)}</svg>"


def lockup_h_svg(mark: Mark = FULL, letters: str = INK, colon: str = JADE) -> str:
    """Знак слева, вордмарк справа. Просвет — высота строчной x, раздел 5."""
    size = mark.height * FONT_RATIO
    scale = size / UNITS_PER_EM
    x = mark.width + X_HEIGHT * scale
    # Оптический центр надписи — середина полосы строчных, а не базовая линия.
    baseline = mark.height / 2 + X_HEIGHT * scale / 2
    opening = open_svg(x + ADVANCE * scale, mark.height, "Re:Pibot")
    return (
        f"{opening}{mark_markup(mark, INK, JADE)}"
        f"{_wordmark_group(scale, x, baseline, letters, colon)}</svg>"
    )


def _lockup_v_body(
    mark: Mark, spiral: str, core: str, letters: str, colon: str
) -> tuple[str, float, float]:
    """Разметка вертикального лок-апа и его габарит.

    Габарит возвращается наружу, потому что открытый граф вписывает тот же
    лок-ап в свой холст: считать его размер второй раз означало бы завести
    вторую версию правды.
    """
    size = mark.height * FONT_RATIO
    scale = size / UNITS_PER_EM
    text_width = ADVANCE * scale
    width = max(mark.width, text_width)
    # Просвет — половина высоты знака, раздел 5.
    baseline = mark.height + mark.height / 2 + X_HEIGHT * scale
    # Ниже базовой линии остаётся выносной элемент буквы p.
    height = baseline + size * 0.12
    body = (
        f'<g transform="translate({(width - mark.width) / 2:.2f} 0)">'
        f"{mark_markup(mark, spiral, core)}</g>"
        f"{_wordmark_group(scale, (width - text_width) / 2, baseline, letters, colon)}"
    )
    return body, width, height


def lockup_v_svg(mark: Mark = FULL, letters: str = INK, colon: str = JADE) -> str:
    """Знак сверху по центру, вордмарк под ним."""
    body, width, height = _lockup_v_body(mark, INK, JADE, letters, colon)
    return f"{open_svg(width, height, 'Re:Pibot')}{body}</svg>"


def og_image_svg() -> str:
    """Открытый граф: знак на Ink, вордмарк под ним. Раздел 8.

    На Ink обычный Jade мутнеет, поэтому ядро — Jade Bright, раздел 2.
    """
    body, width, height = _lockup_v_body(FULL, LIGHT, JADE_BRIGHT, LIGHT, JADE_BRIGHT)
    # Лок-ап занимает половину высоты холста, остальное — воздух.
    scale = OG_HEIGHT * 0.5 / height
    x = (OG_WIDTH - width * scale) / 2
    y = (OG_HEIGHT - height * scale) / 2
    opening = open_svg(OG_WIDTH, OG_HEIGHT, "Re:Pibot — магазин VPN-подписок")
    return (
        f'{opening}<rect width="{OG_WIDTH}" height="{OG_HEIGHT}" fill="{INK}"/>'
        f'<g transform="translate({x:.2f} {y:.2f}) scale({scale:.4f})">{body}</g></svg>'
    )


FILES: dict[str, str] = {
    "logo-mark.svg": mark_svg(FULL, INK, JADE),
    "logo-mark-mono.svg": mark_svg(FULL, CURRENT, CURRENT, "Re:Pibot, одноцветная версия"),
    "logo-mark-small.svg": mark_svg(SMALL, INK, JADE, "Re:Pibot, упрощённый знак"),
    "wordmark.svg": wordmark_svg(),
    "logo-lockup-h.svg": lockup_h_svg(),
    "logo-lockup-v.svg": lockup_v_svg(),
    # Ядро на заливке Jade — белое, раздел 4. Мятное сливалось бы со спиралью.
    "badge.svg": badge_svg(FULL, 96, JADE, JADE_MIST, WHITE),
    # На Ink обычный Jade даёт мутное пятно, берётся Jade Bright — раздел 2.
    "badge-inverse.svg": badge_svg(FULL, 96, INK, LIGHT, JADE_BRIGHT),
    "favicon.svg": badge_svg(SMALL, 48, JADE, JADE_MIST, WHITE),
    # Аватар: знак крупнее плашки и обрезается ею, раздел 8.
    "avatar.svg": badge_svg(FULL, 512, JADE, JADE_MIST, WHITE, scale=1.15, bleed=True),
    "og-image.svg": og_image_svg(),
}

COPIES: tuple[tuple[str, Path], ...] = (
    ("favicon.svg", ROOT / "frontend/apps/web/public/favicon.svg"),
    ("favicon.svg", ROOT / "frontend/apps/miniapp/public/favicon.svg"),
)


def main() -> int:
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in FILES.items():
        (LOGO_DIR / name).write_text(content + "\n", encoding="utf-8")
    for name, destination in COPIES:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(FILES[name] + "\n", encoding="utf-8")
    print(f"Собрано файлов: {len(FILES) + len(COPIES)}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
