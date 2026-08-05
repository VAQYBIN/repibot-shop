"""Снятие контуров вордмарка «re:pibot» с переменного Inter.

Самостоятельный SVG не должен зависеть от того, загрузился ли шрифт: GitHub
веб-шрифты в SVG не грузит вовсе, почтовые клиенты — тем более. Поэтому
в файлах бренд-набора надпись лежит контурами. В интерфейсе вордмарк остаётся
живым текстом: там шрифт есть, и текст переносится, выделяется и ищется.

Форму строки считает HarfBuzz, а не сумма ширин глифов: Inter кернит наши
пары, и без кернинга надпись выходит на 0.5 % шире, чем её же рисует браузер.

Результат пишется в wordmark_paths.py и коммитится: распаковка woff2 и
инстанцирование переменной оси стоят около секунды, а сборка SVG обязана
быть мгновенной — её гоняет verify_generated.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any

import uharfbuzz as hb
from fontTools.misc.transform import Transform
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[2]

# Шрифт берётся из пакета фронтенда, а не из отдельной копии: так версия
# в файлах бренда и версия на страницах не разъедутся.
FONT = (
    ROOT
    / "frontend/packages/ui/node_modules/@fontsource-variable/inter"
    / "files/inter-latin-wght-normal.woff2"
)
TARGET = Path(__file__).with_name("wordmark_paths.py")

TEXT = "re:pibot"
WEIGHT = 500  # Inter Medium, раздел 5 бренд-бука
TRACKING = -0.03  # em, там же


def _static_font() -> tuple[Any, bytes]:
    """Инстанцированный на Medium шрифт и он же в виде ttf для HarfBuzz.

    HarfBuzz не читает woff2, поэтому шрифт пересохраняется в память без
    сжатия. Отдельного файла на диске это не создаёт.
    """
    font = TTFont(FONT)
    font = instantiateVariableFont(font, {"wght": WEIGHT}, inplace=True, updateFontNames=False)
    buffer = io.BytesIO()
    font.flavor = None
    font.save(buffer)
    return font, buffer.getvalue()


def _outlines() -> tuple[str, str, float, Any]:
    font, raw = _static_font()
    units = font["head"].unitsPerEm
    order = font.getGlyphOrder()
    glyphs = font.getGlyphSet()

    shaped = hb.Buffer()
    shaped.add_str(TEXT)
    shaped.guess_segment_properties()
    hb.shape(hb.Font(hb.Face(raw)), shaped, {"kern": True, "liga": True})

    step = round(TRACKING * units)
    offset = 0.0
    letters: list[str] = []
    colon: list[str] = []
    for info, position in zip(shaped.glyph_infos, shaped.glyph_positions, strict=True):
        name = order[info.codepoint]
        pen = SVGPathPen(glyphs, ntos=lambda value: f"{round(value, 1):g}")
        # Ось Y в шрифте направлена вверх, в SVG — вниз, отсюда отражение.
        glyphs[name].draw(TransformPen(pen, Transform(1, 0, 0, -1, offset + position.x_offset, 0)))
        (colon if name == "colon" else letters).append(pen.getCommands())
        offset += position.x_advance + step
    # Трекинг после последнего знака в ширину не входит.
    return "".join(letters), "".join(colon), offset - step, font


def render() -> str:
    """Текст модуля с контурами. Отдельно от записи — чтобы проверять тестом."""
    letters, colon, advance, font = _outlines()
    return (
        '"""Контуры вордмарка. Файл сгенерирован tools/brand/wordmark_source.py.\n\n'
        "Руками не править: правки затрёт следующая генерация, а расхождение\n"
        'поймает verify_generated.\n"""\n\n'
        f"LETTERS = {letters!r}\n\n"
        f"COLON = {colon!r}\n\n"
        f"UNITS_PER_EM = {font['head'].unitsPerEm}\n"
        f"ADVANCE = {advance}\n"
        f"X_HEIGHT = {font['OS/2'].sxHeight}\n"
        f"CAP_HEIGHT = {font['OS/2'].sCapHeight}\n"
    )


def main() -> int:
    TARGET.write_text(render(), encoding="utf-8")
    print(f"Записан {TARGET.relative_to(ROOT)}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
