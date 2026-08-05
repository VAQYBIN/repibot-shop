# Бренд-набор Re:Pibot — план реализации

> **Для агентов:** ОБЯЗАТЕЛЬНЫЙ ПОДСКИЛЛ: используйте superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans для выполнения плана задача за задачей. Шаги размечены чекбоксами (`- [ ]`).

**Цель:** перевести знак Re:Pibot в вектор и собрать все файлы раздела 8 бренд-бука из одного описания геометрии, подключив результат к вебу и MiniApp.

**Архитектура:** параметры знака и палитра лежат в `tools/brand/geometry.py`. Контуры вордмарка снимаются со шрифта Inter один раз и коммитятся отдельным сгенерированным модулем, поэтому сборка SVG не зависит от шрифтовых библиотек. `tools/brand/build.py` собирает одиннадцать SVG, `frontend/packages/ui/scripts/raster-brand.mjs` растеризует из них шесть PNG через Chromium. SVG под контролем `verify_generated`, PNG — коммитятся как артефакты.

**Стек:** Python 3.13, fontTools, uharfbuzz, Playwright (Chromium), React 19, TypeScript 6, Vitest, pytest.

**Спецификация:** [docs/superpowers/specs/2026-08-05-brand-assets-design.md](../specs/2026-08-05-brand-assets-design.md)
**Бренд-бук:** [docs/design/repibot-brandbook.md](../../design/repibot-brandbook.md)

## Глобальные ограничения

- Ветка работы — `dev`. Отдельные ветки, если понадобятся, создаются от `dev`.
- Палитра только каноническая (раздел 2 бренд-бука): Ink `#1A1A18`, Paper `#FAF9F7`, Jade `#17A67C`, Jade Bright `#2CC694`, Jade Mist `#E4F5EE`, светлый `#F2F1ED`, белый `#FFFFFF`. Никаких других hex в файлах бренд-набора.
- Путь спирали полного знака: `M78.5 42.5 A24 24 0 0 1 30.5 42.5 A36 36 0 0 1 102.5 42.5 A48 48 0 0 1 6.5 42.5`, `viewBox="0 0 109 97"`.
- Путь спирали упрощённого знака: `M32.5 38.5 A30 30 0 0 1 92.5 38.5 A42 42 0 0 1 8.5 38.5`, `viewBox="0 0 101 89"`.
- Комментарии, докстринги, сообщения и тексты — на русском, как во всём репозитории.
- Каждая задача заканчивается прогоном `uv run check` без ошибок и одним коммитом.
- Секретов в файлы не попадает: бренд-набор состоит из общедоступной графики.

---

## Структура файлов

| Файл | Ответственность |
|---|---|
| `tools/brand/__init__.py` | пустой, делает пакет |
| `tools/brand/geometry.py` | палитра, параметры знака, сборка SVG-разметки |
| `tools/brand/wordmark_source.py` | снятие контуров с Inter, пишет `wordmark_paths.py` |
| `tools/brand/wordmark_paths.py` | сгенерированный: контуры букв, двоеточия и метрики |
| `tools/brand/build.py` | композиции, запись одиннадцати SVG и копий |
| `frontend/packages/ui/scripts/raster-brand.mjs` | SVG → PNG через Chromium |
| `frontend/packages/ui/src/components/logo-mark.tsx` | знак как React-компонент |
| `tools/tests/test_brand.py` | инварианты геометрии, палитры и файлов |
| `tools/tests/test_wordmark.py` | контуры вордмарка |

---

## Задача 1: Геометрия и палитра

**Файлы:**
- Создать: `tools/brand/__init__.py`
- Создать: `tools/brand/geometry.py`
- Тест: `tools/tests/test_brand.py`

**Интерфейсы:**
- Отдаёт: `INK`, `PAPER`, `JADE`, `JADE_BRIGHT`, `JADE_MIST`, `LIGHT`, `WHITE`, `CURRENT`, `PALETTE: frozenset[str]`; класс `Mark` с полями `path: str`, `core: tuple[float, float, float]`, `stroke: float`, `width: float`, `height: float`, `arcs: int`, `inner_radius: float` и свойствами `unit: float`, `gap: float`, `terminus: float`; константы `FULL: Mark`, `SMALL: Mark`; функции `mark_markup(mark: Mark, stroke: str, core: str) -> str`, `mark_svg(mark: Mark, stroke: str, core: str) -> str`, `badge_svg(mark: Mark, side: float, fill: str, stroke: str, core: str, *, scale: float = 0.7, bleed: bool = False) -> str`.

- [ ] **Шаг 1: Написать падающий тест**

Создать `tools/tests/test_brand.py`:

```python
"""Инварианты знака. Проверяются арифметикой по параметрам, а не глазами.

Бренд-бук задаёт зазор, толщину обводки и минимальные размеры числами —
значит, их можно и нужно проверять машинно. Глазами проверяется только то,
что бренд-бук прямо называет оптическим.
"""

import re

import pytest

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
    assert PALETTE == {
        "#1A1A18",
        "#FAF9F7",
        "#17A67C",
        "#2CC694",
        "#E4F5EE",
        "#F2F1ED",
        "#FFFFFF",
    }
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запустить: `uv run pytest tools/tests/test_brand.py -q`
Ожидается: FAIL с `ModuleNotFoundError: No module named 'tools.brand'`

- [ ] **Шаг 3: Написать геометрию**

Создать пустой `tools/brand/__init__.py` и `tools/brand/geometry.py`:

```python
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
```

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Запустить: `uv run pytest tools/tests/test_brand.py -q`
Ожидается: PASS, 11 тестов

- [ ] **Шаг 5: Прогнать полную проверку**

Запустить: `uv run check`
Ожидается: «Все проверки пройдены.»

- [ ] **Шаг 6: Коммит**

```bash
git add tools/brand/__init__.py tools/brand/geometry.py tools/tests/test_brand.py
git commit -m "feat: геометрия знака и палитра бренда в одном модуле"
```

---

## Задача 2: Контуры вордмарка

**Файлы:**
- Создать: `tools/brand/wordmark_source.py`
- Создать (генерацией): `tools/brand/wordmark_paths.py`
- Изменить: `pyproject.toml`
- Тест: `tools/tests/test_wordmark.py`

**Интерфейсы:**
- Потребляет: ничего из предыдущих задач.
- Отдаёт: модуль `tools.brand.wordmark_paths` с константами `LETTERS: str`, `COLON: str`, `UNITS_PER_EM: int`, `ADVANCE: float`, `X_HEIGHT: int`, `CAP_HEIGHT: int`. Функция `tools.brand.wordmark_source.render() -> str` возвращает текст модуля, `main() -> int` его записывает.

**Почему отдельным сгенерированным модулем.** Снятие контуров стоит секунду: шрифт распаковывается из woff2, переменная ось инстанцируется на 500, строка прогоняется через HarfBuzz. Если делать это при каждой сборке SVG, проверка `verify_generated` начнёт заметно тормозить `uv run check`. Результат детерминирован, поэтому он коммитится и проверяется как обычный сгенерированный файл.

**Почему HarfBuzz, а не сумма ширин глифов.** Inter кернит пары нашей надписи. Измерено: сумма ширин даёт 7598 единиц, HarfBuzz — 7559, Chromium рисует ровно 7559. Без кернинга файловый вордмарк был бы на 0.5 % шире того же вордмарка на странице.

- [ ] **Шаг 1: Добавить зависимости**

В `pyproject.toml` в группу `dev` добавить две строки после `"types-pyyaml>=6.0",`:

```toml
    "fonttools[woff]>=4.55",
    "uharfbuzz>=0.45",
```

Там же добавить исключение для генерируемого модуля — строки контуров длиной в тысячи символов не переносятся:

```toml
[tool.ruff]
extend-exclude = ["docs", "**/integrations/remnawave/models.py", "tools/brand/wordmark_paths.py"]
```

И разрешить mypy импорт библиотек без разметки типов, в конец файла:

```toml
[[tool.mypy.overrides]]
module = ["fontTools.*", "uharfbuzz"]
ignore_missing_imports = true
```

Запустить: `uv sync`
Ожидается: пакеты `fonttools` и `uharfbuzz` установлены

- [ ] **Шаг 2: Написать падающий тест**

Создать `tools/tests/test_wordmark.py`:

```python
"""Вордмарк в кривых.

Двоеточие — часть марки, а не пунктуация (раздел 5), поэтому оно лежит
отдельным контуром: иначе его нельзя покрасить в Jade.
"""

from tools.brand import wordmark_paths
from tools.brand.wordmark_source import render


def test_letters_and_colon_are_separate_shapes() -> None:
    assert wordmark_paths.LETTERS.startswith("M")
    assert wordmark_paths.COLON.startswith("M")
    assert wordmark_paths.COLON not in wordmark_paths.LETTERS


def test_all_seven_letters_are_present() -> None:
    """re + pibot — семь букв, каждая начинается своей командой M."""
    assert wordmark_paths.LETTERS.count("M") >= 7


def test_colon_is_two_dots() -> None:
    assert wordmark_paths.COLON.count("M") == 2


def test_metrics_match_inter() -> None:
    assert wordmark_paths.UNITS_PER_EM == 2048
    assert wordmark_paths.X_HEIGHT == 1118
    assert wordmark_paths.CAP_HEIGHT == 1490


def test_kerning_is_applied() -> None:
    """Сумма ширин глифов дала бы 7171. HarfBuzz с кернингом — 7132."""
    assert wordmark_paths.ADVANCE == 7132.0


def test_generation_is_deterministic() -> None:
    """Иначе verify_generated будет ругаться при каждом прогоне."""
    assert render() == render()
```

- [ ] **Шаг 3: Запустить тест и убедиться, что он падает**

Запустить: `uv run pytest tools/tests/test_wordmark.py -q`
Ожидается: FAIL с `ModuleNotFoundError: No module named 'tools.brand.wordmark_paths'`

- [ ] **Шаг 4: Написать генератор**

Создать `tools/brand/wordmark_source.py`:

```python
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


def _static_font() -> tuple[TTFont, bytes]:
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


def _outlines() -> tuple[str, str, float, TTFont]:
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
```

- [ ] **Шаг 5: Сгенерировать модуль**

Запустить: `uv run python tools/brand/wordmark_source.py`
Ожидается: `Записан tools\brand\wordmark_paths.py`

- [ ] **Шаг 6: Запустить тест и убедиться, что он проходит**

Запустить: `uv run pytest tools/tests/test_wordmark.py -q`
Ожидается: PASS, 6 тестов

- [ ] **Шаг 7: Прогнать полную проверку**

Запустить: `uv run check`
Ожидается: «Все проверки пройдены.»

- [ ] **Шаг 8: Коммит**

```bash
git add pyproject.toml uv.lock tools/brand/wordmark_source.py tools/brand/wordmark_paths.py tools/tests/test_wordmark.py
git commit -m "feat: контуры вордмарка из Inter с кернингом HarfBuzz"
```

---

## Задача 3: Одна команда генерации — несколько файлов

**Файлы:**
- Изменить: `tools/verify_generated.py:23-48` и `tools/verify_generated.py:70-105`
- Тест: `tools/tests/test_verify_generated.py`

**Интерфейсы:**
- Отдаёт: `Generated(paths: tuple[Path, ...], command: list[str], cwd: Path)` вместо прежнего `path: Path`. Функция `verify_generated(entries, root)` возвращает список строк-путей, как и раньше.

**Зачем.** Сборка бренда выдаёт тринадцать файлов одной командой. При нынешнем устройстве пришлось бы объявить тринадцать записей, и генератор запустился бы тринадцать раз — тринадцать лишних запусков `uv` на каждой проверке.

- [ ] **Шаг 1: Написать падающий тест**

Добавить в конец `tools/tests/test_verify_generated.py`:

```python
def test_one_command_can_own_several_files(tmp_path: Path) -> None:
    """Генератор бренда выдаёт тринадцать файлов за один запуск."""
    first = tmp_path / "one.txt"
    second = tmp_path / "two.txt"
    first.write_text("одно", encoding="utf-8")
    second.write_text("устарело", encoding="utf-8")

    code = (
        f"import pathlib;"
        f" pathlib.Path({str(first)!r}).write_text('одно', encoding='utf-8');"
        f" pathlib.Path({str(second)!r}).write_text('другое', encoding='utf-8')"
    )
    entry = Generated(
        paths=(Path("one.txt"), Path("two.txt")),
        command=[sys.executable, "-c", code],
        cwd=tmp_path,
    )

    assert verify_generated([entry], root=tmp_path) == ["two.txt"]
    assert second.read_text(encoding="utf-8") == "устарело"
```

В том же файле заменить все существующие вызовы `Generated(path=...)` на `Generated(paths=(...,))`. Затронуты `test_stale_file_keeps_its_committed_content`, `test_up_to_date_file_is_reported_as_current`, `test_failed_generator_does_not_leave_the_file_damaged`, `test_missing_generator_is_reported_without_a_traceback`, `test_absent_file_is_not_left_behind`. Пример замены:

```python
    entry = Generated(
        paths=(target.relative_to(tmp_path),),
        command=_writer(target, "другое"),
        cwd=tmp_path,
    )
```

И заменить `test_generated_files_are_declared`:

```python
def test_generated_files_are_declared() -> None:
    paths = {path for entry in GENERATED for path in entry.paths}

    assert Path("frontend/packages/core/src/api/openapi.json") in paths
    assert Path("frontend/packages/core/src/api/schema.d.ts") in paths
    assert Path("backend/core/src/repibot_core/integrations/remnawave/models.py") in paths
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запустить: `uv run pytest tools/tests/test_verify_generated.py -q`
Ожидается: FAIL с `TypeError: Generated.__init__() got an unexpected keyword argument 'paths'`

- [ ] **Шаг 3: Переписать модуль**

В `tools/verify_generated.py` заменить объявление датакласса и список:

```python
@dataclass(frozen=True)
class Generated:
    """Файлы под контролем генерации и команда, которая их создаёт.

    Одна команда может выдавать несколько файлов: сборка бренда пишет
    тринадцать за раз, и запускать её тринадцать раз было бы расточительно.
    """

    paths: tuple[Path, ...]
    command: list[str]
    cwd: Path


GENERATED: list[Generated] = [
    Generated(
        paths=(Path("frontend/packages/core/src/api/openapi.json"),),
        command=["uv", "run", "export-openapi"],
        cwd=ROOT,
    ),
    Generated(
        paths=(Path("frontend/packages/core/src/api/schema.d.ts"),),
        command=["pnpm", "--filter", "@repibot/core", "gen:api"],
        cwd=ROOT / "frontend",
    ),
    Generated(
        paths=(Path("backend/core/src/repibot_core/integrations/remnawave/models.py"),),
        command=["uv", "run", "python", "tools/gen_remnawave_models.py"],
        cwd=ROOT,
    ),
]
```

И заменить тело `verify_generated`:

```python
def verify_generated(entries: list[Generated] | None = None, root: Path = ROOT) -> list[str]:
    """Перегенерирует файлы и возвращает пути тех, что разошлись.

    Исходное содержимое восстанавливается в любом случае: проверка сообщает
    о расхождении, но не правит рабочее дерево за разработчика.
    """
    stale: list[str] = []
    for entry in entries if entries is not None else GENERATED:
        targets = [root / path for path in entry.paths]
        before = [target.read_bytes() if target.exists() else None for target in targets]

        produced: list[bytes | None] = []
        try:
            subprocess.run(_resolve(entry.command), cwd=entry.cwd, check=True)  # noqa: S603
        except FileNotFoundError:
            # Нет pnpm или uv — это сообщение, а не трассировка.
            print(f"команда не найдена: {entry.command[0]}", flush=True)  # noqa: T201
            stale.extend(str(path) for path in entry.paths)
            continue
        finally:
            # Снимок и восстановление именно в finally: упавший генератор мог
            # успеть записать половину файла, и без восстановления проверка
            # испортила бы ровно то, что должна была защитить.
            for target, original in zip(targets, before, strict=True):
                produced.append(target.read_bytes() if target.exists() else None)
                if original is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(original)

        for path, original, current in zip(entry.paths, before, produced, strict=True):
            if current is None or _normalise(current.decode("utf-8")) != _normalise(
                (original or b"").decode("utf-8")
            ):
                stale.append(str(path))
    return stale
```

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Запустить: `uv run pytest tools/tests/test_verify_generated.py -q`
Ожидается: PASS, 10 тестов

- [ ] **Шаг 5: Прогнать полную проверку**

Запустить: `uv run check`
Ожидается: «Все проверки пройдены.»

- [ ] **Шаг 6: Коммит**

```bash
git add tools/verify_generated.py tools/tests/test_verify_generated.py
git commit -m "refactor: одна команда генерации может владеть несколькими файлами"
```

---

## Задача 4: Сборка SVG

**Файлы:**
- Создать: `tools/brand/build.py`
- Изменить: `pyproject.toml` (точка входа `build-brand`)
- Изменить: `tools/verify_generated.py` (две новые записи)
- Изменить: `tools/tests/test_brand.py` (проверки файлов)
- Создать генерацией: одиннадцать SVG в `docs/design/logo/` и две копии `favicon.svg`

**Интерфейсы:**
- Потребляет: `tools.brand.geometry` (`FULL`, `SMALL`, `mark_svg`, `badge_svg`, `mark_markup`, палитра), `tools.brand.wordmark_paths` (`LETTERS`, `COLON`, `UNITS_PER_EM`, `ADVANCE`, `X_HEIGHT`).
- Отдаёт: `tools.brand.build.main() -> int`; константы `LOGO_DIR: Path`, `FILES: dict[str, str]` (имя файла → содержимое), `COPIES: tuple[tuple[str, Path], ...]`.

**Композиции.** Кегль вордмарка — 0.485 высоты знака, как в утверждённом оригинале. Просвет между знаком и надписью — высота строчной `x` (раздел 5). Надпись выравнивается по оптическому центру: середина полосы строчных совпадает с серединой знака.

- [ ] **Шаг 1: Написать падающий тест**

В `tools/tests/test_brand.py` дописать импорты к уже существующим, в начало файла:

```python
from pathlib import Path

from tools.brand.build import FILES, LOGO_DIR
```

И добавить в конец файла:

```python
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
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запустить: `uv run pytest tools/tests/test_brand.py -q`
Ожидается: FAIL с `ModuleNotFoundError: No module named 'tools.brand.build'`

- [ ] **Шаг 3: Написать сборку**

Создать `tools/brand/build.py`:

```python
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
)
from tools.brand.wordmark_paths import ADVANCE, COLON, LETTERS, UNITS_PER_EM, X_HEIGHT

ROOT = Path(__file__).resolve().parents[2]
LOGO_DIR = ROOT / "docs" / "design" / "logo"

# Кегль вордмарка относительно высоты знака — из утверждённого оригинала.
FONT_RATIO = 0.485

OG_WIDTH = 1200
OG_HEIGHT = 630

_HEADER = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}">'


def _wordmark_group(scale: float, x: float, baseline: float, letters: str, colon: str) -> str:
    return (
        f'<g transform="translate({x:.2f} {baseline:.2f}) scale({scale:.6f})">'
        f'<path d="{LETTERS}" fill="{letters}"/>'
        f'<path d="{COLON}" fill="{colon}"/></g>'
    )


def wordmark_svg(letters: str = INK, colon: str = JADE, size: float = 100.0) -> str:
    """Только надпись. Габарит — по ширине строки и полосе прописных."""
    scale = size / UNITS_PER_EM
    width = ADVANCE * scale
    height = size
    header = _HEADER.format(width=width, height=height)
    return f"{header}{_wordmark_group(scale, 0, height * 0.78, letters, colon)}</svg>"


def lockup_h_svg(mark: Mark = FULL, letters: str = INK, colon: str = JADE) -> str:
    """Знак слева, вордмарк справа. Просвет — высота строчной x, раздел 5."""
    size = mark.height * FONT_RATIO
    scale = size / UNITS_PER_EM
    gap = X_HEIGHT * scale
    x = mark.width + gap
    # Оптический центр надписи — середина полосы строчных, а не базовая линия.
    baseline = mark.height / 2 + X_HEIGHT * scale / 2
    header = _HEADER.format(width=x + ADVANCE * scale, height=mark.height)
    return (
        f"{header}{mark_markup(mark, INK, JADE)}"
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
    return f"{_HEADER.format(width=width, height=height)}{body}</svg>"


def og_image_svg() -> str:
    """Открытый граф: знак на Ink, вордмарк под ним. Раздел 8.

    На Ink обычный Jade мутнеет, поэтому ядро — Jade Bright, раздел 2.
    """
    body, width, height = _lockup_v_body(FULL, LIGHT, JADE_BRIGHT, LIGHT, JADE_BRIGHT)
    # Лок-ап занимает половину высоты холста, остальное — воздух.
    scale = OG_HEIGHT * 0.5 / height
    x = (OG_WIDTH - width * scale) / 2
    y = (OG_HEIGHT - height * scale) / 2
    header = _HEADER.format(width=OG_WIDTH, height=OG_HEIGHT)
    return (
        f'{header}<rect width="{OG_WIDTH}" height="{OG_HEIGHT}" fill="{INK}"/>'
        f'<g transform="translate({x:.2f} {y:.2f}) scale({scale:.4f})">{body}</g></svg>'
    )


FILES: dict[str, str] = {
    "logo-mark.svg": mark_svg(FULL, INK, JADE),
    "logo-mark-mono.svg": mark_svg(FULL, CURRENT, CURRENT),
    "logo-mark-small.svg": mark_svg(SMALL, INK, JADE),
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
```

- [ ] **Шаг 4: Объявить точку входа**

В `pyproject.toml` в `[project.scripts]` добавить строку:

```toml
build-brand = "tools.brand.build:main"
```

- [ ] **Шаг 5: Собрать файлы**

Запустить: `uv run build-brand`
Ожидается: `Собрано файлов: 13`

- [ ] **Шаг 6: Запустить тест и убедиться, что он проходит**

Запустить: `uv run pytest tools/tests/test_brand.py -q`
Ожидается: PASS

- [ ] **Шаг 7: Зарегистрировать файлы в verify_generated**

В `tools/verify_generated.py` добавить в конец списка `GENERATED`:

```python
    Generated(
        paths=(Path("tools/brand/wordmark_paths.py"),),
        command=["uv", "run", "python", "tools/brand/wordmark_source.py"],
        cwd=ROOT,
    ),
    Generated(
        paths=(
            Path("docs/design/logo/logo-mark.svg"),
            Path("docs/design/logo/logo-mark-mono.svg"),
            Path("docs/design/logo/logo-mark-small.svg"),
            Path("docs/design/logo/wordmark.svg"),
            Path("docs/design/logo/logo-lockup-h.svg"),
            Path("docs/design/logo/logo-lockup-v.svg"),
            Path("docs/design/logo/badge.svg"),
            Path("docs/design/logo/badge-inverse.svg"),
            Path("docs/design/logo/favicon.svg"),
            Path("docs/design/logo/avatar.svg"),
            Path("docs/design/logo/og-image.svg"),
            Path("frontend/apps/web/public/favicon.svg"),
            Path("frontend/apps/miniapp/public/favicon.svg"),
        ),
        command=["uv", "run", "build-brand"],
        cwd=ROOT,
    ),
```

- [ ] **Шаг 8: Прогнать полную проверку**

Запустить: `uv run check`
Ожидается: «Все проверки пройдены.», в разделе `generated` — `Собрано файлов: 13`

- [ ] **Шаг 9: Убедиться, что расхождение ловится**

```bash
python -c "import pathlib; p = pathlib.Path('docs/design/logo/logo-mark.svg'); p.write_text(p.read_text(encoding='utf-8').replace('#17A67C', '#FF0000'), encoding='utf-8')"
uv run verify-generated
git checkout docs/design/logo/logo-mark.svg
```

Ожидается: `Сгенерированные файлы устарели:` и в списке `docs/design/logo/logo-mark.svg`. После `git checkout` файл возвращается на место.

- [ ] **Шаг 10: Коммит**

```bash
git add pyproject.toml tools/brand/build.py tools/verify_generated.py tools/tests/test_brand.py docs/design/logo frontend/apps/web/public/favicon.svg frontend/apps/miniapp/public/favicon.svg
git commit -m "feat: одиннадцать векторов бренд-набора из одного источника"
```

---

## Задача 5: Растеризация

**Файлы:**
- Создать: `frontend/packages/ui/scripts/raster-brand.mjs`
- Изменить: `frontend/packages/ui/package.json`
- Изменить: `CONTRIBUTING.md`
- Создать генерацией: шесть PNG в `docs/design/logo/raster/` и четыре копии в `frontend/apps/web/public/`
- Тест: `tools/tests/test_brand.py`

**Интерфейсы:**
- Потребляет: SVG из `docs/design/logo/`, собранные задачей 4.
- Отдаёт: команду `pnpm --filter @repibot/ui brand:raster`.

**Почему PNG не под verify_generated.** Прогон Chromium на каждой проверке медленный, а байты рендера меняются от версии браузера — расхождение срабатывало бы на пустом месте. Растры пересобираются вручную и коммитятся.

- [ ] **Шаг 1: Написать падающий тест**

Добавить в конец `tools/tests/test_brand.py`:

```python
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
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запустить: `uv run pytest tools/tests/test_brand.py -q -k "raster or graph"`
Ожидается: FAIL с `FileNotFoundError` на `docs/design/logo/raster/favicon-16.png`

- [ ] **Шаг 3: Добавить Playwright в пакет интерфейса**

В `frontend/packages/ui/package.json` в `scripts` добавить:

```json
    "brand:raster": "node scripts/raster-brand.mjs"
```

В `devDependencies` добавить:

```json
    "playwright": "^1.62.0"
```

Запустить: `pnpm install` из `frontend`
Ожидается: установка без ошибок

- [ ] **Шаг 4: Написать растеризатор**

Создать `frontend/packages/ui/scripts/raster-brand.mjs`:

```js
/**
 * Растеризация бренд-набора: SVG → PNG через Chromium.
 *
 * Браузер здесь не прихоть: это единственный движок, которым мы и так
 * пользуемся, и он рисует SVG ровно так же, как увидит пользователь.
 *
 * Результат коммитится и под verify_generated не попадает — байты рендера
 * зависят от версии Chromium, и проверка ругалась бы после каждого его
 * обновления.
 *
 * Браузер ставится командой из CONTRIBUTING.md:
 *   pnpm --filter @repibot/web exec playwright install chromium
 */
import { copyFileSync, mkdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')
const LOGO = resolve(ROOT, 'docs/design/logo')
const RASTER = resolve(LOGO, 'raster')
const WEB = resolve(ROOT, 'frontend/apps/web/public')

const JOBS = [
  { svg: 'favicon.svg', out: 'favicon-16.png', width: 16, height: 16 },
  { svg: 'favicon.svg', out: 'favicon-32.png', width: 32, height: 32 },
  { svg: 'badge.svg', out: 'icon-192.png', width: 192, height: 192 },
  { svg: 'badge.svg', out: 'icon-512.png', width: 512, height: 512 },
  { svg: 'avatar.svg', out: 'avatar-512.png', width: 512, height: 512 },
  { svg: 'og-image.svg', out: 'og-image.png', width: 1200, height: 630 },
]

// og-image остаётся в бренд-наборе: страниц, которыми делятся, пока нет,
// а класть в public файл без потребителя незачем.
const COPIES = ['favicon-16.png', 'favicon-32.png', 'icon-192.png', 'icon-512.png']

mkdirSync(RASTER, { recursive: true })

const browser = await chromium.launch()
try {
  for (const job of JOBS) {
    const svg = readFileSync(resolve(LOGO, job.svg))
    const source = `data:image/svg+xml;base64,${svg.toString('base64')}`
    const page = await browser.newPage({
      viewport: { width: job.width, height: job.height },
      deviceScaleFactor: 1,
    })
    await page.setContent(
      `<style>html,body{margin:0;padding:0}img{display:block;width:100%;height:100%}</style>` +
        `<img src="${source}">`,
    )
    await page.screenshot({ path: resolve(RASTER, job.out), omitBackground: true })
    await page.close()
    console.log(`${job.out} ${job.width}×${job.height}`)
  }
} finally {
  await browser.close()
}

for (const name of COPIES) {
  copyFileSync(resolve(RASTER, name), resolve(WEB, name))
}
console.log(`Скопировано в веб: ${COPIES.length}`)
```

- [ ] **Шаг 5: Собрать растры**

```bash
pnpm --filter @repibot/web exec playwright install chromium
pnpm --filter @repibot/ui brand:raster
```

Ожидается: шесть строк с размерами и `Скопировано в веб: 4`

- [ ] **Шаг 6: Посмотреть результат глазами**

Открыть `docs/design/logo/raster/favicon-16.png`, `icon-512.png`, `avatar-512.png` и `og-image.png`. Проверить по разделу 4 бренд-бука: ядро не касается витка, знак в плашке смотрится смещённым вправо и вверх, у аватара знак выходит за края, а ядро остаётся в кадре.

Если знак в плашке визуально проваливается вниз или влево — править `OPTICAL_SHIFT` в `tools/brand/geometry.py`, пересобирать `uv run build-brand` и растеризовать заново. Раздел 4 прямо требует проверять это глазами, а не координатами.

- [ ] **Шаг 7: Запустить тест и убедиться, что он проходит**

Запустить: `uv run pytest tools/tests/test_brand.py -q`
Ожидается: PASS

- [ ] **Шаг 8: Описать команды в CONTRIBUTING**

Добавить в `CONTRIBUTING.md` раздел:

```markdown
## Бренд-набор

Векторы собираются из одного описания геометрии:

```bash
uv run build-brand
```

Растры пересобираются отдельно — им нужен браузер:

```bash
pnpm --filter @repibot/web exec playwright install chromium
pnpm --filter @repibot/ui brand:raster
```

Контуры вордмарка снимаются со шрифта и обновляются только при смене
гарнитуры или начертания:

```bash
uv run python tools/brand/wordmark_source.py
```

Файлы в `docs/design/logo` руками не правятся: расхождение с генератором
роняет `uv run check`.
```

- [ ] **Шаг 9: Прогнать полную проверку**

Запустить: `uv run check`
Ожидается: «Все проверки пройдены.»

- [ ] **Шаг 10: Коммит**

```bash
git add frontend/packages/ui/package.json frontend/packages/ui/scripts frontend/pnpm-lock.yaml docs/design/logo/raster frontend/apps/web/public CONTRIBUTING.md tools/tests/test_brand.py
git commit -m "feat: растеризация бренд-набора через Chromium"
```

---

## Задача 6: Знак как React-компонент

**Файлы:**
- Создать: `frontend/packages/ui/src/components/logo-mark.tsx`
- Создать: `frontend/packages/ui/src/components/logo-mark.test.tsx`
- Изменить: `frontend/packages/ui/src/index.ts`
- Изменить: `tools/tests/test_brand.py`

**Интерфейсы:**
- Отдаёт: `LogoMark` с пропсами `SVGProps<SVGSVGElement>` без `viewBox` плюс `variant?: 'full' | 'small'`; тип `LogoMarkProps`; тип `LogoMarkVariant`. Экспортируется из `@repibot/ui`.

- [ ] **Шаг 1: Написать падающий тест**

Создать `frontend/packages/ui/src/components/logo-mark.test.tsx`:

```tsx
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { LogoMark } from './logo-mark'

describe('LogoMark', () => {
  it('рисует спираль и отдельное ядро', () => {
    const { container } = render(<LogoMark />)

    expect(container.querySelector('path')).not.toBeNull()
    expect(container.querySelector('circle')).not.toBeNull()
  })

  it('красит спираль текущим цветом, а ядро — акцентом темы', () => {
    const { container } = render(<LogoMark />)

    expect(container.querySelector('path')?.getAttribute('stroke')).toBe('currentColor')
    expect(container.querySelector('circle')?.getAttribute('fill')).toBe('var(--rp-accent)')
  })

  it('упрощённая версия — один виток вместо полутора', () => {
    const { container } = render(<LogoMark variant="small" />)
    const path = container.querySelector('path')?.getAttribute('d') ?? ''

    expect((path.match(/A/g) ?? []).length).toBe(2)
  })

  it('полная версия — три дуги', () => {
    const { container } = render(<LogoMark />)
    const path = container.querySelector('path')?.getAttribute('d') ?? ''

    expect((path.match(/A/g) ?? []).length).toBe(3)
  })

  it('пропускает наружные атрибуты', () => {
    const { container } = render(<LogoMark height={24} aria-label="Re:Pibot" />)

    expect(container.querySelector('svg')?.getAttribute('height')).toBe('24')
    expect(container.querySelector('svg')?.getAttribute('aria-label')).toBe('Re:Pibot')
  })
})
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запустить: `pnpm --filter @repibot/ui test` из `frontend`
Ожидается: FAIL, модуль `./logo-mark` не найден

- [ ] **Шаг 3: Написать компонент**

Создать `frontend/packages/ui/src/components/logo-mark.tsx`:

```tsx
import type { SVGProps } from 'react'

/**
 * Знак Re:Pibot.
 *
 * Обводка — currentColor, ядро — акцент темы, поэтому отдельного файла под
 * тёмную тему не нужно: цвет приходит из окружения.
 *
 * Геометрия продублирована из tools/brand/geometry.py. Дублирование
 * намеренное — интерфейс не должен зависеть от сборки файлов, — и оно
 * заперто тестом tools/tests/test_brand.py, который сверяет обе копии.
 */
const MARKS = {
  full: {
    viewBox: '0 0 109 97',
    path: 'M78.5 42.5 A24 24 0 0 1 30.5 42.5 A36 36 0 0 1 102.5 42.5 A48 48 0 0 1 6.5 42.5',
    core: { cx: 54.5, cy: 42.5, r: 8 },
    strokeWidth: 13,
  },
  // Ниже 32 px полный знак слипается: внутренний виток сходится с ядром.
  // Раздел 4 бренд-бука запрещает решать это уменьшением полной версии.
  small: {
    viewBox: '0 0 101 89',
    path: 'M32.5 38.5 A30 30 0 0 1 92.5 38.5 A42 42 0 0 1 8.5 38.5',
    core: { cx: 62.5, cy: 38.5, r: 10.5 },
    strokeWidth: 17,
  },
} as const

export type LogoMarkVariant = keyof typeof MARKS

export interface LogoMarkProps extends Omit<SVGProps<SVGSVGElement>, 'viewBox'> {
  variant?: LogoMarkVariant
}

export function LogoMark({ variant = 'full', ...props }: LogoMarkProps) {
  const mark = MARKS[variant]
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox={mark.viewBox} fill="none" {...props}>
      <path
        d={mark.path}
        stroke="currentColor"
        strokeWidth={mark.strokeWidth}
        strokeLinecap="round"
      />
      <circle cx={mark.core.cx} cy={mark.core.cy} r={mark.core.r} fill="var(--rp-accent)" />
    </svg>
  )
}
```

- [ ] **Шаг 4: Экспортировать компонент**

В `frontend/packages/ui/src/index.ts` добавить первой строкой:

```ts
export { LogoMark, type LogoMarkProps, type LogoMarkVariant } from './components/logo-mark'
```

- [ ] **Шаг 5: Запустить тест и убедиться, что он проходит**

Запустить: `pnpm --filter @repibot/ui test` из `frontend`
Ожидается: PASS, 5 новых тестов

- [ ] **Шаг 6: Запереть совпадение геометрии тестом**

Добавить в конец `tools/tests/test_brand.py`:

```python
def test_component_draws_the_same_spiral_as_the_files() -> None:
    """Знак на странице и знак в файле обязаны быть одной фигурой."""
    component = (
        ROOT / "frontend/packages/ui/src/components/logo-mark.tsx"
    ).read_text(encoding="utf-8")

    assert FULL.path in component
    assert SMALL.path in component
    assert f"strokeWidth: {FULL.stroke:g}" in component
    assert f"strokeWidth: {SMALL.stroke:g}" in component
```

- [ ] **Шаг 7: Прогнать полную проверку**

Запустить: `uv run check`
Ожидается: «Все проверки пройдены.»

- [ ] **Шаг 8: Коммит**

```bash
git add frontend/packages/ui/src/components/logo-mark.tsx frontend/packages/ui/src/components/logo-mark.test.tsx frontend/packages/ui/src/index.ts tools/tests/test_brand.py
git commit -m "feat: знак Re:Pibot как компонент интерфейса"
```

---

## Задача 7: Подключение к вебу и MiniApp

**Файлы:**
- Изменить: `frontend/apps/web/src/components/lockup.tsx`
- Создать: `frontend/apps/web/src/components/lockup.test.tsx`
- Изменить: `frontend/apps/web/src/app/layout.tsx`
- Создать: `frontend/apps/web/public/manifest.webmanifest`
- Изменить: `frontend/apps/miniapp/index.html`
- Удалить: `frontend/apps/web/public/favicon.png`, `frontend/apps/web/public/brand/`, `frontend/apps/miniapp/public/brand/`, `docs/design/logo-light.png`, `docs/design/logo-dark.png`, `docs/design/lock-up-light.png`, `docs/design/lock-up-dark.png`
- Тест: `tools/tests/test_brand.py`

**Интерфейсы:**
- Потребляет: `LogoMark` из `@repibot/ui` (задача 6), `favicon.svg` и PNG-иконки (задачи 4 и 5).
- Отдаёт: `Lockup({ size }: { size?: number })` — прежняя сигнатура, чтобы `page.tsx` не менялся.

- [ ] **Шаг 1: Написать падающий тест**

Создать `frontend/apps/web/src/components/lockup.test.tsx`:

```tsx
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Lockup } from './lockup'

describe('Lockup', () => {
  it('не тянет ни одного растра', () => {
    const { container } = render(<Lockup />)

    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('на малых размерах берёт упрощённый знак', () => {
    const { container } = render(<Lockup size={24} />)
    const path = container.querySelector('path')?.getAttribute('d') ?? ''

    expect((path.match(/A/g) ?? []).length).toBe(2)
  })

  it('на обычных размерах берёт полный знак', () => {
    const { container } = render(<Lockup size={48} />)
    const path = container.querySelector('path')?.getAttribute('d') ?? ''

    expect((path.match(/A/g) ?? []).length).toBe(3)
  })

  it('показывает вордмарк с двоеточием', () => {
    const { getByText } = render(<Lockup />)

    expect(getByText(':')).toBeInTheDocument()
  })
})
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запустить: `pnpm --filter @repibot/web test` из `frontend`
Ожидается: FAIL — `Lockup` рисует `<img>`

- [ ] **Шаг 3: Переписать лок-ап**

Заменить `frontend/apps/web/src/components/lockup.tsx` целиком:

```tsx
import { LogoMark } from '@repibot/ui'

import { Wordmark } from './wordmark'

// Кегль вордмарка относительно высоты знака — из утверждённого оригинала,
// те же числа в tools/brand/build.py.
const FONT_RATIO = 0.485
// Высота строчной x в Inter: 1118 из 2048 единиц. Раздел 5 задаёт просвет
// между знаком и надписью равным именно ей.
const X_HEIGHT_RATIO = 0.546

// Ниже этого размера полный знак слипается — раздел 4.
const SIMPLIFIED_BELOW = 32

/**
 * Горизонтальный лок-ап: знак слева, вордмарк справа.
 * Кегль и просвет считаются от высоты знака, поэтому пропорции держатся
 * на любом размере и совпадают с файлом docs/design/logo/logo-lockup-h.svg.
 */
export function Lockup({ size = 40 }: { size?: number }) {
  const fontSize = size * FONT_RATIO
  return (
    <div
      className="flex items-center text-text"
      style={{ fontSize, gap: fontSize * X_HEIGHT_RATIO }}
    >
      <LogoMark
        variant={size < SIMPLIFIED_BELOW ? 'small' : 'full'}
        style={{ height: size, width: 'auto' }}
        aria-hidden="true"
      />
      <Wordmark />
    </div>
  )
}
```

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Запустить: `pnpm --filter @repibot/web test` из `frontend`
Ожидается: PASS

- [ ] **Шаг 5: Написать манифест**

Создать `frontend/apps/web/public/manifest.webmanifest`:

```json
{
  "name": "Re:Pibot",
  "short_name": "Re:Pibot",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#FAF9F7",
  "theme_color": "#17A67C",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

- [ ] **Шаг 6: Прописать иконки в метаданных**

Заменить блок `metadata` в `frontend/apps/web/src/app/layout.tsx`:

```tsx
export const metadata: Metadata = {
  title: 'Re:Pibot',
  description: 'Магазин VPN-подписок',
  manifest: '/manifest.webmanifest',
  // SVG первым: браузеры, которые его понимают, растр даже не запросят.
  icons: {
    icon: [
      { url: '/favicon.svg', type: 'image/svg+xml' },
      { url: '/favicon-32.png', sizes: '32x32', type: 'image/png' },
      { url: '/favicon-16.png', sizes: '16x16', type: 'image/png' },
    ],
    apple: '/icon-192.png',
  },
}
```

- [ ] **Шаг 7: Прописать фавикон в MiniApp**

В `frontend/apps/miniapp/index.html` добавить после строки с `<title>`:

```html
    <!-- Внутри Telegram иконка вкладки не видна, но MiniApp открывается
         и в обычном браузере. Путь абсолютный: приложение живёт под /app/. -->
    <link rel="icon" href="/app/favicon.svg" type="image/svg+xml" />
```

- [ ] **Шаг 8: Удалить растровые логотипы**

```bash
git rm frontend/apps/web/public/favicon.png
git rm -r frontend/apps/web/public/brand frontend/apps/miniapp/public/brand
git rm docs/design/logo-light.png docs/design/logo-dark.png
git rm docs/design/lock-up-light.png docs/design/lock-up-dark.png
```

- [ ] **Шаг 9: Запереть отсутствие растров тестом**

Добавить в конец `tools/tests/test_brand.py`:

```python
def test_no_raster_logos_remain_in_the_applications() -> None:
    """Растровый логотип вернётся первым же копипастом, если его не запретить."""
    for application in ("web", "miniapp"):
        public = ROOT / "frontend/apps" / application / "public"
        assert not (public / "brand").exists()
        assert not (public / "favicon.png").exists()


def test_manifest_points_at_existing_icons() -> None:
    manifest = json.loads(
        (ROOT / "frontend/apps/web/public/manifest.webmanifest").read_text(encoding="utf-8")
    )

    assert manifest["theme_color"] == JADE
    for icon in manifest["icons"]:
        assert (ROOT / "frontend/apps/web/public" / icon["src"].lstrip("/")).is_file()
```

В начало файла добавить `import json`.

- [ ] **Шаг 10: Прогнать полную проверку**

Запустить: `uv run check`
Ожидается: «Все проверки пройдены.»

- [ ] **Шаг 11: Посмотреть страницу в браузере**

```bash
pnpm --filter @repibot/web dev
```

Открыть `http://localhost:3000`, проверить лок-ап в обеих темах (переключатель на странице), убедиться, что во вкладке появился зелёный фавикон.

- [ ] **Шаг 12: Коммит**

```bash
git add -A
git commit -m "feat: векторный знак в вебе и MiniApp вместо растров"
```

---

## Задача 8: Бренд-бук и документация

**Файлы:**
- Изменить: `docs/design/repibot-brandbook.md` (строки 3, 158, 178, 65, 267-278)
- Изменить: `README.md`
- Тест: `tools/tests/test_docs.py`

**Интерфейсы:**
- Потребляет: готовый бренд-набор из задач 4 и 5.

- [ ] **Шаг 1: Написать падающий тест**

Добавить в конец `tools/tests/test_docs.py`:

```python
def test_brandbook_describes_the_actual_spiral() -> None:
    """Дуг три, то есть полтора витка. «Два витка» — описание, отставшее от чертежа."""
    brandbook = (ROOT / "docs" / "design" / "repibot-brandbook.md").read_text(encoding="utf-8")

    assert "полутора витков" in brandbook
    assert "двух витков" not in brandbook


def test_brandbook_allows_the_knockout_on_jade() -> None:
    """Запрет зелёного фона относится к основной версии, а не к выворотке."""
    brandbook = (ROOT / "docs" / "design" / "repibot-brandbook.md").read_text(encoding="utf-8")

    assert "основную версию знака на зелёном фоне" in brandbook


def test_readme_points_at_the_brand_kit() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "docs/design/logo" in readme
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запустить: `uv run pytest tools/tests/test_docs.py -q`
Ожидается: FAIL на всех трёх новых тестах

- [ ] **Шаг 3: Поправить бренд-бук**

Строка 3, заменить:

```
Версия 1.0. Основан на утверждённом знаке: разомкнутая спираль из двух витков с отделённым ядром.
```

на:

```
Версия 1.1. Основан на утверждённом знаке: разомкнутая спираль из полутора витков — трёх полукруглых дуг — с отделённым ядром.
```

Правило 5 в разделе «Правила цвета», заменить:

```
5. **Никогда не размещать знак на зелёном фоне.** Ядро исчезнет.
```

на:

```
5. **Не размещать основную версию знака на зелёном фоне.** Ядро в Jade на нём исчезнет. Для заливки Jade существует выворотка из раздела 4: спираль в Jade Mist, ядро белое.
```

В таблице анатомии раздела 4 заменить `≈ `0.75x`` на `≈ `0.8x``.

В абзаце про минимальные размеры заменить «один виток вместо двух» на «один виток вместо полутора».

Раздел 8 заменить целиком:

```markdown
## 8. Файлы

Собраны и лежат в `docs/design/logo`. Правятся не руками, а генератором — см. `CONTRIBUTING.md`.

| Файл | Назначение |
|---|---|
| `logo-mark.svg` | знак, полная версия |
| `logo-mark-mono.svg` | одноцветная, `currentColor` |
| `logo-mark-small.svg` | упрощённая для 16–32 px |
| `logo-lockup-h.svg`, `logo-lockup-v.svg` | лок-апы |
| `wordmark.svg` | только надпись, в кривых |
| `badge.svg`, `badge-inverse.svg` | плашки для аватарок и иконок |
| `favicon.svg` | упрощённый знак на плашке |
| `avatar.svg`, `og-image.svg` | исходники растров |

Растры в `docs/design/logo/raster`: `favicon-16.png`, `favicon-32.png`, `icon-192.png`, `icon-512.png`, `avatar-512.png`, `og-image.png` (1200×630).

В интерфейсе знак берётся не файлом, а компонентом `LogoMark` из `@repibot/ui`: он красится текущим цветом и переключается вместе с темой.
```

- [ ] **Шаг 4: Дописать README**

Добавить в `README.md` в раздел о структуре проекта строку:

```markdown
- `docs/design/logo` — бренд-набор: знак, лок-апы, иконки. Собирается `uv run build-brand`.
```

- [ ] **Шаг 5: Запустить тест и убедиться, что он проходит**

Запустить: `uv run pytest tools/tests/test_docs.py -q`
Ожидается: PASS

- [ ] **Шаг 6: Прогнать полную проверку**

Запустить: `uv run check`
Ожидается: «Все проверки пройдены.»

- [ ] **Шаг 7: Коммит**

```bash
git add docs/design/repibot-brandbook.md README.md tools/tests/test_docs.py
git commit -m "docs: бренд-бук 1.1 — полтора витка, выворотка на Jade, собранные файлы"
```

---

## Границы работы

Сознательно не входит:

- **Мета-теги открытого графа.** `og-image.png` собирается как файл раздела 8, но в `layout.tsx` не подключается: для абсолютного адреса картинки нужен публичный адрес сайта, которого у контейнера `web` намеренно нет. Подключается в подпроекте 1 вместе со страницами, которыми есть смысл делиться.
- **Прелоадер и анимация появления** из раздела 6 — у них пока нет ни одного потребителя.
- **Печатные носители и CMYK.**
