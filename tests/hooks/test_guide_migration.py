"""PIPE-PAGES-R020.43 to R020.48: a split guide accounts for every source block."""

from __future__ import annotations

import copy
import json
import posixpath
import re
from pathlib import Path

import pytest

from pipelines_hooks.docs import claims
from pipelines_hooks.docs import guide_migration as gm
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import Repo
from tests.hooks.docs_support import fetch, serve

OLD = """# Guide

Intro paragraph that stays.

## Commands

Use `src/tool.py` to run things.

```bash
tool --help
```

```mermaid
graph TD
  A[Start] --> B[End]
```

Legacy note that is retired.
"""
PLAN = {
    "b001": {"disposition": "retained"},
    "b002": {"disposition": "retained"},
    "b003": {"disposition": "retained"},
    "b004": {
        "disposition": "moved",
        "dest": "pages/commands.md",
        "anchor": "commands",
        "claims": [{"id": "b004.c1", "kind": "path", "text": "src/tool.py"}],
    },
    "b005": {"disposition": "moved", "dest": "pages/commands.md", "anchor": "commands"},
    "b006": {"disposition": "moved", "dest": "pages/architecture.md", "anchor": "diagram"},
    "b007": {"disposition": "retired", "review": "obsolete after the 2026 rewrite"},
}


def manifest_for(old: str = OLD, plan: dict | None = None, limit: int = 900) -> dict:
    blocks = []
    for block in gm.split_blocks(old):
        entry = (
            copy.deepcopy((plan or PLAN)[block.id])
            if block.id in (plan or PLAN)
            else {"disposition": "retired", "review": "r"}
        )
        blocks.append({"id": block.id, "digest": block.digest, **entry})
    return {
        "schema": 1,
        "old": "migration/old-guide.md",
        "guide": "docs/guide.md",
        "size_limit": limit,
        "blocks": blocks,
    }


def build(tmp_path: Path, *, old: str = OLD, plan: dict | None = None, limit: int = 900, land: bool = True) -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.root.mkdir(parents=True)
    repo.git("init", "-q")
    repo.stage(
        {
            "migration/old-guide.md": old,
            "src/tool.py": "print('x')\n",
            gm.DECLARATION: json.dumps(manifest_for(old, plan, limit)),
        }
    )
    if land:
        out = tmp_path / "scratch"
        assert repo.run("guide-migration", "--render", str(out)) == 0
        repo.stage({str(p.relative_to(out)): p.read_text() for p in out.rglob("*") if p.is_file()})
    return repo


def edit(repo: Repo, rel: str, old: str, new: str) -> None:
    repo.stage({rel: (repo.root / rel).read_text().replace(old, new)})


# spec: PIPE-PAGES-R020.43
def test_guide_migration_model(tmp_path: Path) -> None:
    blocks = gm.split_blocks(OLD)
    assert [(b.id, b.kind) for b in blocks] == [
        ("b001", "prose"),
        ("b002", "prose"),
        ("b003", "prose"),
        ("b004", "prose"),
        ("b005", "code"),
        ("b006", "diagram"),
        ("b007", "prose"),
    ]
    assert len({b.digest for b in blocks}) == 7
    repo = build(tmp_path)
    manifest = gm.load_manifest(repo.root)
    moved = [r for r in manifest.records if r.disposition == "moved"]
    assert (manifest.old, manifest.guide, manifest.size_limit, len(manifest.records)) == (
        "migration/old-guide.md",
        "docs/guide.md",
        900,
        7,
    )
    assert moved[0].dest == "pages/commands.md" and moved[0].claims[0].kind == "path"
    for bad in (
        {"blocks": manifest_for()["blocks"] + [dict(manifest_for()["blocks"][0])]},
        {"blocks": [{"id": "b001", "digest": "x", "disposition": "vanished"}]},
        {
            "blocks": [
                {
                    "id": "b001",
                    "digest": "x",
                    "disposition": "moved",
                    "claims": [{"id": "c", "kind": "vibes", "text": "t"}],
                }
            ]
        },
    ):
        repo.stage({gm.DECLARATION: json.dumps(manifest_for() | bad)})
        with pytest.raises(CannotRun):
            gm.load_manifest(repo.root)


# spec: PIPE-PAGES-R020.44
def test_guide_migration_behavior(tmp_path: Path) -> None:
    repo = build(tmp_path)
    result, unverified = gm.check(repo.root)
    assert result.findings == [] and unverified == []
    guide = (repo.root / "docs/guide.md").read_text()
    assert "[pages/commands.md](../pages/commands.md)" in guide and "tool --help" not in guide
    assert "tool --help" in (repo.root / "pages/commands.md").read_text()
    assert gm.RESOLVERS is claims.RESOLVERS or gm.RESOLVERS == claims.RESOLVERS
    # an omitted block, a silent deletion and a changed claim each fail independently
    cases = {
        "omitted": lambda r: r.stage({gm.DECLARATION: json.dumps(_without(manifest_for(), "b007"))}),
        "deleted": lambda r: edit(r, "pages/commands.md", "tool --help", "tool --other"),
        "changed": lambda r: edit(r, "migration/old-guide.md", "src/tool.py", "src/gone.py"),
        "unreviewed": lambda r: r.stage({gm.DECLARATION: json.dumps(_retire_without_review())}),
        "retained-lost": lambda r: edit(r, "docs/guide.md", "Intro paragraph that stays.", "Different."),
    }
    for name, mutate in cases.items():
        broken = build(tmp_path / name)
        mutate(broken)
        assert gm.check(broken.root)[0].findings, name


def _without(manifest: dict, block_id: str) -> dict:
    return manifest | {"blocks": [b for b in manifest["blocks"] if b["id"] != block_id]}


def _retire_without_review() -> dict:
    m = manifest_for()
    m["blocks"][-1].pop("review")
    return m


# spec: PIPE-PAGES-R020.45
def test_guide_migration_wiring(tmp_path: Path) -> None:
    from pipelines_hooks.cli import GATES, run_gate

    assert GATES["guide-migration"] == "pipelines_hooks.docs.guide_migration"
    root = Path(__file__).resolve().parents[2]
    assert "entry: pipelines-hook guide-migration --check" in (root / ".pre-commit-hooks.yaml").read_text()
    workflow = (root / ".github/workflows/pages_pipeline.yml").read_text()
    assert workflow.index("docs.guide_migration") < workflow.index("Upload artifact")
    assert gm.RESOLVERS is claims.RESOLVERS
    repo = build(tmp_path)
    assert run_gate("guide-migration", ["--root", str(repo.root), "--check"]) == 0 == repo.run("guide-migration")
    scratch = tmp_path / "other"
    assert repo.run("guide-migration", "--render", str(scratch)) == 0 and (scratch / "docs/guide.md").is_file()


# spec: PIPE-PAGES-R020.46
def test_guide_migration_refusal(tmp_path: Path) -> None:
    repo = build(tmp_path)
    before = (repo.root / "docs/guide.md").read_bytes()
    assert repo.run("guide-migration") == 0 and (repo.root / "docs/guide.md").read_bytes() == before
    assert repo.run("guide-migration", "--render", str(tmp_path / "scratch")) == 2  # refuses overwrite
    assert build(tmp_path / "small", limit=50).run("guide-migration") == 1  # oversized
    broken = build(tmp_path / "link")
    edit(broken, "docs/guide.md", "../pages/architecture.md", "../pages/missing.md")
    assert broken.run("guide-migration") == 1
    bad_diagram = OLD.replace("A[Start] --> B[End]", "A[Start, here] --> B[End]")
    assert build(tmp_path / "diagram", old=bad_diagram).run("guide-migration") == 1
    unavailable = build(tmp_path / "unavailable")
    unavailable.git("rm", "-q", "--cached", "migration/old-guide.md")
    assert unavailable.run("guide-migration") == 2
    unsupported = manifest_for()
    unsupported["blocks"][3]["claims"][0]["kind"] = "vibes"
    stale = build(tmp_path / "kind")
    stale.stage({gm.DECLARATION: json.dumps(unsupported)})
    assert stale.run("guide-migration") == 2
    unknown = manifest_for()
    unknown["blocks"][3]["claims"].append({"id": "b004.c2", "kind": "unverified", "text": "It is fast."})
    claimant = build(tmp_path / "unverified")
    claimant.stage({gm.DECLARATION: json.dumps(unknown)})
    assert claimant.run("guide-migration") == 2


# spec: PIPE-PAGES-R020.47
def test_guide_migration_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path)
    capsys.readouterr()
    assert repo.run("guide-migration") == 0
    out = capsys.readouterr().out
    assert re.search(
        r"block id=b004 kind=prose lines=\d+-\d+ digest=\w+ disposition=moved to=pages/commands.md#commands after=\w+",
        out,
    )
    assert "counts blocks=7 retained=3 moved=3 retired=1" in out
    assert re.search(r"size guide=docs/guide.md bytes=\d+ limit=900", out)
    assert "claim id=b004.c1 block=b004 kind=path evidence=measured" in out
    assert "navigation links=['pages/architecture.md', 'pages/commands.md']" in out
    assert "verification complete=yes unverified=0 evidence-kinds=byte-preserved,editorial-review,measured" in out
    unknown = manifest_for()
    unknown["blocks"][3]["claims"].append({"id": "b004.c2", "kind": "unverified", "text": "It is fast."})
    repo.stage({gm.DECLARATION: json.dumps(unknown)})
    assert repo.run("guide-migration") == 2
    again = capsys.readouterr().out
    assert "claim id=b004.c2 block=b004 kind=unverified evidence=unresolved" in again
    assert (
        "verification complete=no unverified=1" in again and "counts blocks=7" in again
    )  # all blocks still accounted for


# spec: PIPE-PAGES-R020.48
def test_guide_migration_cli(tmp_path: Path) -> None:
    repo = build(tmp_path)
    assert repo.run("guide-migration") == 0
    with serve(repo.root) as base:
        guide = fetch(f"{base}/docs/guide.md")
        for target in re.findall(r"\]\(([^)]+)\)", guide):
            assert fetch(f"{base}/{posixpath.normpath(posixpath.join('docs', target))}").strip()
        assert "graph TD" in fetch(f"{base}/pages/architecture.md")
    omitted = build(tmp_path / "o")
    omitted.stage({gm.DECLARATION: json.dumps(_without(manifest_for(), "b005"))})
    assert omitted.run("guide-migration") == 1
    changed = build(tmp_path / "c")
    edit(changed, "pages/commands.md", "Use `src/tool.py`", "Use `src/other.py`")
    assert changed.run("guide-migration") == 1
    diagram = build(tmp_path / "d")
    edit(diagram, "pages/architecture.md", "A[Start] --> B[End]", "A[Start, x] --> B[End]")
    assert diagram.run("guide-migration") == 1
    unknown = build(tmp_path / "u")
    manifest = manifest_for()
    manifest["blocks"][3]["claims"].append({"id": "b004.c2", "kind": "unverified", "text": "It is fast."})
    unknown.stage({gm.DECLARATION: json.dumps(manifest)})
    assert unknown.run("guide-migration") == 2
    unknown.stage({gm.DECLARATION: json.dumps(manifest_for())})
    assert unknown.run("guide-migration") == 0
