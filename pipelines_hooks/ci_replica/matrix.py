"""GitHub Actions expression handling: matrix substitution and expression stripping."""

from __future__ import annotations

import re
from itertools import product

GHA_EXPRESSION_RE = re.compile(r"\$\{\{.*?\}\}")
MATRIX_EXPRESSION_RE = re.compile(r"\$\{\{\s*matrix\.([\w.-]+)\s*\}\}")


def strip_expressions(text: str) -> tuple[str, list[str]]:
    """Blank every remaining ``${{ ... }}`` (github/env/secrets contexts do not exist locally)."""
    return GHA_EXPRESSION_RE.sub("", text), GHA_EXPRESSION_RE.findall(text)


def _lookup(combo: dict, dotted: str) -> str | None:
    value: object = combo
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return "" if value is None else str(value)


def substitute_matrix(text: str, combo: dict) -> str:
    """Resolve ``${{ matrix.a.b }}`` against one leg; unresolved references stay for stripping."""
    return MATRIX_EXPRESSION_RE.sub(lambda m: m.group(0) if _lookup(combo, m.group(1)) is None else str(_lookup(combo, m.group(1))), text)


def matrix_combinations(matrix: dict | None) -> list[dict]:
    """Cartesian legs of the axes plus each ``include`` entry (``exclude`` is not modelled)."""
    table = matrix or {}
    return (_axis_legs(table) + _include_legs(table)) or [{}]


def _axis_legs(table: dict) -> list[dict]:
    axes = {key: values for key, values in table.items() if key not in ("include", "exclude") and isinstance(values, list)}
    if not axes:
        return []
    return [dict(zip(axes, values, strict=True)) for values in product(*axes.values())]


def _include_legs(table: dict) -> list[dict]:
    return [dict(extra) for extra in table.get("include") or [] if isinstance(extra, dict)]


def combo_label(combo: dict) -> str:
    """``#name`` of a matrix leg, e.g. ``#ubuntu-latest``."""
    if not combo:
        return ""
    if "name" in combo and not isinstance(combo["name"], dict):
        return f"#{combo['name']}"
    return "#" + "-".join(str(v.get("name", v)) if isinstance(v, dict) else str(v) for v in combo.values())


def apply_matrix(step: dict, combo: dict) -> dict:
    if not combo:
        return step
    return {key: substitute_matrix(value, combo) if key in ("run", "name", "uses") and isinstance(value, str) else value for key, value in step.items()}
