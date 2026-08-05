"""Геометрия знака Re:Pibot и палитра бренда.

Числа перенесены из утверждённого оригинала docs/design/repibot_spiral_logo.svg
один раз и живут только здесь. Раздел 8 бренд-бука предупреждает: если файлов
станет восемь, а источника геометрии не будет, любая правка превратится
в восемь правок. Поэтому все файлы бренд-набора собираются отсюда.

Система координат перенесена к габариту обводки: у оригинала знак стоял
в середине большого холста вместе с остальными версиями.
"""

from __future__ import annotations

from dataclasses import dataclass

# Раздел 2 бренд-бука. Значения канонические, приводить к ним всё остальное.
INK = "#1A1A18"
PAPER = "#FAF9F7"
JADE = "#17A67C"
JADE_BRIGHT = "#2CC694"
JADE_MIST = "#E4F5EE"
LIGHT = "#F2F1ED"
WHITE = "#FFFFFF"

# Одноцветная версия красится тем, чем красится текст вокруг.
CURRENT = "currentColor"

PALETTE = frozenset({INK, PAPER, JADE, JADE_BRIGHT, JADE_MIST, LIGHT, WHITE})

# Раздел 4: при врезке в квадрат знак смещается вправо и вверх на 0.15x.
OPTICAL_SHIFT = 0.15

# Раздел 4: скругление плашки — 0.35 от стороны.
BADGE_RADIUS_RATIO = 0.35

# Доля стороны плашки, которую занимает знак. Оставшееся — охранное поле.
BADGE_SCALE = 0.7


@dataclass(frozen=True)
class Mark:
    """Одна версия знака: спираль, ядро, обводка и габарит.

    inner_radius — радиус витка, ближе всего подходящего к центру ядра.
    Из него считается зазор, который раздел 1 называет несущим элементом.
    """

    path: str
    core: tuple[float, float, float]
    stroke: float
    width: float
    height: float
    arcs: int
    inner_radius: float

    @property
    def unit(self) -> float:
        """Диаметр ядра — единица измерения раздела 4."""
        return self.core[2] * 2

    @property
    def gap(self) -> float:
        """Просвет между краем ядра и внутренним краем ближайшего витка."""
        return self.inner_radius - self.stroke / 2 - self.core[2]

    @property
    def terminus(self) -> float:
        """Абсцисса свободного конца внешнего витка — там, где разрыв."""
        return float(self.path.rsplit(" ", 2)[-2])


FULL = Mark(
    path="M78.5 42.5 A24 24 0 0 1 30.5 42.5 A36 36 0 0 1 102.5 42.5 A48 48 0 0 1 6.5 42.5",
    core=(54.5, 42.5, 8.0),
    stroke=13.0,
    width=109.0,
    height=97.0,
    arcs=3,
    inner_radius=24.0,
)

# Упрощённая версия для 16-32 px. Раздел 4 запрещает получать её уменьшением
# полного знака: у полного при ширине 16 px обводка выходит 1.9 px, а зазор
# 1.4 px, то есть тоньше пикселя после растеризации.
SMALL = Mark(
    path="M32.5 38.5 A30 30 0 0 1 92.5 38.5 A42 42 0 0 1 8.5 38.5",
    core=(62.5, 38.5, 10.5),
    stroke=17.0,
    width=101.0,
    height=89.0,
    arcs=2,
    inner_radius=30.0,
)

_HEADER = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}">'


def mark_markup(mark: Mark, stroke: str, core: str) -> str:
    """Спираль и ядро без обёртки — чтобы вставлять в другие композиции."""
    cx, cy, radius = mark.core
    return (
        f'<path d="{mark.path}" fill="none" stroke="{stroke}"'
        f' stroke-width="{mark.stroke:g}" stroke-linecap="round"/>'
        f'<circle cx="{cx:g}" cy="{cy:g}" r="{radius:g}" fill="{core}"/>'
    )


def mark_svg(mark: Mark, stroke: str, core: str) -> str:
    """Знак отдельным файлом, габарит по обводке."""
    header = _HEADER.format(width=mark.width, height=mark.height)
    return f"{header}{mark_markup(mark, stroke, core)}</svg>"


def badge_svg(
    mark: Mark,
    side: float,
    fill: str,
    stroke: str,
    core: str,
    *,
    scale: float = BADGE_SCALE,
    bleed: bool = False,
) -> str:
    """Знак, вписанный в скруглённый квадрат: аватарка, иконка приложения.

    При bleed знак крупнее плашки и обрезается ею — так требует раздел 8
    для аватара. Обрезка нужна именно clipPath: viewBox её не делает.
    """
    factor = side * scale / max(mark.width, mark.height)
    shift = OPTICAL_SHIFT * mark.unit * factor
    x = (side - mark.width * factor) / 2 + shift
    y = (side - mark.height * factor) / 2 - shift
    radius = side * BADGE_RADIUS_RATIO
    tile = f'<rect width="{side:g}" height="{side:g}" rx="{radius:g}" fill="{fill}"/>'
    body = (
        f'<g transform="translate({x:.2f} {y:.2f}) scale({factor:.4f})">'
        f"{mark_markup(mark, stroke, core)}</g>"
    )
    if bleed:
        clip = (
            f'<clipPath id="tile"><rect width="{side:g}" height="{side:g}"'
            f' rx="{radius:g}"/></clipPath>'
        )
        body = f'{clip}<g clip-path="url(#tile)">{body}</g>'
    header = _HEADER.format(width=side, height=side)
    return f"{header}{tile}{body}</svg>"
