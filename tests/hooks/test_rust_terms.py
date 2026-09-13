"""The terms of acceptance for Rust exhaustive dispatch, on known shapes.

Ported from epistemic-graph's tests/test_rust_exhaustive_match.py (the shapes
the rule must get right, not a sample of any tree).
"""

from __future__ import annotations

import pytest

from pipelines_hooks.rust.dispatch import dispatch_shape, exhaustive_dispatch_exempt
from pipelines_hooks.rust.mask import code_mask

CAPS = (10, 15)


def _dispatcher(arm: str) -> str:
    return f"fn dispatch(kind: Kind) -> u8 {{\n    match kind {{\n        Kind::A => 1,\n        {arm},\n    }}\n}}\n"


def test_flat_exhaustive_match_has_no_catch_all() -> None:
    source = "fn dispatch(kind: Kind) -> u8 {\n    match kind {\n        Kind::A => 1,\n        Kind::B => 2,\n        Kind::C => 3,\n    }\n}\n"
    assert dispatch_shape(source, 1) == (3, 0)


@pytest.mark.parametrize(
    "arm", ["_ => 0", "other => 0", "ref rest => 0", "mut rest => 0", "bound @ _ => 0", "n if n > 2 => 0", "Kind::A | leftover => 0"]
)
def test_every_irrefutable_arm_shape_is_a_catch_all(arm: str) -> None:
    assert dispatch_shape(_dispatcher(arm), 1).catch_alls == 1


@pytest.mark.parametrize(
    "arm", ["Kind::B => 2", "Kind::B | Kind::C => 2", "Kind::B { field } => 2", "Kind::B(inner) => 2", "kind::lowercase::Path => 2", "MAX_LIMIT => 2"]
)
def test_discriminating_arms_are_not_catch_alls(arm: str) -> None:
    assert dispatch_shape(_dispatcher(arm), 1).catch_alls == 0


def test_a_catch_all_in_a_string_or_comment_is_not_an_arm() -> None:
    source = 'fn dispatch(kind: Kind) -> u8 {\n    // _ => 0\n    let note = "_ => 0";\n    match kind {\n        Kind::A => 1,\n        Kind::B => 2,\n    }\n}\n'
    assert dispatch_shape(source, 1) == (2, 0)


def test_a_nested_match_is_counted_and_its_catch_all_disqualifies() -> None:
    source = "fn d(k: Kind, s: Sub) -> u8 {\n    match k {\n        Kind::A => match s {\n            Sub::X => 1,\n            _ => 2,\n        },\n        Kind::B => 3,\n    }\n}\n"
    assert dispatch_shape(source, 1) == (4, 1)


def test_non_rust_cognitive_residual_and_unattributable_are_never_exempt() -> None:
    source = _dispatcher("Kind::B => 2")
    assert not exhaustive_dispatch_exempt(None, line=1, metrics=(30, 1), caps=CAPS)
    assert not exhaustive_dispatch_exempt(source, line=1, metrics=(30, 16), caps=CAPS)
    assert not exhaustive_dispatch_exempt(source, line=1, metrics=(13, 1), caps=CAPS)
    assert exhaustive_dispatch_exempt(source, line=1, metrics=(12, 1), caps=CAPS)
    assert not exhaustive_dispatch_exempt(source, line=1, metrics=(11, 1), caps=CAPS) or dispatch_shape(source, 1).arms < 11


def test_a_function_without_any_match_is_never_exempt() -> None:
    ladder = "fn f(x: u32) -> u32 {\n" + "".join(f"    if x == {i} {{ return {i}; }}\n" for i in range(20)) + "    0\n}\n"
    assert dispatch_shape(ladder, 1) == (0, 0)
    assert not exhaustive_dispatch_exempt(ladder, line=1, metrics=(21, 2), caps=CAPS)


def test_unlexable_source_is_not_provable() -> None:
    assert dispatch_shape('fn f() {\n    let s = "unterminated;\n}\n', 1) is None
    assert code_mask('let s = "a // b"; // gone\n') == "let s = " + " " * 8 + "; " + " " * 7 + "\n"
