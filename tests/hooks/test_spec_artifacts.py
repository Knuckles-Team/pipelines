"""PIPE-PAGES-R020.73 to R020.78: generator-skill artifacts validate and render the standard spec files."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipelines_hooks.cli import GATES
from pipelines_hooks.specs import artifact_schema as schema
from pipelines_hooks.specs import generator
from tests.hooks.conftest import Repo

SRC = [{"path": "skills/spec/SKILL.md", "line": 3}]
DOC = {
    "schema_version": 1,
    "spec_id": "DEMO-ART",
    "stories": [
        {
            "id": "US1",
            "owner": "pipelines",
            "sources": SRC,
            "requirements": ["DEMO-ART-R001"],
            "actor": "a maintainer",
            "goal": "a checked spec",
            "benefit": "rows stay consistent",
        },
    ],
    "criteria": [
        {
            "id": "AC1",
            "owner": "pipelines",
            "sources": SRC,
            "requirements": ["DEMO-ART-R001"],
            "story": "US1",
            "predicates": ["the schema accepts the document"],
            "proofs": ["tests/test_demo.py::test_ok"],
        },
    ],
    "tasks": [
        {
            "id": "TK1",
            "owner": "pipelines",
            "sources": SRC,
            "requirements": ["DEMO-ART-R001"],
            "criteria": ["AC1"],
            "targets": ["pkg/demo.py"],
            "proofs": ["tests/test_demo.py::test_ok"],
        },
        {
            "id": "TK2",
            "owner": "pipelines",
            "sources": SRC,
            "requirements": ["DEMO-ART-R001"],
            "prerequisites": ["TK1"],
            "criteria": ["AC1"],
            "targets": ["pkg/more.py"],
            "proofs": ["tests/test_demo.py::test_ok"],
        },
    ],
}


def _doc(**change: object) -> dict[str, object]:
    return {**copy.deepcopy(DOC), **change}


def _repo(tmp_path: Path, document: dict[str, object] | None = None) -> Repo:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    repo.commit({"artifacts.json": json.dumps(document or DOC), "README.md": "# demo\n"})
    return repo


# spec: PIPE-PAGES-R020.73
def test_spec_artifacts_model() -> None:
    doc = schema.ArtifactDocument.model_validate(DOC)
    assert doc.stories[0].actor == "a maintainer" and doc.tasks[1].prerequisites == ("TK1",)
    assert doc.criteria[0].proofs and doc.tasks[0].targets == ("pkg/demo.py",)
    with pytest.raises(ValidationError):
        schema.ArtifactDocument.model_validate({**DOC, "extra": 1})
    with pytest.raises(ValidationError):
        schema.UserStory.model_validate({**DOC["stories"][0], "rank": 1})  # type: ignore[index]
    with pytest.raises(ValidationError):
        schema.ArtifactDocument.model_validate(_doc(schema_version=2))
    bad = copy.deepcopy(DOC)
    bad["stories"][0]["requirements"] = ["not-an-id"]  # type: ignore[index]
    with pytest.raises(ValidationError):
        schema.ArtifactDocument.model_validate(bad)
    bad = copy.deepcopy(DOC)
    bad["tasks"][0]["targets"] = ["../escape.py"]  # type: ignore[index]
    with pytest.raises(ValidationError):
        schema.ArtifactDocument.model_validate(bad)


# spec: PIPE-PAGES-R020.74
def test_spec_artifacts_behavior() -> None:
    doc = schema.ArtifactDocument.model_validate(DOC)
    files = schema.render(doc)
    assert tuple(files) == schema.OUTPUT_FILES and files == schema.render(doc)
    assert (
        "| `DEMO-ART-R001` | the schema accepts the document | Run `tests/test_demo.py::test_ok`. |"
        in files["requirements.md"]
    )
    assert "- [ ] T002 DEMO-ART-R001 TK2: pkg/more.py after TK1" in files["tasks.md"]
    assert "As a maintainer, I want a checked spec so that rows stay consistent." in files["spec.md"]
    again = schema.ArtifactDocument.model_validate(json.loads(json.dumps(doc.model_dump(mode="json"))))
    assert again == doc and again.tasks[0].sources[0].line == 3


# spec: PIPE-PAGES-R020.75
def test_spec_artifacts_wiring(tmp_path: Path) -> None:
    assert GATES["spec-artifact-schema"] == "pipelines_hooks.specs.artifact_schema"
    assert GATES["spec-artifacts"] == "pipelines_hooks.specs.spec_bundle"  # the R012 gate keeps its own id
    hooks = (Path(__file__).resolve().parents[2] / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    assert "entry: pipelines-hook spec-artifact-schema" in hooks
    repo = _repo(tmp_path)
    assert repo.run("spec-artifact-schema", "--input", "artifacts.json", "--output", "specs/demo") == 0
    assert (repo.root / "specs/demo/requirements.md").is_file()


# spec: PIPE-PAGES-R020.76
def test_spec_artifacts_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cases: dict[str, dict[str, object]] = {"schema": _doc(schema_version=9), "extra": {**_doc(), "unknown": 1}}
    dup = copy.deepcopy(DOC)
    dup["tasks"][1]["id"] = "TK1"  # type: ignore[index]
    cases["duplicate"] = dup
    missing = copy.deepcopy(DOC)
    missing["criteria"][0]["story"] = "US9"  # type: ignore[index]
    cases["missing"] = missing
    for index, (label, document) in enumerate(cases.items()):
        repo = _repo(tmp_path / f"c{index}", document)
        assert repo.run("spec-artifact-schema", "--input", "artifacts.json", "--output", "specs/demo") == 1, label
        assert not (repo.root / "specs").exists()
    repo = _repo(tmp_path / "ok")
    assert repo.run("spec-artifact-schema", "--input", "artifacts.json", "--output", "../outside") == 2
    assert repo.run("spec-artifact-schema", "--input", "absent.json") == 2
    assert repo.run("spec-artifact-schema", "--input", "artifacts.json", "--output", "specs/demo") == 0
    (repo.root / "specs/demo/spec.md").write_text("mine\n", encoding="utf-8")
    assert repo.run("spec-artifact-schema", "--input", "artifacts.json", "--output", "specs/demo") == 2
    assert (repo.root / "specs/demo/spec.md").read_text(encoding="utf-8") == "mine\n"
    capsys.readouterr()


# spec: PIPE-PAGES-R020.77
def test_spec_artifacts_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert repo.run("spec-artifact-schema", "--input", "artifacts.json") == 0
    out = capsys.readouterr().out
    assert "schema_version=1" in out and f"schema={schema.schema_digest()}" in out and "source=" in out
    assert "artifacts: US1 AC1 TK1 TK2" in out and "prerequisites=acyclic" in out
    assert out.count("output ") == 6 and "digest=" in out
    assert "schema compatibility only; no implemented behaviour, graph ingestion or runtime acceptance" in out
    assert not (repo.root / "specs").exists()


# spec: PIPE-PAGES-R020.78
def test_spec_artifacts_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert repo.run("spec-artifact-schema", "--input", "artifacts.json", "--output", "specs/demo") == 0
    written = {p: (repo.root / "specs/demo" / p).read_text(encoding="utf-8") for p in schema.OUTPUT_FILES}
    assert written == schema.render(schema.ArtifactDocument.model_validate(DOC))
    repo.commit({f"specs/demo/{name}": text for name, text in written.items()}, "render")
    computed = generator.computed(repo.root)
    ids = [rid for status in computed.values() for rid in status["requirement_ids"]]
    assert "DEMO-ART-R001" in ids
    unknown = _doc()
    unknown["tasks"][0]["colour"] = "red"  # type: ignore[index]
    cyclic = copy.deepcopy(DOC)
    cyclic["tasks"][0]["prerequisites"] = ["TK2"]  # type: ignore[index]
    dangling = copy.deepcopy(DOC)
    dangling["tasks"][0]["criteria"] = ["AC9"]  # type: ignore[index]
    for index, document in enumerate((unknown, cyclic, dangling)):
        other = _repo(tmp_path / f"bad{index}", document)
        assert other.run("spec-artifact-schema", "--input", "artifacts.json", "--output", "specs/demo") == 1
        assert not (other.root / "specs").exists()
    capsys.readouterr()
