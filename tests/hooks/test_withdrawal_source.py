"""Rust evidence withdrawals cannot change literals, code, or unrelated comments."""

import pytest

from pipelines_hooks.specs.withdrawal_source import source_withdrawal_only

_IDS = {"DEMO-R001"}
_MARKER = "// spec: DEMO-R001\n"
_REASON = (
    "// Partial refusal coverage for DEMO-R001; "
    "successful-operation acceptance remains open.\n"
)


# spec: PIPE-CONNSPEC-R001
@pytest.mark.parametrize("replacement", ["", _REASON])
def test_actual_comment_removal_or_replacement(replacement: str) -> None:
    source = "fn test_refusal() { assert!(true); }\n"
    assert source_withdrawal_only(_MARKER + source, replacement + source, _IDS)


@pytest.mark.parametrize("prefix", ["r", "br", "cr"])
@pytest.mark.parametrize("hashes", ["", "#", "###"])
def test_raw_string_marker_is_not_evidence(prefix: str, hashes: str) -> None:
    opening = f'const TEXT: &str = {prefix}{hashes}"\n'
    closing = f'"{hashes};\n'
    assert not source_withdrawal_only(
        opening + _MARKER + closing, opening + closing, _IDS
    )


@pytest.mark.parametrize(
    ("opening", "closing"),
    [
        ('const TEXT: &str = "\n', '";\n'),
        ('const TEXT: &str = "escaped \\"\n', '";\n'),
        ("/* outer /* nested */\n", "*/\n"),
        ("/* outer /* nested\n", "*/ */\n"),
    ],
)
def test_non_comment_marker_is_preserved(opening: str, closing: str) -> None:
    assert not source_withdrawal_only(
        opening + _MARKER + closing, opening + closing, _IDS
    )


@pytest.mark.parametrize(
    "source",
    [
        "fn borrow<'a>(value: &'a str) {}\n",
        "fn borrow(value: &'static str) {}\n",
        "const CHARACTER: char = '\"';\n",
        "const CHARACTER: char = '\\'';\n",
        "const CHARACTER: char = '/';\n",
        "const CHARACTER: char = 'é';\n",
    ],
)
def test_literals_and_lifetimes_do_not_hide_actual_comments(source: str) -> None:
    assert source_withdrawal_only(source + _MARKER, source, _IDS)


@pytest.mark.parametrize(
    "source",
    [
        'const TEXT: &str = r#"unfinished\n',
        'const TEXT: &str = "unfinished\n',
        "/* unfinished\n",
    ],
)
def test_unfinished_tokens_fail_closed(source: str) -> None:
    assert not source_withdrawal_only(source + _MARKER, source, _IDS)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (_MARKER + "fn original() {}\n", "fn feature() {}\n"),
        ("// spec: DEMO-R002\n", ""),
        ("// ordinary comment\n", ""),
        ("fn original() {} " + _MARKER, "fn original() {}\n"),
        (_MARKER, "// arbitrary replacement\n"),
    ],
)
def test_unrelated_changes_fail(before: str, after: str) -> None:
    assert not source_withdrawal_only(before, after, _IDS)
