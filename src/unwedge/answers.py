"""Readers for System One answer payloads (TypeSafe jev and Laya return the same schema)."""

from __future__ import annotations

from collections.abc import Mapping


def noul(answers: Mapping[str, Mapping], key: str) -> float:
    return float(answers[key]["noul"])


def score_mass(answers: Mapping[str, Mapping], key: str, level: int) -> float:
    """Probability mass on one Score level. jev omits zero levels and uses string keys;
    Laya lists every level. A missing level is 0.0."""
    probabilities = answers[key].get("probabilities", {})
    return float(probabilities.get(str(level), probabilities.get(level, 0.0)))


def score_value(answers: Mapping[str, Mapping], key: str) -> float:
    return float(answers[key]["score"])


def choice(answers: Mapping[str, Mapping], key: str) -> tuple[str, float]:
    return str(answers[key]["choice"]), float(answers[key].get("confidence", 0.0))
