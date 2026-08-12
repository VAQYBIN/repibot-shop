"""Узловое дерево Telegra.ph → Markdown.

Telegra.ph отдаёт содержимое страницы деревом объектов, а не HTML. Перевод
делается здесь, чтобы админ получил в редакторе обычный Markdown и мог
править его руками — ради этого импорт и затевался.
"""

from __future__ import annotations

# Блочные теги: каждый даёт абзац, между абзацами — пустая строка.
BLOCK_PREFIXES = {
    "h3": "## ",
    "h4": "### ",
    "blockquote": "> ",
}

# Оставляются без содержимого: тянуть чужие файлы к себе некуда, а документ
# без картинки остаётся документом.
DROPPED = frozenset({"img", "video", "iframe", "figure", "figcaption"})

INLINE_WRAPPERS = {
    "b": "**",
    "strong": "**",
    "i": "*",
    "em": "*",
    "code": "`",
}


def nodes_to_markdown(nodes: list[object]) -> str:
    """Markdown страницы. Пустое дерево даёт пустую строку."""
    blocks: list[str] = []
    for node in nodes:
        blocks.extend(_block(node))
    return "" if not blocks else "\n\n".join(blocks) + "\n"


def _block(node: object) -> list[str]:
    if isinstance(node, str):
        text = node.strip()
        return [text] if text else []
    if not isinstance(node, dict):
        return []

    tag = str(node.get("tag", ""))
    if tag in DROPPED:
        return []

    children = _children(node)

    if tag == "hr":
        return ["---"]
    if tag in {"ul", "ol"}:
        return [_list(children, ordered=tag == "ol")]
    if tag == "pre":
        return ["```\n" + _inline(children) + "\n```"]

    text = _inline(children)
    if not text:
        return []
    return [BLOCK_PREFIXES.get(tag, "") + text]


def _list(items: list[object], *, ordered: bool) -> str:
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        text = _inline(_children(item)) if isinstance(item, dict) else str(item).strip()
        if not text:
            continue
        lines.append(f"{index}. {text}" if ordered else f"- {text}")
    return "\n".join(lines)


def _inline(nodes: list[object]) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, str):
            parts.append(node)
            continue
        if not isinstance(node, dict):
            continue

        tag = str(node.get("tag", ""))
        if tag in DROPPED:
            continue

        inner = _inline(_children(node))
        if tag == "br":
            parts.append("\n")
        elif tag == "a":
            href = str(_attrs(node).get("href", ""))
            parts.append(f"[{inner}]({href})" if href else inner)
        elif tag in INLINE_WRAPPERS and inner:
            mark = INLINE_WRAPPERS[tag]
            parts.append(f"{mark}{inner}{mark}")
        else:
            # Неизвестная обёртка отдаёт своё содержимое: потерять текст хуже,
            # чем потерять начертание.
            parts.append(inner)
    return "".join(parts).strip()


def _children(node: object) -> list[object]:
    if not isinstance(node, dict):
        return []
    children = node.get("children")
    return list(children) if isinstance(children, list) else []


def _attrs(node: dict[str, object]) -> dict[str, object]:
    attrs = node.get("attrs")
    return dict(attrs) if isinstance(attrs, dict) else {}
