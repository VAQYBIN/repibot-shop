# Импорт документа с Telegra.ph

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** админ вставляет ссылку на Telegra.ph, получает заголовок и текст в Markdown и правит их у себя.

**Architecture:** ссылка — способ ввода, а не источник. Текст забирается один раз через открытый API Telegra.ph, переводится из их узлового дерева в Markdown и возвращается вызывающему. Ничего не сохраняется: сохранение — отдельное действие админа. В рантайме на Telegra.ph мы не ходим никогда.

**Tech Stack:** httpx, FastAPI, pytest.

## Global Constraints

- **Не выполняйте git-команд.** Коммит делает ведущий после проверки задачи.
- **Не запускайте `uv run check` целиком.** Только команды из шагов.
- **Не редактируйте `pyproject.toml`, `package.json`, `uv.lock`, `pnpm-lock.yaml`.**
- Комментарии и строки документации на русском, объясняют «почему», а не «что».
- `# noqa` без сработавшего правила запрещён.
- Строгий mypy.
- Файлы тестов именуются уникально на весь репозиторий.
- Сначала тест, потом код.
- **Сеть в тестах не используется.** Ответ Telegra.ph подставляется заглушкой транспорта httpx.

---

### Task 1: Узловое дерево Telegra.ph в Markdown

**Files:**
- Create: `backend/core/src/repibot_core/integrations/telegraph/__init__.py`
- Create: `backend/core/src/repibot_core/integrations/telegraph/nodes.py`
- Test: `backend/core/tests/test_telegraph_nodes.py`

**Interfaces:**
- Produces: `nodes_to_markdown(nodes: list[object]) -> str`.

Формат Telegra.ph: узел — либо строка, либо объект `{"tag": "p", "attrs": {...}, "children": [...]}`. `attrs` и `children` необязательны.

- [ ] **Step 1: Написать падающий тест**

`backend/core/tests/test_telegraph_nodes.py`:

```python
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
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_telegraph_nodes.py -q`
Expected: FAIL — `ModuleNotFoundError: repibot_core.integrations.telegraph`.

- [ ] **Step 3: Написать конвертер**

`backend/core/src/repibot_core/integrations/telegraph/__init__.py`:

```python
"""Telegra.ph: разовый импорт текста, не источник в рантайме."""
```

`backend/core/src/repibot_core/integrations/telegraph/nodes.py`:

```python
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
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_telegraph_nodes.py -q`
Expected: PASS, 8 тестов.

- [ ] **Step 5: Проверить линтеры и типы**

Run: `uv run ruff check backend/core && uv run ruff format --check backend/core && uv run mypy backend/core`
Expected: без замечаний.

---

### Task 2: Загрузка страницы Telegra.ph

**Files:**
- Create: `backend/core/src/repibot_core/integrations/telegraph/client.py`
- Test: `backend/core/tests/test_telegraph_client.py`

**Interfaces:**
- Consumes: `nodes_to_markdown` (Task 1).
- Produces:
  - `TelegraphPage(title: str, content: str)` — `dataclass(frozen=True, slots=True)`;
  - `TelegraphError(Exception)` с полем `code: str` (`invalid_source`, `not_found`, `import_failed`);
  - `TelegraphClient(client: httpx.AsyncClient | None = None)` с методом `async def fetch(self, url: str) -> TelegraphPage`.

- [ ] **Step 1: Написать падающий тест**

`backend/core/tests/test_telegraph_client.py`:

```python
"""Загрузка страницы Telegra.ph.

Сеть не используется: транспорт httpx подменяется заглушкой, поэтому тест
проверяет наше поведение, а не доступность чужого сервиса.
"""

from __future__ import annotations

import httpx
import pytest

from repibot_core.integrations.telegraph.client import (
    TelegraphClient,
    TelegraphError,
)

PAGE_RESPONSE = {
    "ok": True,
    "result": {
        "title": "Пользовательское соглашение",
        "content": [
            {"tag": "h3", "children": ["Общие положения"]},
            {"tag": "p", "children": ["Текст соглашения."]},
        ],
    },
}


def _client(handler: object) -> TelegraphClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return TelegraphClient(httpx.AsyncClient(transport=transport))


async def test_page_is_fetched_and_converted() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json=PAGE_RESPONSE)

    page = await _client(handler).fetch("https://telegra.ph/Polzovatelskoe-soglashenie-06-01-28")

    assert page.title == "Пользовательское соглашение"
    assert page.content == "## Общие положения\n\nТекст соглашения.\n"
    assert "api.telegra.ph/getPage" in requested[0]
    assert "Polzovatelskoe-soglashenie-06-01-28" in requested[0]
    assert "return_content=true" in requested[0]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/terms",
        "https://telegra.ph.evil.com/page",
        "http://127.0.0.1:8000/api/admin/plans",
        "не адрес вовсе",
    ],
)
async def test_foreign_addresses_are_rejected(url: str) -> None:
    """Эндпоинт, ходящий по произвольному адресу, простукивает внутреннюю сеть снаружи."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover — не вызывается
        raise AssertionError("запрос не должен уходить")

    with pytest.raises(TelegraphError) as error:
        await _client(handler).fetch(url)

    assert error.value.code == "invalid_source"


async def test_missing_page_is_reported_as_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "error": "PAGE_NOT_FOUND"})

    with pytest.raises(TelegraphError) as error:
        await _client(handler).fetch("https://telegra.ph/Nothing-01-01")

    assert error.value.code == "not_found"


async def test_unavailable_service_is_reported_separately() -> None:
    """Их недоступность — не наша ошибка ввода: админ должен видеть разницу."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("нет связи")

    with pytest.raises(TelegraphError) as error:
        await _client(handler).fetch("https://telegra.ph/Something-01-01")

    assert error.value.code == "import_failed"
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_telegraph_client.py -q`
Expected: FAIL — модуля `client` нет.

- [ ] **Step 3: Написать клиент**

`backend/core/src/repibot_core/integrations/telegraph/client.py`:

```python
"""Разовая загрузка страницы Telegra.ph.

Адрес принимается только с их домена. Это не придирчивость: эндпоинт,
который по просьбе пользователя ходит на произвольный URL, позволяет
простукивать внутреннюю сеть снаружи — включая наши же служебные адреса.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from repibot_core.integrations.telegraph.nodes import nodes_to_markdown

API_URL = "https://api.telegra.ph/getPage"
ALLOWED_HOSTS = frozenset({"telegra.ph", "api.telegra.ph"})
TIMEOUT_SECONDS = 5.0


class TelegraphError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class TelegraphPage:
    title: str
    content: str


class TelegraphClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)

    async def fetch(self, url: str) -> TelegraphPage:
        path = _path_of(url)

        try:
            response = await self._client.get(
                API_URL, params={"path": path, "return_content": "true"}
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            msg = "Telegra.ph не ответил"
            raise TelegraphError("import_failed", msg) from error

        if not payload.get("ok"):
            msg = "страница не найдена"
            raise TelegraphError("not_found", msg)

        result = payload.get("result", {})
        content = result.get("content")
        return TelegraphPage(
            title=str(result.get("title", "")),
            content=nodes_to_markdown(content if isinstance(content, list) else []),
        )


def _path_of(url: str) -> str:
    """Путь страницы в адресе Telegra.ph.

    Хост сравнивается целиком, а не поиском подстроки: `telegra.ph.evil.com`
    содержит нужные символы и не имеет к сервису никакого отношения.
    """
    try:
        parsed = urlparse(url)
    except ValueError as error:
        msg = "это не адрес"
        raise TelegraphError("invalid_source", msg) from error

    if parsed.scheme not in {"http", "https"} or parsed.hostname not in ALLOWED_HOSTS:
        msg = "принимаются только ссылки на telegra.ph"
        raise TelegraphError("invalid_source", msg)

    path = parsed.path.strip("/")
    if not path:
        msg = "в ссылке нет страницы"
        raise TelegraphError("invalid_source", msg)
    return path
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_telegraph_client.py -q`
Expected: PASS, 7 тестов (четыре из них — параметризованные адреса).

- [ ] **Step 5: Проверить линтеры и типы**

Run: `uv run ruff check backend/core && uv run ruff format --check backend/core && uv run mypy backend/core`
Expected: без замечаний.

---

## Готовность плана

После двух задач текст с Telegra.ph превращается в Markdown, а чужие адреса отвергаются до того, как уйдёт запрос. Эндпоинт `POST /api/admin/legal/import`, который этим пользуется, живёт в плане админского API.
