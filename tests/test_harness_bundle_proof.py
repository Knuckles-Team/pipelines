"""The release proof of declared coding harness bundles (PIPE-RELEASE-R028.1, R028.3, R028.4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from scripts import harness_bundle_proof as proof  # noqa: E402

STUB = ROOT / "tests/fixtures/harness_bundles/stub_bundle.py"
WORKFLOW = ROOT / ".github/workflows/python_pipeline.yml"


def _repo(path: Path, catalog: dict | None = None, validator: str = "") -> Path:
    declared = f'''[project]
name = "fixture"
version = "1.2.3"

[tool.pipelines.harness_bundles]
command = "{sys.executable} {STUB}"
output = "harness-bundles"
'''
    if catalog is not None:
        (path / "catalog.json").write_text(json.dumps(catalog))
        declared += 'catalog = "catalog.json"\n'
    declared += '\n[tool.pipelines.harness_bundles.profiles.claude]\nstructural = ["plugin.json"]\n'
    if validator:
        declared += f'validator = "{validator}"\n'
    declared += '\n[tool.pipelines.harness_bundles.profiles.codex]\nstructural = ["plugin.json"]\n'
    (path / "pyproject.toml").write_text(declared)
    return path


# spec: PIPE-RELEASE-R028.1
def test_each_declared_profile_is_built_validated_and_deleted(tmp_path: Path, monkeypatch, capsys) -> None:
    root = _repo(tmp_path)
    created: list[Path] = []
    real = proof.tempfile.TemporaryDirectory

    class Tracking(real):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            created.append(Path(self.name))

    monkeypatch.setattr(proof.tempfile, "TemporaryDirectory", Tracking)
    assert proof.main(["--root", str(root)]) == 0
    assert len(created) == 2 and not any(p.exists() for p in created)
    # A failing validator on the runner fails the release; a missing structural file does too.
    monkeypatch.undo()
    (tmp_path / "v").mkdir()
    failing = _repo(tmp_path / "v", validator=f"{sys.executable} -c 'raise SystemExit(3)'")
    assert proof.main(["--root", str(failing)]) == 1
    assert "validator exited 3" in capsys.readouterr().err
    decl = proof.load_declaration(root)
    bad = proof.prove("claude", {"structural": ["missing.json"]}, decl["command"], root)
    assert bad == ["claude: missing missing.json"]


# spec: PIPE-RELEASE-R028.3
def test_catalog_entries_must_be_command_or_pinned_package_sources(tmp_path: Path) -> None:
    command = f"{sys.executable} {STUB}"
    good = {
        "entries": [
            {"name": "a", "source": {"type": "command", "command": command + " --harness claude"}},
            {"name": "b", "source": {"type": "package", "package": "fixture", "version": "1.2.3"}},
        ]
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(good))
    assert proof.check_catalog(path, "1.2.3", command) == []
    bad = {
        "entries": [
            {"name": "rel", "source": "./plugins/x"},
            {"name": "tree", "source": {"type": "path", "path": "bundle/"}},
            {"name": "old", "source": {"type": "package", "package": "fixture", "version": "1.0.0"}},
            {"name": "cmd", "source": {"type": "command", "command": "other-tool"}},
        ]
    }
    path.write_text(json.dumps(bad))
    problems = proof.check_catalog(path, "1.2.3", command)
    assert len(problems) == 4 and all(p.startswith("CATALOG_SOURCE_INVALID") for p in problems)


# spec: PIPE-RELEASE-R028.4
def test_release_job_runs_the_proof_before_publish(tmp_path: Path, monkeypatch, capsys) -> None:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = document["jobs"]
    assert "harness-bundles" in jobs["publish-pypi"]["needs"]
    step = next(s for s in jobs["harness-bundles"]["steps"] if "harness_bundle_proof.py" in s.get("run", ""))
    assert "--root" in step["run"] or "harness_bundle_proof.py" in step["run"]
    root = _repo(tmp_path, catalog={"entries": [{"name": "a", "source": "./x"}]})
    assert proof.main(["--root", str(root)]) == 1  # a relative catalog source fails the release
    assert "CATALOG_SOURCE_INVALID" in capsys.readouterr().err
    root = _repo(tmp_path, catalog={"entries": []})
    assert proof.main(["--root", str(root)]) == 0
    monkeypatch.setenv("STUB_WRITE_TOKEN", "1")
    assert proof.main(["--root", str(root)]) == 1
    assert "credential in" in capsys.readouterr().err
