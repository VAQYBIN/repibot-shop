"""Перевод узлового дерева Telegra.ph в Markdown."""

from __future__ import annotations

from repibot_core.integrations.telegraph.nodes import nodes_to_markdown


def test_paragraphs_are_separated_by_a_blank_line() -> None:
    markdown = nodes_to_markdown(
        [
            {"tag": "p", "children": ["первый"]},
            {"tag": "p", "children": ["второй"]},
        ]
    )

    assert markdown == "первый\n\nвторой\n"


def test_headings_map_to_second_and_third_level() -> None:
    """h1 в Telegra.ph нет: их заголовки начинаются с h3."""
    markdown = nodes_to_markdown(
        [
            {"tag": "h3", "children": ["Общие положения"]},
            {"tag": "h4", "children": ["Подраздел"]},
        ]
    )

    assert markdown == "## Общие положения\n\n### Подраздел\n"


def test_inline_marks_are_preserved() -> None:
    markdown = nodes_to_markdown(
        [
            {
                "tag": "p",
                "children": [
                    "обычный ",
                    {"tag": "strong", "children": ["жирный"]},
                    " и ",
                    {"tag": "em", "children": ["наклонный"]},
                ],
            }
        ]
    )

    assert markdown == "обычный **жирный** и *наклонный*\n"


def test_links_keep_their_address() -> None:
    markdown = nodes_to_markdown(
        [
            {
                "tag": "p",
                "children": [
                    {
                        "tag": "a",
                        "attrs": {"href": "mailto:help@example.com"},
                        "children": ["почта"],
                    }
                ],
            }
        ]
    )

    assert markdown == "[почта](mailto:help@example.com)\n"


def test_lists_are_numbered_and_bulleted() -> None:
    markdown = nodes_to_markdown(
        [
            {"tag": "ul", "children": [{"tag": "li", "children": ["раз"]}]},
            {"tag": "ol", "children": [{"tag": "li", "children": ["два"]}]},
        ]
    )

    assert markdown == "- раз\n\n1. два\n"


def test_images_and_video_are_dropped_with_their_content() -> None:
    """Юридический документ с картинкой нам не нужен, а чужие файлы тянуть некуда."""
    markdown = nodes_to_markdown(
        [
            {"tag": "figure", "children": [{"tag": "img", "attrs": {"src": "/file/x.jpg"}}]},
            {"tag": "p", "children": ["текст"]},
        ]
    )

    assert markdown == "текст\n"


def test_blockquote_and_rule() -> None:
    markdown = nodes_to_markdown(
        [
            {"tag": "blockquote", "children": ["цитата"]},
            {"tag": "hr"},
        ]
    )

    assert markdown == "> цитата\n\n---\n"


def test_unknown_tag_keeps_its_text() -> None:
    """Неизвестная обёртка не должна съедать содержимое вместе с собой."""
    markdown = nodes_to_markdown([{"tag": "span", "children": ["важное"]}])

    assert markdown == "важное\n"
