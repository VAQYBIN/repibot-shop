"""Документация проверяется на полноту машинно: устаревшая инструкция
по развёртыванию хуже её отсутствия.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["README.md", "CONTRIBUTING.md", "LICENSE", "docs/deployment.md"])
def test_required_documents_exist(name: str) -> None:
    assert (ROOT / name).is_file()


COMMUNITY_FILES = (
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
)


@pytest.mark.parametrize("name", COMMUNITY_FILES)
def test_community_files_exist(name: str) -> None:
    """README на них ссылается, а GitHub показывает их в интерфейсе.

    Пропавший файл превращает и то и другое в ссылку на 404.
    """
    assert (ROOT / name).is_file()


def test_readme_shows_the_banner() -> None:
    """Шапка — единственное, что видно до прокрутки.

    Перепутанные условия media в <picture> — самая вероятная ошибка при
    правке README, а присутствия одних только имён файлов для её поимки
    недостаточно: тёмная и светлая версии должны стоять под своим условием.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert (
        '<source media="(prefers-color-scheme: dark)" srcset="docs/design/logo/banner.svg">'
        in readme
    )
    assert (
        '<source media="(prefers-color-scheme: light)" '
        'srcset="docs/design/logo/banner-light.svg">' in readme
    )


def test_readme_covers_local_start() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for fragment in ("docker compose up", "uv run check", ".env.example"):
        assert fragment in readme


def test_deployment_covers_botfather_oidc_setup() -> None:
    """Redirect URI и Trusted Origins задаются в BotFather — забыть их
    невозможно обнаружить иначе, чем сломанным входом через Telegram."""
    deployment = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    for fragment in ("BotFather", "Redirect URI", "Trusted Origins", "REMNAWAVE_TOKEN"):
        assert fragment in deployment


def test_readme_documents_where_specs_live() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "docs/superpowers/specs" in readme


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


def test_deployment_explains_the_support_supergroup() -> None:
    """Право управления темами — единственная неочевидная часть настройки.

    Без него `createForumTopic` отвечает отказом, обращения молча копятся в
    очереди, и человек ждёт ответа, которого никто не увидел.
    """
    deployment = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    for fragment in ("SUPPORT_CHAT_ID", "управление темами", "-100"):
        assert fragment in deployment


def test_deployment_lists_every_scheduled_task() -> None:
    """Задача без строки в таблице расписаний — задача, о которой узнают
    только тогда, когда она сломается."""
    tasks = (ROOT / "backend" / "core" / "src" / "repibot_core" / "tasks.py").read_text(
        encoding="utf-8"
    )
    deployment = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    scheduled = re.findall(r"@broker\.task\([^\n]*schedule=[^\n]*\)\s*\nasync def (\w+)", tasks)

    assert scheduled, "не найдено ни одной задачи с расписанием — сломался разбор"
    assert [name for name in scheduled if f"`{name}`" not in deployment] == []


def test_ci_runs_on_the_development_branch() -> None:
    """Разработка идёт на dev. Проверки, не запускающиеся на ней, бесполезны."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "branches: [main, dev]" in workflow
