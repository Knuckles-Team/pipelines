"""change-scope: one classification per pull request decides which gates run (PIPE-RELEASE-R007.8-.10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.ci_replica.change_scope import SPEC_GATES, classify, scope_for
from tests.hooks.conftest import Repo

CONFIG = """repos:
  - repo: local
    hooks:
      - {id: spec, name: spec, entry: x, language: system, pass_filenames: false, always_run: true}
      - {id: trailing-whitespace, name: ws, entry: x, language: system}
      - {id: tests-fast, name: tests, entry: x, language: system, pass_filenames: false}
      - {id: ruff-check, name: ruff, entry: x, language: system}
      - {id: medulla-journeys, name: journeys, entry: x, language: system, always_run: true}
"""


def _outputs(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line and ":" not in line.split("=", 1)[0])


# spec: PIPE-RELEASE-R007.8
@pytest.mark.parametrize(
    ("paths", "scope", "classes"),
    [
        (["specs/a/requirements.md", "specs/a/tasks.md", ".specify/memory/constitution.md"], "spec", {"spec"}),
        (["specs/a/contracts/api.yaml", "specs/a/checklists/review.md"], "spec", {"spec"}),
        (["docs/guide.md", "README.md", "LICENSE", "plans/x.md"], "spec", {"docs"}),
        (["pkg/module.py"], "code", {"python"}),
        (["crates/core/src/lib.rs"], "code", {"rust"}),
        (["web/src/app.tsx"], "code", {"frontend"}),
        ([".github/workflows/ci.yml"], "full", {"ci"}),
        ([".config/pre-commit.yaml"], "full", {"ci"}),
        (["uv.lock"], "full", {"deps"}),
        (["crates/core/Cargo.toml"], "full", {"deps"}),
        (["specs/a/requirements.md", "pkg/module.py"], "code", {"spec", "python"}),
        (["specs/a/requirements.md", "data/blob.bin"], "code", {"spec", "other"}),
    ],
)
def test_change_scope_classifies_each_fixture_diff(paths: list[str], scope: str, classes: set[str]) -> None:
    outputs = scope_for(paths)
    assert outputs["scope"] == scope
    assert {name for name in classes if outputs[name] == "true"} == classes
    assert outputs["code"] == str(scope != "spec").lower()


# spec: PIPE-RELEASE-R007.8
def test_change_scope_writes_step_outputs_and_the_spec_skip_list(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = repo.commit({".config/pre-commit.yaml": CONFIG, "pkg/a.py": "A = 1\n"}, "baseline")
    repo.commit({"specs/x/requirements.md": "# x\n", "specs/x/plan.md": "# p\n"}, "spec only")
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert repo.run("change-scope", "--base-ref", base, "--config", ".config/pre-commit.yaml") == 0
    stdout = capsys.readouterr().out
    written = _outputs(output.read_text(encoding="utf-8"))
    assert written == _outputs(stdout)
    assert written["scope"] == "spec" and written["code"] == "false" and written["spec"] == "true"
    assert written["skip-hooks"] == "tests-fast,ruff-check,medulla-journeys"
    assert "not applicable" in stdout


# spec: PIPE-RELEASE-R007.9
def test_change_scope_keeps_every_hook_for_code_and_full_runs(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit({".config/pre-commit.yaml": CONFIG, "pkg/a.py": "A = 1\n"}, "baseline")
    repo.commit({"pkg/a.py": "A = 2\n", "specs/x/requirements.md": "# x\n"}, "code and spec")
    assert repo.run("change-scope", "--base-ref", base, "--config", ".config/pre-commit.yaml") == 0
    code = _outputs(capsys.readouterr().out)
    assert code["scope"] == "code" and code["skip-hooks"] == ""
    assert repo.run("change-scope", "--force-full", "--config", ".config/pre-commit.yaml") == 0
    full = _outputs(capsys.readouterr().out)
    assert full["scope"] == "full" and full["skip-hooks"] == ""
    assert "spec" in SPEC_GATES and "tests-fast" not in SPEC_GATES


# spec: PIPE-RELEASE-R007.10
def test_change_scope_refuses_and_falls_back_conservatively(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit({"pkg/a.py": "A = 1\n"}, "baseline")
    repo.git("rm", "-q", "pkg/a.py")
    repo.git("commit", "-qm", "delete")
    assert repo.run("change-scope", "--base-ref", base) == 0
    assert _outputs(capsys.readouterr().out)["python"] == "true"
    assert repo.run("change-scope") == 2
    assert repo.run("change-scope", "--base-ref", "no-such-ref") == 2
    assert scope_for([])["scope"] == "full"
    assert classify("tools/run.sh") == "other"
    capsys.readouterr()
    repo.commit({".config/pre-commit.yaml": "repos: [\n"}, "broken config")
    head = repo.git("rev-parse", "HEAD").strip()
    repo.commit({"specs/y/requirements.md": "# y\n"}, "spec")
    assert repo.run("change-scope", "--base-ref", head, "--config", ".config/pre-commit.yaml") == 2
