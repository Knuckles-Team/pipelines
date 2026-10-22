"""spec-standard refuses third-party product names in authored spec text (PIPE-GATES-R005)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.specs.standard import main
from pipelines_hooks.specs.third_party_names import CONFIG, check_repository, load_terms
from tests.git_fixture_environment import fixture_git_environment

FILES = ("spec.md", "plan.md", "requirements.md", "tasks.md", "test-spec.md", "status.json")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], env=fixture_git_environment(), check=True)
    d = tmp_path / "specs" / "foo"
    d.mkdir(parents=True)
    for name in FILES:
        (d / name).write_text('{"spec_id": "FOO"}\n' if name.endswith(".json") else "x\n")
    (d / "spec.md").write_text("# FOO — Title\n")
    (d / "requirements.md").write_text("| `FOO-R001` | **Merge.** Merge branches by evidence. | test |\n")
    (tmp_path / "specs" / "README.md").write_text("- [x](foo/spec.md)\n")
    return tmp_path


def _write(root: Path, name: str, text: str) -> None:
    (root / "specs" / "foo" / name).write_text(text)


def test_clean_spec_passes(root, capsys):
    assert main(["--root", str(root)]) == 0
    assert "spec-standard: clean" in capsys.readouterr().out


@pytest.mark.parametrize(
    "text",
    [
        "| `FOO-R001` | **Merge.** A Stardog-style virtual graph. | t |\n",
        "Unlike LangGraph, this spec merges by evidence.\n",
        "The comparator (ModernRelay/omnigraph) uses last-write-wins.\n",
        "This follows GitHub Spec Kit's flow.\n",
        "Parity with openclaw channels.\n",
    ],
)
def test_named_product_is_a_finding(root, capsys, text):
    # spec: PIPE-GATES-R005
    _write(root, "plan.md", text)
    assert main(["--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "specs/foo/plan.md:1: names third-party product" in out


@pytest.mark.parametrize(
    "text",
    [
        "Run `opencode.json` as the entry point.\n",
        "```\nLangfuse host\n```\n",
        "See [the trace store](https://langfuse.example/docs).\n",
        "The `langfuse` connector and the langfuse-agent repository.\n",
        "The langfuse connector answers the question.\n",
        "SPARQL, OWL, RDF, SHACL, OpenTelemetry, OIDC, MCP and A2A.\n",
        "Scores arrive per CONN-LANGFUSE-AGENT-TRACE-INGEST-R001.2 and the Bolt protocol.\n",
    ],
)
def test_identifiers_code_links_and_standards_pass(root, capsys, text):
    _write(root, "plan.md", text)
    assert main(["--root", str(root)]) == 0, capsys.readouterr().out


def test_lowercase_term_glued_to_identifier_punctuation_passes(root):
    _write(root, "plan.md", "The harness2-compat branch, and harness2 itself.\n")
    found = check_repository(root, "any")
    assert len(found) == 1 and "'harness2'" in found[0]


def test_evidence_files_are_not_authored_text(root):
    (root / "specs" / "foo" / "evidence").mkdir()
    (root / "specs" / "foo" / "evidence" / "run.md").write_text("Recorded by Codex.\n")
    assert check_repository(root, "any") == []


def test_connector_may_name_its_own_target(root):
    # spec: PIPE-GATES-R005
    _write(root, "spec.md", "# FOO — Title\n\nReads traces from Langfuse.\n")
    assert check_repository(root, "langfuse-agent") == []
    assert len(check_repository(root, "agent-utilities")) == 1


def test_allowance_is_per_repository():
    assert "Langfuse" not in load_terms("langfuse-agent")
    assert "Langfuse" in load_terms("vector-mcp")
    assert "Qdrant" not in load_terms("vector-mcp")


def test_config_ships_with_the_package():
    assert CONFIG.is_file()
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert "specs/third_party_names.toml" in pyproject
