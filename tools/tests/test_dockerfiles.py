"""Инварианты образов проверяются чтением файлов: сборка в тестах слишком дорога.

Эти проверки ловят ровно те ошибки, которые иначе всплывают на продакшене:
образ от root, отсутствие кеша слоёв, забытый .dockerignore.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKER = ROOT / "docker"


@pytest.fixture(scope="module")
def backend() -> str:
    return (DOCKER / "backend.Dockerfile").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def web() -> str:
    return (DOCKER / "web.Dockerfile").read_text(encoding="utf-8")


def test_backend_is_multi_stage(backend: str) -> None:
    assert backend.count("FROM ") >= 2


def test_backend_installs_dependencies_before_copying_sources(backend: str) -> None:
    """Иначе правка одной строки кода пересобирает все зависимости заново."""
    deps_install = backend.index("--no-install-project")
    full_copy = backend.index("COPY . .")

    assert deps_install < full_copy


def test_backend_does_not_install_dev_dependencies(backend: str) -> None:
    assert "--no-dev" in backend


def test_backend_runs_as_non_root(backend: str) -> None:
    assert "USER " in backend
    assert "USER root" not in backend


def test_web_uses_standalone_output(web: str) -> None:
    assert ".next/standalone" in web


def test_web_runs_as_non_root(web: str) -> None:
    assert "USER " in web


def test_dockerignore_excludes_heavy_and_secret_paths() -> None:
    ignored = set((ROOT / ".dockerignore").read_text(encoding="utf-8").split())

    for entry in (".git", ".venv", "node_modules", ".env", "docs"):
        assert entry in ignored, f"{entry} не исключён из контекста сборки"
