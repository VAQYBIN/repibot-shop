"""Документация проверяется на полноту машинно: устаревшая инструкция
по развёртыванию хуже её отсутствия.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["README.md", "CONTRIBUTING.md", "LICENSE", "docs/deployment.md"])
def test_required_documents_exist(name: str) -> None:
    assert (ROOT / name).is_file()


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


def test_ci_runs_on_the_development_branch() -> None:
    """Разработка идёт на dev. Проверки, не запускающиеся на ней, бесполезны."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "branches: [main, dev]" in workflow
