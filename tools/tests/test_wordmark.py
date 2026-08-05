"""Вордмарк в кривых.

Двоеточие — часть марки, а не пунктуация (раздел 5), поэтому оно лежит
отдельным контуром: иначе его нельзя покрасить в Jade.
"""

from tools.brand import wordmark_paths
from tools.brand.wordmark_source import render


def test_letters_and_colon_are_separate_shapes() -> None:
    assert wordmark_paths.LETTERS.startswith("M")
    assert wordmark_paths.COLON.startswith("M")
    assert wordmark_paths.COLON not in wordmark_paths.LETTERS


def test_all_seven_letters_are_present() -> None:
    """re + pibot — семь букв, каждая начинается своей командой M."""
    assert wordmark_paths.LETTERS.count("M") >= 7


def test_colon_is_two_dots() -> None:
    assert wordmark_paths.COLON.count("M") == 2


def test_metrics_match_inter() -> None:
    assert wordmark_paths.UNITS_PER_EM == 2048
    assert wordmark_paths.X_HEIGHT == 1118
    assert wordmark_paths.CAP_HEIGHT == 1490


def test_kerning_is_applied() -> None:
    """Сумма ширин глифов дала бы 7171. HarfBuzz с кернингом — 7132."""
    assert wordmark_paths.ADVANCE == 7132.0


def test_generation_is_deterministic() -> None:
    """Иначе verify_generated будет ругаться при каждом прогоне."""
    assert render() == render()
