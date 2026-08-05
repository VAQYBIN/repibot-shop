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
