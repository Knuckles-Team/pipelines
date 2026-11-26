"""PIPE-GATES-R066: each gate has a test that plants a violation in its stated universe.

A hook is covered when a test function under ``tests/hooks/`` runs it and asserts a refusal
(exit 1 or 2, or ``CannotRun``), and a test function runs it and asserts a clean exit. A test
runs a hook by naming its id in a quoted string, or by importing the gate module and calling
its ``main`` or a check function. A group hook is covered through its members and an alias
through its target. There is no allowance list: a hook without such tests is a finding.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

from pipelines_hooks.cli import ALIASES, GATES, GROUPS

ROOT = Path(__file__).resolve().parents[1]
REFUSAL = re.compile(r"==\s*[12]\b|!=\s*0|pytest\.raises\(CannotRun")
CLEAN = re.compile(r"==\s*0\b|assert not \w+|== \[\]|== \(\)")
CALL = re.compile(r"\b(main|findings|scan|check\w*|run\w*)\(")


def load_catalogue(root: Path = ROOT) -> dict[str, str]:
    """Hook id -> the gate id its entry runs."""
    hooks = yaml.safe_load((root / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    return {hook["id"]: hook["entry"].split()[1] for hook in hooks}


def _test_functions(tests: Path) -> list[tuple[set[str], str]]:
    found = []
    for path in sorted(tests.rglob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported |= {f"{node.module or ''}.{alias.name}" for alias in node.names}
            elif isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
        found += [
            (imported, ast.get_source_segment(text, fn) or "")
            for fn in ast.walk(tree)
            if isinstance(fn, ast.FunctionDef) and fn.name.startswith("test")
        ]
    return found


def _runs(gate: str, imported: set[str], source: str) -> bool:
    if re.search(r"""["']""" + re.escape(gate) + r"""["']""", source):
        return True
    module = GATES.get(gate)
    return bool(module and any(i == module or i.startswith(module + ".") for i in imported) and CALL.search(source))


def hooks_without_planted_test(catalogue: dict[str, str], tests: Path) -> list[str]:
    """Hook ids with no refusal test or no clean test, as ``<id>: <what is missing>``."""
    functions = _test_functions(tests)
    missing = []
    for hook, entry in sorted(catalogue.items()):
        gate = ALIASES.get(entry, entry)
        names = [gate, *GROUPS.get(gate, ())]
        for kind, pattern in (("planted violation", REFUSAL), ("clean tree", CLEAN)):
            if not any(_runs(n, imp, src) and pattern.search(src) for imp, src in functions for n in names):
                missing.append(f"{hook}: no {kind} test under tests/hooks")
    return missing


# spec: PIPE-GATES-R066
def test_every_catalogue_hook_has_a_planted_violation_test() -> None:
    assert hooks_without_planted_test(load_catalogue(), ROOT / "tests" / "hooks") == []


# spec: PIPE-GATES-R066
def test_a_hook_without_a_test_is_listed(tmp_path: Path) -> None:
    (tmp_path / "test_demo.py").write_text(
        "from tests.hooks.conftest import Repo\n\n"
        "def test_covered(repo: Repo) -> None:\n    assert repo.run('public-surface') == 1\n\n"
        "def test_covered_clean(repo: Repo) -> None:\n    assert repo.run('public-surface') == 0\n\n"
        "def test_only_planted(repo: Repo) -> None:\n    assert repo.run('swallowed-errors') == 1\n",
        encoding="utf-8",
    )
    catalogue = {"public-surface": "public-surface", "swallowed-errors": "swallowed-errors", "env-sprawl": "env-sprawl"}
    assert hooks_without_planted_test(catalogue, tmp_path) == [
        "env-sprawl: no planted violation test under tests/hooks",
        "env-sprawl: no clean tree test under tests/hooks",
        "swallowed-errors: no clean tree test under tests/hooks",
    ]
    published = load_catalogue()
    assert published["spec-glossary"] == "spec-glossary" and "contract-coverage" in published
