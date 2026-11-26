"""PIPE-PAGES-R021.67-.71: total solution size, measured only against adequate candidates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import run_gate
from pipelines_hooks.code import solution_size as size
from pipelines_hooks.core.errors import CannotRun


def snapshot(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


BASE = {
    "src/__init__.py": "",
    "src/a.py": "def a():\n    return 1\n\n\ndef unchanged():\n    return 0\n",
    "src/b.py": "VALUE = 1\n",
}
SMALL = {**BASE, "src/a.py": "def a():\n    return 1\n"}


def receipts(path: Path, *evidence: tuple[str, str]) -> Path:
    path.write_text(
        json.dumps({"receipts": [{"id": f"r{i}", "snapshot": s, "behavior": b} for i, (s, b) in enumerate(evidence)]})
    )
    return path


def measured(tmp_path: Path):  # type: ignore[no-untyped-def]
    base = size.measure(snapshot(tmp_path / "base", BASE), ("src",))
    cand = size.measure(snapshot(tmp_path / "cand", SMALL), ("src",))
    return base, cand


# spec: PIPE-PAGES-R021.67
def test_model_records_total_size_separately_from_changed_lines(tmp_path: Path) -> None:
    base = size.measure(snapshot(tmp_path / "base", BASE), ("src",), changed_lines=2)
    assert (base.total_bytes, base.nonblank_lines) == (sum(len(t) for t in BASE.values()), 5)
    assert base.syntax_nodes["python-ast/v1"] > 0 and base.adapter_versions == {".py": "python-ast/v1"}
    assert base.changed_lines == 2 and base.changed_lines != base.nonblank_lines
    assert len(base.snapshot_digest) == 64 and "src/b.py" in base.files


# spec: PIPE-PAGES-R021.68
def test_unchanged_source_is_measured_and_exclusions_need_a_producer(tmp_path: Path) -> None:
    base, cand = measured(tmp_path)
    assert cand.total_bytes < base.total_bytes and "src/b.py" in cand.files  # unchanged modules count
    gen = snapshot(tmp_path / "gen", {**BASE, "src/gen.py": "X = 1\n"})
    ok = size.measure(gen, ("src",), ({"path": "src/gen.py", "category": "generated", "producer": "codegen"},))
    assert "src/gen.py" not in ok.files
    with pytest.raises(CannotRun, match="producer"):
        size.measure(gen, ("src",), ({"path": "src/gen.py", "category": "generated", "producer": ""},))
    assert size.compare(
        base,
        cand,
        {
            "receipts": [
                {"id": "a", "snapshot": base.snapshot_digest, "behavior": "pass"},
                {"id": "b", "snapshot": cand.snapshot_digest, "behavior": "pass"},
            ]
        },
    )["eligible"]


# spec: PIPE-PAGES-R021.70
def test_refusals_keep_comparison_unavailable(tmp_path: Path) -> None:
    base, cand = measured(tmp_path)
    with pytest.raises(CannotRun, match="no adequacy receipts"):
        size.compare(base, cand, {})
    with pytest.raises(CannotRun, match="no adequacy receipt for snapshot"):
        size.compare(base, cand, {"receipts": [{"id": "a", "snapshot": base.snapshot_digest, "behavior": "pass"}]})
    other = size.measure(snapshot(tmp_path / "wide", {**BASE, "lib/x.py": "X = 1\n"}), ("src", "lib"))
    with pytest.raises(CannotRun, match="different scopes"):
        size.compare(base, other, {"receipts": []})
    rust = snapshot(tmp_path / "rust", {"src/x.rs": "fn main() {}\n"})
    with pytest.raises(CannotRun, match="no syntax adapter"):
        size.measure(rust, ("src",))
    failing = size.compare(
        base,
        cand,
        {
            "receipts": [
                {"id": "a", "snapshot": base.snapshot_digest, "behavior": "pass"},
                {"id": "b", "snapshot": cand.snapshot_digest, "behavior": "fail"},
            ]
        },
    )
    assert failing["eligible"] is False and failing["delta"]["total_bytes"] < 0  # type: ignore[index]


# spec: PIPE-PAGES-R021.71
def test_evidence_reports_absolute_delta_exclusions_and_open_policy(tmp_path: Path) -> None:
    base, cand = measured(tmp_path)
    out = size.compare(
        base,
        cand,
        {
            "receipts": [
                {"id": "ra", "snapshot": base.snapshot_digest, "behavior": "pass"},
                {"id": "rb", "snapshot": cand.snapshot_digest, "behavior": "pass"},
            ]
        },
        decision="decision-9",
    )
    assert out["adequacy_receipts"] == ["ra", "rb"] and out["owner_decision"] == "decision-9"
    assert out["baseline"]["adapter_versions"] == {".py": "python-ast/v1"}  # type: ignore[index]
    assert "unresolved" in str(out["shortcut_comment_policy"]) and out["delta"]["nonblank_lines"] == -2  # type: ignore[index]
    rec = receipts(tmp_path / "rec.json", (base.snapshot_digest, "pass"), (cand.snapshot_digest, "fail"))
    args = [
        "--size-baseline",
        str(tmp_path / "base"),
        "--size-candidate",
        str(tmp_path / "cand"),
        "--size-scope",
        "src",
    ]
    assert (
        run_gate("repository-validation", [*args, "--adequacy", str(rec), "--size-report", str(tmp_path / "out.json")])
        == 1
    )
    assert json.loads((tmp_path / "out.json").read_text())["eligible"] is False
    rec = receipts(tmp_path / "rec.json", (base.snapshot_digest, "pass"), (cand.snapshot_digest, "pass"))
    assert run_gate("repository-validation", [*args, "--adequacy", str(rec)]) == 0
    assert run_gate("repository-validation", args) == 2


# spec: PIPE-PAGES-R021.69
def test_measurement_is_published_with_the_identities_a_run_receipt_preserves(tmp_path: Path) -> None:
    base, cand = measured(tmp_path)
    rec = receipts(tmp_path / "rec.json", (base.snapshot_digest, "pass"), (cand.snapshot_digest, "pass"))
    args = [
        "--size-baseline",
        str(tmp_path / "base"),
        "--size-candidate",
        str(tmp_path / "cand"),
        "--size-scope",
        "src",
    ]
    consumer = tmp_path / "allocation"
    assert run_gate("repository-validation", [*args, "--adequacy", str(rec), "--size-publish", str(consumer)]) == 0
    (published,) = consumer.glob("*.json")
    record = json.loads(published.read_text())
    assert record["decision"] == size.ALLOCATION_DECISION == "MEDULLA-DECISION-ENGINE-R136.4"
    assert record["source"] == {"baseline": base.snapshot_digest, "candidate": cand.snapshot_digest}
    assert record["counts"]["nonblank_lines"] == cand.nonblank_lines
    result = size.compare(base, cand, json.loads(rec.read_text()))
    assert record == json.loads(
        json.dumps(size.allocation_record(result))
    )  # a run receipt rebuilds the same identities
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the consumer directory belongs")
    assert run_gate("repository-validation", [*args, "--adequacy", str(rec), "--size-publish", str(blocked)]) == 2


# spec: PIPE-PAGES-R021.72
def test_cli_measures_two_snapshots_and_refuses_changed_lines_alone(tmp_path: Path) -> None:
    base, cand = measured(tmp_path)
    args = [
        "--size-baseline",
        str(tmp_path / "base"),
        "--size-candidate",
        str(tmp_path / "cand"),
        "--size-scope",
        "src",
    ]
    failing = receipts(tmp_path / "fail.json", (base.snapshot_digest, "pass"), (cand.snapshot_digest, "fail"))
    assert run_gate("repository-validation", [*args, "--adequacy", str(failing)]) == 1  # smaller but not adequate
    passing = receipts(tmp_path / "pass.json", (base.snapshot_digest, "pass"), (cand.snapshot_digest, "pass"))
    out_a, out_b = tmp_path / "a.json", tmp_path / "b.json"
    for out in (out_a, out_b):
        assert run_gate("repository-validation", [*args, "--adequacy", str(passing), "--size-report", str(out)]) == 0
    assert out_a.read_text() == out_b.read_text()  # exact, reproducible counts
    report = json.loads(out_a.read_text())
    assert report["baseline"]["files"] == ["src/__init__.py", "src/a.py", "src/b.py"]  # unchanged modules are counted
    assert report["delta"]["nonblank_lines"] == -2
    assert run_gate("repository-validation", ["--changed-lines", "3"]) == 2  # changed lines alone fail the contract
