"""Отрисовка Markdown и очистка результата.

Документ набирает человек, а показывается он всем: проверяются не только
обычные абзацы, но и то, что через текст нельзя пронести скрипт.
"""

from __future__ import annotations

from repibot_core.content.markdown import render_markdown


def test_headings_and_lists_are_rendered() -> None:
    html = render_markdown("## Общие положения\n\n- первый\n- второй\n")

    assert "<h2>Общие положения</h2>" in html
    assert "<li>первый</li>" in html


def test_raw_script_does_not_survive() -> None:
    """Сырой HTML внутри Markdown не разбирается, а то, что дошло, вычищается."""
    html = render_markdown("<script>alert(1)</script>\n\nобычный текст")

    assert "<script>" not in html
    assert "alert(1)" not in html or "&lt;script&gt;" in html


def test_javascript_scheme_never_becomes_a_link() -> None:
    """Схема javascript: не доходит до href ни одним путём.

    markdown-it отказывается строить такую ссылку сам, поэтому в выводе
    остаётся простой текст. Сам по себе он безвреден — кликать не по чему;
    опасно ровно попадание схемы в атрибут, и проверяется именно оно.
    """
    html = render_markdown("[нажми](javascript:alert(1))")

    assert "<a" not in html
    assert "href=" not in html


def test_external_link_gets_rel() -> None:
    html = render_markdown("[почта](mailto:help@example.com)")

    assert 'rel="nofollow noopener"' in html or "nofollow" in html


def test_first_level_heading_is_not_allowed() -> None:
    """Заголовок страницы берётся из title: второй h1 ломал бы структуру."""
    html = render_markdown("# Заголовок\n")

    assert "<h1>" not in html
