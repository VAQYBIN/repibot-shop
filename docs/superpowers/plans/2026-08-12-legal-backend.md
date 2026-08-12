# Юридические документы: хранение и публичное чтение

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** таблица `legal_documents` с версиями, отрисовка Markdown в безопасный HTML и публичное чтение опубликованных документов.

**Architecture:** строка версии неизменяема по содержимому: правка создаёт новую, публикация проставляет дату, снятие — отметку `withdrawn_at`. Markdown хранится как есть, HTML собирается при отдаче и чистится `nh3`. Публичный API отдаёт документ одной локалью с запасным вариантом.

**Tech Stack:** SQLAlchemy 2.0, Alembic, FastAPI, `markdown-it-py`, `nh3`, pytest + testcontainers.

## Global Constraints

- **Не выполняйте git-команд.** Коммит делает ведущий после проверки задачи.
- **Не запускайте `uv run check` целиком** — он не укладывается в лимит времени. Только команды, указанные в шагах.
- **Не редактируйте `pyproject.toml`, `package.json`, `uv.lock`, `pnpm-lock.yaml`.** Зависимости `markdown-it-py` и `nh3` уже установлены ведущим. Если чего-то не хватает — остановитесь и сообщите.
- Комментарии и строки документации на русском, объясняют «почему», а не «что».
- `# noqa` без сработавшего правила запрещён: `RUF100` ловит лишние подавления и роняет проверку.
- Строгий mypy: аннотации обязательны, `Any` только там, где иначе нельзя.
- Файлы тестов именуются уникально на весь репозиторий: два `test_legal.py` в разных пакетах роняют сборку pytest.
- Сначала тест, потом код. Тест обязан упасть до реализации — это проверяется отдельным шагом.

---

### Task 1: Модель и миграция

**Files:**
- Create: `backend/core/src/repibot_core/db/models/legal.py`
- Modify: `backend/core/src/repibot_core/db/models/__init__.py`
- Create: `backend/core/src/repibot_core/db/migrations/versions/0020_legal_documents.py`
- Test: `backend/core/tests/test_legal_model.py`

**Interfaces:**
- Produces: `LegalDocument` с полями `id`, `slug`, `locale`, `title`, `content`, `version`, `published_at`, `withdrawn_at`, `created_by_id`, `created_at`, `updated_at`.

- [ ] **Step 1: Написать падающий тест**

`backend/core/tests/test_legal_model.py`:

```python
"""Ограничения таблицы юридических документов."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import LegalDocument

pytestmark = pytest.mark.docker


async def test_second_draft_for_the_same_pair_is_rejected(db_session: AsyncSession) -> None:
    """Черновик у пары slug+locale ровно один: иначе непонятно, какой открывать."""
    db_session.add(
        LegalDocument(slug="terms", locale="ru", title="Условия", content="текст", version=1)
    )
    await db_session.flush()

    db_session.add(
        LegalDocument(slug="terms", locale="ru", title="Условия", content="другой", version=2)
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_published_versions_may_coexist(db_session: AsyncSession) -> None:
    """История версий — смысл таблицы: опубликованные строки не конфликтуют."""
    now = __import__("datetime").datetime.now(__import__("datetime").UTC)
    for version in (1, 2):
        db_session.add(
            LegalDocument(
                slug="terms",
                locale="ru",
                title="Условия",
                content=f"версия {version}",
                version=version,
                published_at=now,
            )
        )
    await db_session.flush()
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_legal_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'LegalDocument'`.

- [ ] **Step 3: Написать модель**

`backend/core/src/repibot_core/db/models/legal.py`:

```python
"""Юридические документы: соглашение, политика, оферта — что заведёт админ.

Набор имён не фиксирован: проект открытый, у каждого разворачивающего свой
перечень и своё юрлицо. Поэтому slug — обычное поле, а не перечисление.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class LegalDocument(TimestampMixin, Base):
    __tablename__ = "legal_documents"
    __table_args__ = (
        UniqueConstraint("slug", "locale", "version", name="uq_legal_documents_version"),
        # Черновик у пары ровно один. NULL в обычном уникальном индексе
        # Postgres не конфликтует сам с собой, поэтому условие вынесено в
        # частичный индекс — без него вторая правка молча завела бы второй
        # черновик, и «открыть черновик» перестало бы иметь единственный ответ.
        Index(
            "uq_legal_documents_single_draft",
            "slug",
            "locale",
            unique=True,
            postgresql_where=text("published_at IS NULL"),
        ),
        Index("ix_legal_documents_lookup", "slug", "locale", "version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64))
    locale: Mapped[str] = mapped_column(String(2))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Снятие с публикации не стирает текст: удалить условия, на которых
    # кто-то уже купил, — ровно то, ради чего версии и заводились.
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
```

- [ ] **Step 4: Подключить модель к пакету**

В `backend/core/src/repibot_core/db/models/__init__.py` добавить импорт и запись в `__all__` рядом с остальными — порядок алфавитный, как в файле.

```python
from repibot_core.db.models.legal import LegalDocument
```

- [ ] **Step 5: Написать миграцию**

`backend/core/src/repibot_core/db/migrations/versions/0020_legal_documents.py`:

```python
"""Юридические документы с историей версий.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=2), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("slug", "locale", "version", name="uq_legal_documents_version"),
    )
    op.create_index(
        "uq_legal_documents_single_draft",
        "legal_documents",
        ["slug", "locale"],
        unique=True,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index(
        "ix_legal_documents_lookup", "legal_documents", ["slug", "locale", "version"]
    )


def downgrade() -> None:
    op.drop_table("legal_documents")
```

Сверьте `created_at`/`updated_at` с тем, как их объявляет `TimestampMixin` в `backend/core/src/repibot_core/db/base.py`, и повторите ровно эти типы и умолчания: расхождение поймает сравнение схемы с моделями.

- [ ] **Step 6: Убедиться, что тест проходит**

Run: `uv run pytest backend/core/tests/test_legal_model.py -q`
Expected: PASS, 2 теста.

- [ ] **Step 7: Проверить линтеры и типы**

Run: `uv run ruff check backend/core && uv run ruff format --check backend/core && uv run mypy backend/core`
Expected: без замечаний.

---

### Task 2: Markdown в безопасный HTML

**Files:**
- Create: `backend/core/src/repibot_core/content/__init__.py`
- Create: `backend/core/src/repibot_core/content/markdown.py`
- Test: `backend/core/tests/test_legal_markdown.py`

**Interfaces:**
- Produces: `render_markdown(source: str) -> str` — HTML, пригодный для вставки на страницу.

- [ ] **Step 1: Написать падающий тест**

`backend/core/tests/test_legal_markdown.py`:

```python
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


def test_javascript_scheme_is_stripped() -> None:
    html = render_markdown("[нажми](javascript:alert(1))")

    assert "javascript:" not in html


def test_external_link_gets_rel() -> None:
    html = render_markdown("[почта](mailto:help@example.com)")

    assert 'rel="nofollow noopener"' in html or "nofollow" in html


def test_first_level_heading_is_not_allowed() -> None:
    """Заголовок страницы берётся из title: второй h1 ломал бы структуру."""
    html = render_markdown("# Заголовок\n")

    assert "<h1>" not in html
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_legal_markdown.py -q`
Expected: FAIL — `ModuleNotFoundError: repibot_core.content`.

- [ ] **Step 3: Написать модуль**

`backend/core/src/repibot_core/content/__init__.py`:

```python
"""Работа с текстом, который вводит человек и читают все."""
```

`backend/core/src/repibot_core/content/markdown.py`:

```python
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
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_legal_markdown.py -q`
Expected: PASS, 5 тестов.

Если `nh3.clean` не принимает какой-то из именованных аргументов, посмотрите сигнатуру `python -c "import nh3; help(nh3.clean)"` и приведите вызов к ней, сохранив смысл: набор тегов, набор атрибутов, набор схем и дописывание `rel`.

- [ ] **Step 5: Проверить линтеры и типы**

Run: `uv run ruff check backend/core && uv run ruff format --check backend/core && uv run mypy backend/core`
Expected: без замечаний.

---

### Task 3: Репозиторий и сервис версий

**Files:**
- Create: `backend/core/src/repibot_core/db/repositories/legal.py`
- Create: `backend/core/src/repibot_core/services/legal.py`
- Test: `backend/core/tests/test_legal_service.py`

**Interfaces:**
- Consumes: `LegalDocument` (Task 1), `render_markdown` (Task 2).
- Produces:
  - `LegalDocumentView(slug, locale, title, content, version, published_at, withdrawn_at)` — `dataclass(frozen=True, slots=True)`;
  - `LegalVersionView(version, published_at, withdrawn_at, created_at, created_by_id)`;
  - `LegalService(session)` с методами:
    - `published_list(locale: str) -> list[LegalDocumentView]`
    - `published(slug: str, locale: str) -> LegalDocumentView | None` — с запасной локалью
    - `current(slug: str, locale: str) -> LegalDocumentView | None` — черновик, иначе последняя версия
    - `save_draft(slug: str, locale: str, title: str, content: str, author_id: int) -> LegalDocumentView`
    - `publish(slug: str, locale: str) -> LegalDocumentView`
    - `withdraw(slug: str, locale: str) -> None`
    - `versions(slug: str, locale: str) -> list[LegalVersionView]`
    - `version(slug: str, locale: str, version: int) -> LegalDocumentView | None`
    - `known_slugs() -> list[tuple[str, str]]` — пары slug и locale, включая черновики
  - `SLUG_PATTERN` — скомпилированное `^[a-z0-9-]{2,64}$`.

- [ ] **Step 1: Написать падающий тест**

`backend/core/tests/test_legal_service.py`:

```python
"""Версии документа: правка, публикация, снятие, запасная локаль."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.services.errors import ServiceError
from repibot_core.services.legal import LegalService

pytestmark = pytest.mark.docker


async def test_editing_a_published_document_creates_a_new_version(
    db_session: AsyncSession,
) -> None:
    service = LegalService(db_session)
    await service.save_draft(
        slug="terms", locale="ru", title="Условия", content="первый", author_id=None
    )
    await service.publish(slug="terms", locale="ru")

    await service.save_draft(
        slug="terms", locale="ru", title="Условия", content="второй", author_id=None
    )
    published = await service.publish(slug="terms", locale="ru")

    assert published.version == 2
    assert [item.version for item in await service.versions("terms", "ru")] == [2, 1]


async def test_draft_is_not_published(db_session: AsyncSession) -> None:
    service = LegalService(db_session)
    await service.save_draft(
        slug="privacy", locale="ru", title="Политика", content="черновик", author_id=None
    )

    assert await service.published("privacy", "ru") is None


async def test_withdrawn_document_disappears_from_the_public_list(
    db_session: AsyncSession,
) -> None:
    service = LegalService(db_session)
    await service.save_draft(
        slug="offer", locale="ru", title="Оферта", content="текст", author_id=None
    )
    await service.publish(slug="offer", locale="ru")

    await service.withdraw(slug="offer", locale="ru")

    assert await service.published("offer", "ru") is None
    assert await service.published_list("ru") == []


async def test_publishing_again_returns_a_withdrawn_document(db_session: AsyncSession) -> None:
    """Отдельной кнопки «вернуть» нет: возврат — обычная новая версия."""
    service = LegalService(db_session)
    await service.save_draft(
        slug="offer", locale="ru", title="Оферта", content="текст", author_id=None
    )
    await service.publish(slug="offer", locale="ru")
    await service.withdraw(slug="offer", locale="ru")

    await service.save_draft(
        slug="offer", locale="ru", title="Оферта", content="текст", author_id=None
    )
    restored = await service.publish(slug="offer", locale="ru")

    assert restored.version == 2
    assert (await service.published("offer", "ru")) is not None


async def test_missing_locale_falls_back(db_session: AsyncSession) -> None:
    """Подвал на английском не должен приводить в пустоту, если заведён только русский."""
    service = LegalService(db_session)
    await service.save_draft(
        slug="terms", locale="ru", title="Условия", content="текст", author_id=None
    )
    await service.publish(slug="terms", locale="ru")

    document = await service.published("terms", "en")

    assert document is not None
    assert document.locale == "ru"


async def test_invalid_slug_is_rejected(db_session: AsyncSession) -> None:
    """Косая черта в slug превратила бы имя документа в часть пути."""
    service = LegalService(db_session)

    with pytest.raises(ServiceError):
        await service.save_draft(
            slug="terms/../etc", locale="ru", title="Условия", content="текст", author_id=None
        )


async def test_publishing_without_a_draft_fails(db_session: AsyncSession) -> None:
    service = LegalService(db_session)

    with pytest.raises(ServiceError):
        await service.publish(slug="terms", locale="ru")
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_legal_service.py -q`
Expected: FAIL — `ModuleNotFoundError: repibot_core.services.legal`.

- [ ] **Step 3: Написать репозиторий**

`backend/core/src/repibot_core/db/repositories/legal.py`:

```python
"""Доступ к юридическим документам."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import LegalDocument


class LegalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def draft(self, slug: str, locale: str) -> LegalDocument | None:
        statement = select(LegalDocument).where(
            LegalDocument.slug == slug,
            LegalDocument.locale == locale,
            LegalDocument.published_at.is_(None),
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def latest(self, slug: str, locale: str) -> LegalDocument | None:
        """Последняя версия пары, включая черновик."""
        statement = (
            select(LegalDocument)
            .where(LegalDocument.slug == slug, LegalDocument.locale == locale)
            .order_by(LegalDocument.version.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def latest_published(self, slug: str, locale: str) -> LegalDocument | None:
        statement = (
            select(LegalDocument)
            .where(
                LegalDocument.slug == slug,
                LegalDocument.locale == locale,
                LegalDocument.published_at.is_not(None),
            )
            .order_by(LegalDocument.version.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def locales_with_publication(self, slug: str) -> list[str]:
        statement = (
            select(LegalDocument.locale)
            .where(LegalDocument.slug == slug, LegalDocument.published_at.is_not(None))
            .distinct()
        )
        return list((await self._session.execute(statement)).scalars())

    async def all_slugs(self) -> list[tuple[str, str]]:
        statement = select(LegalDocument.slug, LegalDocument.locale).distinct()
        return [(slug, locale) for slug, locale in (await self._session.execute(statement)).all()]

    async def versions(self, slug: str, locale: str) -> list[LegalDocument]:
        statement = (
            select(LegalDocument)
            .where(LegalDocument.slug == slug, LegalDocument.locale == locale)
            .order_by(LegalDocument.version.desc())
        )
        return list((await self._session.execute(statement)).scalars())

    async def version(self, slug: str, locale: str, version: int) -> LegalDocument | None:
        statement = select(LegalDocument).where(
            LegalDocument.slug == slug,
            LegalDocument.locale == locale,
            LegalDocument.version == version,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    def add(self, document: LegalDocument) -> None:
        self._session.add(document)
```

- [ ] **Step 4: Написать сервис**

`backend/core/src/repibot_core/services/legal.py`:

```python
"""Юридические документы: черновик, публикация, история версий.

Опубликованная строка не меняется по содержимому. Правка создаёт новую
версию, и потому на вопрос «какой текст действовал в марте» есть ровно один
ответ — ради него версии в таблице и заведены.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import LegalDocument
from repibot_core.db.repositories.legal import LegalRepository
from repibot_core.services.errors import ServiceError

SLUG_PATTERN = re.compile(r"^[a-z0-9-]{2,64}$")

# Порядок перебора запасных локалей. Русская первая: развёртывание в первую
# очередь русскоязычное, а пустая правовая ссылка хуже ссылки на другом языке.
FALLBACK_ORDER = ("ru", "en")


@dataclass(frozen=True, slots=True)
class LegalDocumentView:
    slug: str
    locale: str
    title: str
    content: str
    version: int
    published_at: datetime | None
    withdrawn_at: datetime | None


@dataclass(frozen=True, slots=True)
class LegalVersionView:
    version: int
    published_at: datetime | None
    withdrawn_at: datetime | None
    created_at: datetime
    created_by_id: int | None


class LegalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._documents = LegalRepository(session)

    async def published_list(self, locale: str) -> list[LegalDocumentView]:
        """По одному документу на slug: нужной локали или запасной."""
        seen = {slug for slug, _ in await self._documents.all_slugs()}
        found = [await self.published(slug, locale) for slug in sorted(seen)]
        return [document for document in found if document is not None]

    async def published(self, slug: str, locale: str) -> LegalDocumentView | None:
        for candidate in (locale, *FALLBACK_ORDER):
            document = await self._documents.latest_published(slug, candidate)
            if document is not None and document.withdrawn_at is None:
                return _view(document)
        return None

    async def current(self, slug: str, locale: str) -> LegalDocumentView | None:
        document = await self._documents.latest(slug, locale)
        return None if document is None else _view(document)

    async def save_draft(
        self, *, slug: str, locale: str, title: str, content: str, author_id: int | None
    ) -> LegalDocumentView:
        _check_slug(slug)
        _check_locale(locale)

        draft = await self._documents.draft(slug, locale)
        if draft is not None:
            draft.title = title
            draft.content = content
            await self._session.flush()
            return _view(draft)

        latest = await self._documents.latest(slug, locale)
        document = LegalDocument(
            slug=slug,
            locale=locale,
            title=title,
            content=content,
            version=1 if latest is None else latest.version + 1,
            created_by_id=author_id,
        )
        self._documents.add(document)
        await self._session.flush()
        return _view(document)

    async def publish(self, *, slug: str, locale: str) -> LegalDocumentView:
        draft = await self._documents.draft(slug, locale)
        if draft is None:
            msg = "публиковать нечего: черновика нет"
            raise ServiceError(msg, "draft_not_found")

        draft.published_at = datetime.now(UTC)
        await self._session.flush()
        return _view(draft)

    async def withdraw(self, *, slug: str, locale: str) -> None:
        """Снимает с публикации, не трогая текст.

        Отметка ставится на последнюю опубликованную версию: публичное чтение
        смотрит именно на неё, а история при этом остаётся целой.
        """
        document = await self._documents.latest_published(slug, locale)
        if document is None:
            msg = "снимать нечего: документ не опубликован"
            raise ServiceError(msg, "not_found")

        document.withdrawn_at = datetime.now(UTC)
        await self._session.flush()

    async def versions(self, slug: str, locale: str) -> list[LegalVersionView]:
        return [
            LegalVersionView(
                version=document.version,
                published_at=document.published_at,
                withdrawn_at=document.withdrawn_at,
                created_at=document.created_at,
                created_by_id=document.created_by_id,
            )
            for document in await self._documents.versions(slug, locale)
        ]

    async def version(self, slug: str, locale: str, version: int) -> LegalDocumentView | None:
        document = await self._documents.version(slug, locale, version)
        return None if document is None else _view(document)

    async def known_slugs(self) -> list[tuple[str, str]]:
        return sorted(await self._documents.all_slugs())


def _check_slug(slug: str) -> None:
    if SLUG_PATTERN.match(slug) is None:
        msg = "имя документа состоит из строчных букв, цифр и дефиса"
        raise ServiceError(msg, "validation_error")


def _check_locale(locale: str) -> None:
    if locale not in FALLBACK_ORDER:
        msg = "поддерживаются только локали ru и en"
        raise ServiceError(msg, "validation_error")


def _view(document: LegalDocument) -> LegalDocumentView:
    return LegalDocumentView(
        slug=document.slug,
        locale=document.locale,
        title=document.title,
        content=document.content,
        version=document.version,
        published_at=document.published_at,
        withdrawn_at=document.withdrawn_at,
    )
```

Сверьте сигнатуру `ServiceError` в `backend/core/src/repibot_core/services/errors.py` и вызывайте её так, как это делают соседние сервисы: если код ошибки передаётся другим способом, повторите их форму.

- [ ] **Step 5: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_legal_service.py -q`
Expected: PASS, 7 тестов.

- [ ] **Step 6: Проверить линтеры и типы**

Run: `uv run ruff check backend/core && uv run ruff format --check backend/core && uv run mypy backend/core`
Expected: без замечаний.

---

### Task 4: Публичное чтение через API

**Files:**
- Create: `backend/api/src/repibot_api/routers/legal.py`
- Modify: `backend/api/src/repibot_api/schemas.py`
- Modify: `backend/api/src/repibot_api/main.py`
- Test: `backend/api/tests/test_legal_public_routes.py`

**Interfaces:**
- Consumes: `LegalService`, `LegalDocumentView` (Task 3), `render_markdown` (Task 2).
- Produces:
  - `GET /api/legal?locale=ru` → `list[LegalListItemResponse]` с полями `slug`, `title`, `published_at`;
  - `GET /api/legal/{slug}?locale=ru` → `LegalDocumentResponse` с полями `slug`, `title`, `html`, `locale`, `version`, `published_at`.

- [ ] **Step 1: Написать падающий тест**

`backend/api/tests/test_legal_public_routes.py`:

```python
"""Публичное чтение юридических документов."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from repibot_core.services.legal import LegalService

pytestmark = pytest.mark.docker


async def _publish(engine: AsyncEngine, slug: str, locale: str, content: str) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        service = LegalService(session)
        await service.save_draft(
            slug=slug, locale=locale, title="Условия", content=content, author_id=None
        )
        await service.publish(slug=slug, locale=locale)
        await session.commit()


async def test_empty_list_when_nothing_is_published(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/legal")

    assert response.status_code == 200
    assert response.json() == []


async def test_published_document_is_readable(api_client: AsyncClient, engine: AsyncEngine) -> None:
    await _publish(engine, "terms", "ru", "## Раздел\n\nтекст")

    listed = await api_client.get("/api/legal")
    assert [item["slug"] for item in listed.json()] == ["terms"]

    document = await api_client.get("/api/legal/terms")
    assert document.status_code == 200
    body = document.json()
    assert body["title"] == "Условия"
    assert "<h2>Раздел</h2>" in body["html"]
    assert body["locale"] == "ru"


async def test_draft_is_invisible(api_client: AsyncClient, engine: AsyncEngine) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await LegalService(session).save_draft(
            slug="privacy", locale="ru", title="Политика", content="черновик", author_id=None
        )
        await session.commit()

    assert (await api_client.get("/api/legal/privacy")).status_code == 404
    assert (await api_client.get("/api/legal")).json() == []


async def test_unknown_document_is_not_found(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/legal/nothing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `uv run pytest backend/api/tests/test_legal_public_routes.py -q`
Expected: FAIL — 404 на `/api/legal`, маршрута ещё нет.

- [ ] **Step 3: Добавить схемы**

В конец `backend/api/src/repibot_api/schemas.py`:

```python
class LegalListItemResponse(BaseModel):
    """Строка для подвала: имя, подпись и дата, когда текст стал действовать."""

    slug: str
    title: str
    published_at: datetime


class LegalDocumentResponse(BaseModel):
    slug: str
    title: str
    html: str
    locale: str
    version: int
    published_at: datetime
```

Если `datetime` в файле ещё не импортирован, добавьте импорт к остальным вверху.

- [ ] **Step 4: Написать роутер**

`backend/api/src/repibot_api/routers/legal.py`:

```python
"""Юридические документы для всех.

Читается без входа: человек имеет право посмотреть условия до того, как
заведёт аккаунт. Черновики сюда не попадают никогда.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import db_session
from repibot_api.errors import ApiError
from repibot_api.schemas import LegalDocumentResponse, LegalListItemResponse
from repibot_core.content.markdown import render_markdown
from repibot_core.services.legal import LegalService

router = APIRouter()

# Локаль приходит параметром, а не заголовком: страница на сервере и запрос из
# браузера должны получать одно и то же, а Accept-Language у них разный.
LocaleQuery = Annotated[str, Query(pattern="^(ru|en)$")]


@router.get("/api/legal", response_model=list[LegalListItemResponse])
async def list_legal_documents(
    session: Annotated[AsyncSession, Depends(db_session)],
    locale: LocaleQuery = "ru",
) -> list[LegalListItemResponse]:
    documents = await LegalService(session).published_list(locale)
    return [
        LegalListItemResponse(
            slug=document.slug,
            title=document.title,
            # published_at у опубликованного документа заполнен по построению:
            # published_list отбирает только такие.
            published_at=document.published_at,
        )
        for document in documents
        if document.published_at is not None
    ]


@router.get("/api/legal/{slug}", response_model=LegalDocumentResponse)
async def read_legal_document(
    slug: str,
    session: Annotated[AsyncSession, Depends(db_session)],
    locale: LocaleQuery = "ru",
) -> LegalDocumentResponse:
    document = await LegalService(session).published(slug, locale)
    if document is None or document.published_at is None:
        raise ApiError("документ не найден", 404, "not_found")

    return LegalDocumentResponse(
        slug=document.slug,
        title=document.title,
        html=render_markdown(document.content),
        locale=document.locale,
        version=document.version,
        published_at=document.published_at,
    )
```

Сверьте сигнатуру `ApiError` с тем, как её вызывают в `backend/api/src/repibot_api/routers/subscription.py`, и повторите порядок аргументов.

- [ ] **Step 5: Подключить роутер**

В `backend/api/src/repibot_api/main.py` импортировать `router as legal_router` и включить его рядом с остальными — после `subscription_router`, до `winback_router`. Порядок объявления определяет порядок путей в схеме OpenAPI, поэтому не переставляйте существующие строки.

- [ ] **Step 6: Убедиться, что тесты проходят**

Run: `uv run pytest backend/api/tests/test_legal_public_routes.py -q`
Expected: PASS, 4 теста.

- [ ] **Step 7: Обновить схему OpenAPI и типы клиента**

Run: `uv run export-openapi && cd frontend && pnpm --filter @repibot/core gen:api`
Expected: изменились `frontend/packages/core/src/api/openapi.json` и `frontend/packages/core/src/api/schema.d.ts`.

Затем: `uv run verify-generated`
Expected: без замечаний.

- [ ] **Step 8: Проверить линтеры и типы**

Run: `uv run ruff check backend && uv run ruff format --check backend && uv run mypy backend`
Expected: без замечаний.

---

## Готовность плана

После четырёх задач: документ можно завести только из кода (админского API ещё нет), но публичное чтение работает целиком — список, документ, запасная локаль, невидимый черновик. Следующие планы опираются на `LegalService` и на два публичных маршрута.
