"""Byte-identical wheels across two independent builds (PIPE-RELEASE-R003 remaining half).

This host cannot build the fleet's Rust/maturin wheels; this exercises the
real comparison tool end to end against a pure-Python fixture package, using
the actual build backend (no network: ``--no-isolation`` reuses this
project's own locked ``build``/``setuptools``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from release_fixtures import write_reproducible_fixture

from scripts.release.errors import ReproducibilityError
from scripts.release.reproducibility import build_wheel_twice, compare_wheels


def test_building_the_same_source_twice_with_one_source_date_epoch_is_byte_identical(tmp_path: Path) -> None:
    source = write_reproducible_fixture(tmp_path / "source")
    wheel_a, wheel_b = build_wheel_twice(source, tmp_path / "out-a", tmp_path / "out-b", source_date_epoch="1700000000")
    result = compare_wheels(wheel_a, wheel_b)
    assert result.identical, result.differences
    assert wheel_a.read_bytes() == wheel_b.read_bytes()


def test_a_deliberately_different_source_date_epoch_is_detected_as_not_reproducible(tmp_path: Path) -> None:
    source_one = write_reproducible_fixture(tmp_path / "source-one")
    source_two = write_reproducible_fixture(tmp_path / "source-two")
    wheel_one, _ = build_wheel_twice(source_one, tmp_path / "one-a", tmp_path / "one-b", source_date_epoch="1700000000")
    wheel_two, _ = build_wheel_twice(source_two, tmp_path / "two-a", tmp_path / "two-b", source_date_epoch="1700000100")

    result = compare_wheels(wheel_one, wheel_two)

    assert not result.identical
    assert result.differences
    assert any("timestamp differs" in line for line in result.differences)


def test_a_build_that_produces_no_wheel_cannot_run(tmp_path: Path) -> None:
    empty_source = tmp_path / "empty"
    empty_source.mkdir()
    with pytest.raises(ReproducibilityError):
        build_wheel_twice(empty_source, tmp_path / "out-a", tmp_path / "out-b", source_date_epoch="1700000000")
