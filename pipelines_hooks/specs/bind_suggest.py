"""spec-bind-suggest: rank existing tests that may prove a not-yet-VERIFIED requirement row.

Pure and repeatable: the output depends only on ``requirements.md``, the tracked test
files and the alias file. It never edits anything. A candidate is a suggestion that a
reviewer confirms by reading the test; it is not evidence. Scores:

- 100: the row text names ``path::test_name`` and that test exists.
- 85: the row text names a test function that exists once in the repository.
- 90: a test's name or docstring names the row ID (or an old alias of it).
- 80: a test body or comment names the row ID, apart from its own ``spec:`` binding line.
- up to 60: at least two title key terms (and 40% of them) appear in the test name and docstring.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

from pipelines_hooks.core.gitenv import git_text, repo_root
from pipelines_hooks.specs.aliases import load_aliases
from pipelines_hooks.specs.generator import generate
from pipelines_hooks.specs.ids import ROW_RE, TOKEN_RE
from pipelines_hooks.specs.requirements_doc import parse_rows

_TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|[^/]*\.(test|spec)\.(ts|tsx|js|jsx)|[^/]*tests?\.rs)$")
_JS_TEST_RE = re.compile(r"^\s*(?:it|test)(?:\.\w+)?\(\s*([\"'`])(.+?)\1", re.M)
_RUST_TEST_RE = re.compile(r"#\[(?:\w+::)?test[^\]]*\]\s*(?:#\[[^\]]*\]\s*)*(?:async\s+)?fn\s+(\w+)")
_REF_RE = re.compile(r"([\w./\-]+\.(?:py|ts|tsx|js|jsx|rs))::(\w+)")
_NAME_RE = re.compile(r"\b(test_\w+)\b")
_BINDING_LINE_RE = re.compile(r"(?://|#)\s*spec:|mark\.spec\(")
_STOPWORDS = frozenset(
    "with that this from into when each only must should shall will have been their there which while about "
    "after before every using used uses over under than then also both same such other more most less test tests "
    "requirement requirements row rows spec".split()
)
MAX_PER_ROW = 3
MIN_TERMS = 2
MIN_TERM_RATIO = 0.4


class TestCase(NamedTuple):
    """One discovered test: where it is, what it is called, and the text a row may match."""

    __test__ = False
    path: str
    name: str
    head: str  # name + docstring words
    body: str  # source with spec-binding lines removed


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", text).lower().replace("_", " "))
    return {w.rstrip("s") if len(w) > 4 else w for w in words if len(w) >= 4 and w not in _STOPWORDS}


def _strip_bindings(source: str) -> str:
    return "\n".join(line for line in source.splitlines() if not _BINDING_LINE_RE.search(line))


def _python_cases(path: str, source: str) -> list[TestCase]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    cases = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            segment = ast.get_source_segment(source, node) or ""
            doc = ast.get_docstring(node) or ""
            cases.append(TestCase(path, node.name, f"{node.name}\n{doc}", _strip_bindings(segment)))
    return cases


def _other_cases(path: str, source: str) -> list[TestCase]:
    names = [m.group(2) for m in _JS_TEST_RE.finditer(source)] + _RUST_TEST_RE.findall(source)
    body = _strip_bindings(source)
    return [TestCase(path, name, name, body) for name in names]


def discover_tests(root: Path) -> list[TestCase]:
    """Every test in a tracked test file, in path then source order."""
    cases: list[TestCase] = []
    for rel in sorted(git_text(root, ("ls-files",)).splitlines()):
        if not _TEST_FILE_RE.search(rel):
            continue
        try:
            source = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        cases += _python_cases(rel, source) if rel.endswith(".py") else _other_cases(rel, source)
    return cases


def _row_texts(root: Path) -> dict[str, str]:
    """requirement ID -> the rest of its table row (requirement and acceptance cells)."""
    texts: dict[str, str] = {}
    for path in sorted(root.glob("specs/*/requirements.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = ROW_RE.match(line)
            if match:
                texts.setdefault(match.group(1), match.group(2))
    return texts


def _id_names(rid: str, aliases: dict[str, str]) -> set[str]:
    names = {rid}
    for old, new in aliases.items():
        if new == rid:
            names.add(old)
        elif new.endswith("-") and rid.startswith(new):
            names.add(old + rid[len(new) :])
    return names


def _mentions(text: str, names: set[str]) -> bool:
    return any(token in names for token in TOKEN_RE.findall(text))


def _score_case(
    case: TestCase, names: set[str], title_terms: set[str], row_text: str, by_name: dict[str, list[TestCase]]
):
    refs = {(p, n) for p, n in _REF_RE.findall(row_text)}
    if any(case.path.endswith(p) and case.name == n for p, n in refs):
        return 100, "row names this test"
    named = set(_NAME_RE.findall(row_text))
    if case.name in named and len(by_name[case.name]) == 1:
        return 85, "row names this test function"
    if _mentions(case.head, names):
        return 90, "test name or docstring names the row ID"
    if _mentions(case.body, names):
        return 80, "test body names the row ID"
    common = title_terms & _terms(case.head)
    if len(common) >= MIN_TERMS and len(common) / len(title_terms) >= MIN_TERM_RATIO:
        return round(60 * len(common) / len(title_terms)), "title terms in test name: " + ", ".join(sorted(common))
    return 0, ""


def suggest(root: Path, head: str = "HEAD") -> dict:
    """Ranked candidates for every SPECIFIED or LANDED leaf row, plus per-state counts."""
    aliases = load_aliases(root)
    tests = discover_tests(root)
    by_name: dict[str, list[TestCase]] = defaultdict(list)
    for case in tests:
        by_name[case.name].append(case)
    row_text = _row_texts(root)
    titles = {
        row.id: row.title
        for path in sorted(root.glob("specs/*/requirements.md"))
        for row in parse_rows(path.read_text(encoding="utf-8"))
    }
    counts: dict[str, int] = defaultdict(int)
    candidates: list[dict] = []
    matched: set[str] = set()
    for document in generate(root, head).values():
        for record in document["requirements"]:
            state = record["delivery_state"]
            if "rollup_of" in record:
                continue
            counts[state] += 1
            if state not in {"SPECIFIED", "LANDED"}:
                continue
            rid = record["id"]
            names, terms = _id_names(rid, aliases), _terms(titles.get(rid, ""))
            scored = []
            for case in tests:
                score, reason = _score_case(case, names, terms, row_text.get(rid, ""), by_name)
                if score:
                    scored.append((-score, case.path, case.name, reason))
            for neg, path, name, reason in sorted(scored)[:MAX_PER_ROW]:
                matched.add(rid)
                candidates.append(
                    {"row": rid, "state": state, "test": f"{path}::{name}", "score": -neg, "reason": reason}
                )
    candidates.sort(key=lambda c: (-c["score"], c["row"], c["test"]))
    return {
        "repo": root.name,
        "states": dict(sorted(counts.items())),
        "rows_with_candidates": len(matched),
        "candidates": candidates,
    }


def render_markdown(result: dict, min_score: int) -> str:
    lines = [
        f"# spec-bind-suggest: {result['repo']}",
        "",
        f"Leaf rows by state: {result['states']}. Rows with a candidate: {result['rows_with_candidates']}.",
        "",
        "| Row | State | Score | Test | Reason |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| `{c['row']}` | {c['state']} | {c['score']} | `{c['test']}` | {c['reason']} |"
        for c in result["candidates"]
        if c["score"] >= min_score
    ]
    return "\n".join(lines) + "\n"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="spec-bind-suggest", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--min-score", type=int, default=1)
    parser.add_argument("--out", type=Path, default=None, help="write here instead of stdout")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    arguments = _parse_args(argv)
    result = suggest(repo_root(arguments.root), arguments.head)
    result["candidates"] = [c for c in result["candidates"] if c["score"] >= arguments.min_score]
    text = (
        render_markdown(result, arguments.min_score)
        if arguments.format == "markdown"
        else json.dumps(result, indent=2) + "\n"
    )
    if arguments.out:
        arguments.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0
