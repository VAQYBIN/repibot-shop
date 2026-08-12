"""Markdown → безопасный HTML.

Очистка выполняется при отдаче, а не при сохранении. Список разрешённых
тегов со временем меняется, и документ, сохранённый по прошлогодним
правилам, не должен оставаться с дырой внутри.
"""

from __future__ import annotations

import nh3
from markdown_it import MarkdownIt

# h1 в набор не входит намеренно: заголовок страницы берётся из поля title,
# а второй заголовок первого уровня ломает структуру документа для
# скринридера и поисковика разом.
ALLOWED_TAGS = {
    "p",
    "h2",
    "h3",
    "h4",
    "ul",
    "ol",
    "li",
    "strong",
    "em",
    "a",
    "blockquote",
    "code",
    "pre",
    "hr",
    "br",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
}

ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}

ALLOWED_SCHEMES = {"http", "https", "mailto"}

# html=False: сырой HTML внутри Markdown не разбирается, а экранируется.
# Очистка после этого — второй рубеж, а не единственный.
_renderer = MarkdownIt("commonmark", {"html": False, "linkify": False})


def render_markdown(source: str) -> str:
    """HTML документа, пригодный для вставки на страницу как есть."""
    return nh3.clean(
        _renderer.render(source),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_SCHEMES,
        link_rel="nofollow noopener",
    )
