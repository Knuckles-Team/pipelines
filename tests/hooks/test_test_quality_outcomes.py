"""PIPE-PAGES-R021.13-.18: tests must observe their outcomes, proven by declared counterexamples."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pipelines_hooks.code import outcomes
from pipelines_hooks.code.test_quality import RULES
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import Repo

CMD = (
    "from pathlib import Path\n\n\n"
    "def run(value, state):\n"
    "    if value < 0:\n        raise ValueError('negative')\n"
    "    Path(state).write_text('done')\n"
    "    return value * 2\n"
)
TESTS = (
    "import pytest\n\nfrom pkg.cmd import run\n\n\n"
    "def test_value(tmp_path):\n"
    "    result = run(21, tmp_path / 's')\n"
    "    assert result == 42\n\n\n"
    "def test_error(tmp_path):\n"
    "    with pytest.raises(ValueError):\n"
    "        run(-1, tmp_path / 's')\n\n\n"
    "def test_state(tmp_path):\n"
    "    run(1, tmp_path / 's')\n"
    "    assert (tmp_path / 's').read_text() == 'done'\n"
)
RUNNER = f'["{sys.executable}", "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:xdist", "--rootdir=."]'


def contract(extra: str = "", *, state_line: int = 18) -> str:
    return f"""version = 1
runner = {RUNNER}
scope = ["tests/test_cmd.py"]
timeout = 120

[[contracts]]
test = "tests/test_cmd.py::test_value"
subject = "pkg.cmd:run"
[[contracts.outcomes]]
kind = "return-value"
observable = "result"
predicate = "== 42"
assertion_line = 8
counterexample = {{file = "pkg/cmd.py", old = "value * 2", new = "value * 3"}}

[[contracts]]
test = "tests/test_cmd.py::test_error"
subject = "pkg.cmd:run"
[[contracts.outcomes]]
kind = "error-state"
observable = "ValueError"
predicate = "raised"
assertion_line = 12
counterexample = {{file = "pkg/cmd.py", old = "raise ValueError('negative')", new = "return 0"}}

[[contracts]]
test = "tests/test_cmd.py::test_state"
subject = "pkg.cmd:run"
[[contracts.outcomes]]
kind = "side-effect"
observable = "state file"
predicate = "== 'done'"
assertion_line = {state_line}
counterexample = {{file = "pkg/cmd.py", old = "'done'", new = "'oops'"}}
[[contracts.not_applicable]]
kind = "return-value"
reason = "the state test checks only the side effect"
{extra}"""


def build(tmp_path: Path, tests: str = TESTS, cts: str | None = None) -> Repo:
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    repo.commit(
        {
            "pkg/__init__.py": "",
            "pkg/cmd.py": CMD,
            "pytest.ini": "[pytest]\npythonpath = .\n",
            "tests/test_cmd.py": tests,
            ".pipelines/outcomes.toml": cts or contract(),
            "coverage.json": json.dumps({"totals": {"percent_covered": 95}}),
        }
    )
    return repo


# spec: PIPE-PAGES-R021.13
def test_model_rule_and_contract_shape(tmp_path: Path) -> None:
    assert "outcome-not-observed" in RULES
    build(tmp_path)
    runner, scope, _, contracts, digest = outcomes.load_contracts(tmp_path / ".pipelines/outcomes.toml")
    assert scope == ["tests/test_cmd.py"] and len(digest) == 64
    assert [c.outcomes[0]["kind"] for c in contracts] == ["return-value", "error-state", "side-effect"]
    assert outcomes.OutcomeProof("t", "return-value", "pass", "FAILED", "f:1", "pass").status == "pass"


# spec: PIPE-PAGES-R021.14
def test_counterexamples_fail_at_the_designated_assertion(tmp_path: Path) -> None:
    build(tmp_path)
    result = outcomes.check(tmp_path, tmp_path / ".pipelines/outcomes.toml")
    assert result.findings == [] and [p.status for p in result.proofs] == ["pass", "pass", "pass"]
    ignoring = TESTS.replace("    assert result == 42\n", "    assert result is not None\n")
    (tmp_path / "weak").mkdir()
    weak = build(tmp_path / "weak", ignoring)
    survived = outcomes.check(weak.root, weak.root / ".pipelines/outcomes.toml")
    assert survived.findings == [("tests/test_cmd.py", 8, "outcome-not-observed")]


# spec: PIPE-PAGES-R021.15
def test_wiring_through_the_gate_and_a_disposable_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path)
    assert repo.run("test-quality") == 0
    assert (tmp_path / "pkg/cmd.py").read_text() == CMD and not (tmp_path / ".pytest_cache").exists()
    bare = TESTS + "\n\ndef test_extra():\n    assert 1 == 1\n"
    repo.commit({"tests/test_cmd.py": bare})
    assert repo.run("test-quality") == 1
    assert "test_cmd.py:21 outcome-not-observed" in capsys.readouterr().out


# spec: PIPE-PAGES-R021.16
def test_refusals(tmp_path: Path) -> None:
    repo = build(tmp_path)
    repo.commit(
        {
            "tests/test_cmd.py": TESTS.replace(
                "def test_value(tmp_path):",
                "@pytest.mark.skip(reason='skipped for the proof')\ndef test_value(tmp_path):",
            )
        }
    )
    assert repo.run("test-quality") == 2
    repo.commit({"tests/test_cmd.py": TESTS})
    repo.commit({".pipelines/outcomes.toml": contract(state_line=17)})  # the call line, not an assertion
    assert repo.run("test-quality") == 2
    unrelated = contract().replace("old = \"'done'\", new = \"'oops'\"", 'old = "Path(state)", new = "Pathx(state)"')
    repo.commit({".pipelines/outcomes.toml": unrelated})
    with pytest.raises(CannotRun, match="outside the designated assertion"):
        outcomes.check(tmp_path, tmp_path / ".pipelines/outcomes.toml")
    repo.commit({".pipelines/outcomes.toml": "version = 1\n"})
    assert repo.run("test-quality") == 2


# spec: PIPE-PAGES-R021.17
def test_evidence_separates_static_from_measured(tmp_path: Path) -> None:
    build(tmp_path)
    ev = outcomes.check(tmp_path, tmp_path / ".pipelines/outcomes.toml").evidence
    assert {p["kind"] for p in ev["proofs"]} == {"return-value", "error-state", "side-effect"}  # type: ignore[attr-defined,union-attr]
    assert ev["not_applicable"] == [
        {
            "test": "tests/test_cmd.py::test_state",
            "kind": "return-value",
            "reason": "the state test checks only the side effect",
        }
    ]
    assert len(str(ev["policy_digest"])) == 64 and "not all semantics" in str(ev["measured"])


# spec: PIPE-PAGES-R021.18
def test_hot_path_constant_unrelated_and_ignored_results_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = build(tmp_path)
    assert repo.run("test-quality") == 0
    constant = TESTS.replace("    assert result == 42\n", "    assert True\n")
    repo.commit({"tests/test_cmd.py": constant})
    assert repo.run("test-quality") == 1
    ignored = TESTS.replace("    assert result == 42\n", "    assert tmp_path.exists()\n")
    repo.commit({"tests/test_cmd.py": ignored})
    assert repo.run("test-quality") == 1
    assert "tests/test_cmd.py:8 outcome-not-observed" in capsys.readouterr().out
    repo.commit({"tests/test_cmd.py": TESTS})
    assert repo.run("test-quality") == 0
