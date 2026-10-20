"""The published gate set partition (PIPE-GATES-R001): the fast set and the full set.

T-001: the partition test asserts both sets' exact membership from the
published gate configuration and asserts that the full set is the fast
set's complement within the eight blocking gates. It also fails a
configuration missing one blocking gate or declaring a ninth.
"""

from __future__ import annotations

import pytest
from pipelines_hooks.cli import ALIASES, GATES, GROUPS
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.gate_sets import BLOCKING_GATES, GateSets, load_gate_sets, published_sets


def test_the_fast_set_is_exactly_the_five_pre_land_gates() -> None:
    # spec: PIPE-GATES-R001
    sets = published_sets()
    assert set(sets.fast) == {"format", "hygiene", "secrets", "types", "tests-fast"}


def test_the_full_set_is_exactly_the_complement_within_the_eight() -> None:
    # spec: PIPE-GATES-R001
    sets = published_sets()
    assert set(sets.full) == {"spec", "tests", "supply-chain"}
    assert set(sets.full) == set(sets.blocking) - set(sets.fast)
    assert set(sets.fast) & set(sets.full) == set()
    assert set(sets.fast) | set(sets.full) == set(sets.blocking)
    assert len(sets.blocking) == 8


def test_the_partition_matches_the_published_gate_infrastructure() -> None:
    # spec: PIPE-GATES-R001
    published = {*GATES, *GROUPS, *ALIASES}
    sets = published_sets()
    assert {"secrets", "tests-fast", "spec", "supply-chain"} <= published
    assert set(sets.blocking) - published == {"format", "hygiene", "types", "tests"}


def _render(key: str, value: object) -> str:
    if isinstance(value, list):
        return f"{key} = [{', '.join(repr(item) for item in value)}]"
    return f"{key} = {value!r}"


def _document(**overrides: object) -> str:
    doc: dict[str, object] = {
        "version": 1,
        "blocking": ["format", "hygiene", "secrets", "types", "tests-fast", "spec", "tests", "supply-chain"],
        "fast": ["format", "hygiene", "secrets", "types", "tests-fast"],
        "full": ["spec", "tests", "supply-chain"],
    }
    doc.update(overrides)
    return "\n".join(_render(key, value) for key, value in doc.items()) + "\n"


def _load(tmp_path, **overrides: object) -> GateSets:
    path = tmp_path / "gate-sets.toml"
    path.write_text(_document(**overrides), encoding="utf-8")
    return load_gate_sets(path)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("blocking", ["format", "hygiene", "secrets", "types", "tests-fast", "spec", "supply-chain"]),
        ("blocking", ["format", "hygiene", "secrets", "types", "tests-fast", "spec", "tests", "supply-chain", "lint"]),
        ("fast", ["format", "hygiene", "secrets", "types", "tests-fast", "lint"]),
        ("full", ["spec", "tests", "supply-chain", "format"]),
        ("fast", ["format", "hygiene", "secrets", "types", "tests-fast", "spec"]),
        ("full", ["spec", "supply-chain"]),
        ("fast", ["format", "format", "hygiene", "secrets", "types", "tests-fast"]),
        ("version", 2),
    ],
)
def test_a_declared_deviation_from_the_standard_fails_closed(tmp_path, key: str, value: object) -> None:
    # spec: PIPE-GATES-R001
    with pytest.raises(CannotRun, match="gate-sets"):
        _load(tmp_path, **{key: value})


def test_a_missing_blocking_gate_is_named(tmp_path) -> None:
    # spec: PIPE-GATES-R001
    with pytest.raises(CannotRun, match="missing .*secrets"):
        _load(tmp_path, blocking=["format", "hygiene", "types", "tests-fast", "spec", "tests", "supply-chain"])


def test_a_ninth_blocking_gate_is_named(tmp_path) -> None:
    # spec: PIPE-GATES-R001
    with pytest.raises(CannotRun, match="lint"):
        _load(
            tmp_path,
            blocking=["format", "hygiene", "secrets", "types", "tests-fast", "spec", "tests", "supply-chain", "lint"],
        )


def test_the_shipped_declaration_loads_clean() -> None:
    # spec: PIPE-GATES-R001
    sets = published_sets()
    assert sets.blocking == BLOCKING_GATES
