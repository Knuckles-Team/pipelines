"""PIPE-PAGES-R020.79 to R020.84: the pinned former validation command's behaviors are all mapped to hooks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.hygiene import config_inventory as ci
from pipelines_hooks.hygiene import config_inventory_behavior as cb
from tests.hooks.conftest import Repo
from tests.hooks.test_config_inventory import DECLARATION, _inventory

BASELINE = ".config/validation-baseline.json"
REVISION = "a" * 40
POLICY = f'''
[validation]
baseline = "{BASELINE}"
repository = "former-central"
revision = "{REVISION}"
entry_point = "central-validate"
'''
LAYOUT = '[dirs]\n".config" = "configuration"\n\n[files]\n"README.md" = "readme"\n'
POSITIVE = {".config/repo-layout.toml": LAYOUT, "README.md": "# fixture\n"}
NEGATIVE = {**POSITIVE, ".kissconfig": "calibrated\n"}


def behavior(bid: str = "root-layout", **over: object) -> dict:
    entry = {
        "id": bid,
        "kind": "validation",
        "inputs": ["tracked root entries"],
        "env": [],
        "expected_exit": 1,
        "mapping": {"hook": "root-hygiene", "gate": "root-hygiene"},
        "positive": {"path": f"fixtures/{bid}/positive", "digest": "", "exit": 0},
        "negative": {"path": f"fixtures/{bid}/negative", "digest": "", "exit": 1},
    }
    return entry | over


def build(tmp_path: Path, behaviors: list[dict] | None = None, *, declaration: str = DECLARATION + POLICY,
          revision: str = REVISION, unsupported: list[str] | None = None, with_baseline: bool = True,
          drop_hook: bool = False) -> Repo:  # fmt: skip
    repo = Repo(tmp_path / "repo")
    repo.root.mkdir(parents=True)
    repo.git("init", "-q")
    scratch = tmp_path / "scratch"
    ci.render(_inventory(), scratch)
    files = {str(p.relative_to(scratch)): p.read_text(encoding="utf-8") for p in scratch.rglob("*") if p.is_file()}
    if drop_hook:
        files["svc/.pre-commit-config.yaml"] = files["svc/.pre-commit-config.yaml"].replace(
            "root-hygiene", "other-hook"
        )
    repo.stage({ci.DECLARATION: declaration, **files})
    behaviors = behaviors if behaviors is not None else [behavior()]
    for entry in behaviors:
        for label, tree in (("positive", POSITIVE), ("negative", NEGATIVE)):
            if label in entry:
                repo.stage({f"{entry[label]['path']}/{rel}": text for rel, text in tree.items()})
                entry[label]["digest"] = cb._tree_digest(repo.root, entry[label]["path"])[0]
    if with_baseline:
        baseline = {
            "format": cb.FORMAT,
            "command": {"repository": "former-central", "revision": revision, "entry_point": "central-validate"},
            "behaviors": behaviors,
            "unknown_scope": ["behaviors of the former command not recoverable from the pinned revision"],
            "unsupported_environments": unsupported or [],
        }
        repo.stage({BASELINE: json.dumps(baseline)})
    return repo


# spec: PIPE-PAGES-R020.79
def test_validation_behavior_inventory_model(tmp_path: Path) -> None:
    repo = build(tmp_path)
    inventory = ci.load_inventory(repo.root)
    assert inventory.validation == cb.ValidationPolicy(BASELINE, "former-central", REVISION, "central-validate")
    manifest = cb.load_manifest(repo.root, inventory.validation)
    (item,) = manifest.behaviors
    assert (item.id, item.kind, item.hook, item.gate, item.expected_exit) == (
        "root-layout",
        "validation",
        "root-hygiene",
        "root-hygiene",
        1,
    )
    assert item.inputs == ("tracked root entries",) and manifest.unknown_scope
    with pytest.raises(CannotRun, match="40-hex"):
        cb.parse_policy({"baseline": BASELINE, "repository": "r", "revision": "main", "entry_point": "e"})
    with pytest.raises(CannotRun, match="exactly"):
        cb.parse_policy({"baseline": BASELINE})
    with pytest.raises(CannotRun, match="repeats an id"):
        cb.load_manifest(build(tmp_path / "d", [behavior(), behavior()]).root, inventory.validation)


# spec: PIPE-PAGES-R020.80
def test_validation_behavior_inventory_behavior(tmp_path: Path) -> None:
    repo = build(tmp_path / "ok")
    inventory = ci.load_inventory(repo.root)
    findings, _ = ci.check(repo.root, inventory)
    assert findings == []
    unmapped = behavior("unmapped", mapping={})
    retired = behavior("retired", mapping={}, retired={"decision": "owner-decision-17"})
    repo = build(tmp_path / "gap", [behavior(), unmapped, retired])
    findings, _ = ci.check(repo.root, ci.load_inventory(repo.root))
    assert any("behavior unmapped: no mapped hook and no owner retirement decision" in f for f in findings)
    assert not any("retired" in f for f in findings)
    assert "behavior id=retired state=retired decision=owner-decision-17" in "\n".join(ci._BEHAVIOR_LINES)
    missing = build(tmp_path / "nohook", drop_hook=True)
    findings, _ = ci.check(missing.root, ci.load_inventory(missing.root))
    assert any("svc/.pre-commit-config.yaml: project 'svc' configures no hook root-hygiene" in f for f in findings)
    changed = behavior(negative={"path": "fixtures/root-layout/negative", "digest": "", "exit": 3})
    repo = build(tmp_path / "exit", [changed])
    findings, _ = ci.check(repo.root, ci.load_inventory(repo.root))
    assert any("negative fixture observed exit 1, pinned 3" in f for f in findings)


# spec: PIPE-PAGES-R020.81
def test_validation_behavior_inventory_wiring(tmp_path: Path) -> None:
    assert GATES["config-inventory"] == "pipelines_hooks.hygiene.config_inventory"
    root = Path(__file__).resolve().parents[2]
    hooks = (root / ".pre-commit-hooks.yaml").read_text()
    assert "entry: pipelines-hook config-inventory --check" in hooks
    repo = build(tmp_path)
    assert repo.run("config-inventory", "--check") == 0 == repo.run("config-inventory", "--scope", "validation")
    # spec-hook adoption alone does not establish validation coverage
    bare = build(tmp_path / "bare", declaration=DECLARATION)
    assert bare.run("config-inventory", "--scope", "validation") == 2


# spec: PIPE-PAGES-R020.82
def test_validation_behavior_inventory_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert build(tmp_path / "nobase", with_baseline=False).run("config-inventory") == 2
    assert build(tmp_path / "rev", revision="b" * 40).run("config-inventory") == 2
    assert build(tmp_path / "env", unsupported=["legacy-interpreter"]).run("config-inventory") == 2
    stale = build(tmp_path / "stale")
    stale.stage({"fixtures/root-layout/positive/README.md": "# changed\n"})
    assert stale.run("config-inventory") == 2
    assert (
        build(tmp_path / "pin", declaration=DECLARATION + POLICY.replace(REVISION, "short")).run("config-inventory")
        == 2
    )
    capsys.readouterr()
    assert build(tmp_path / "map", drop_hook=True).run("config-inventory") == 1
    assert (
        build(
            tmp_path / "chg", [behavior(negative={"path": "fixtures/root-layout/negative", "digest": "", "exit": 3})]
        ).run("config-inventory")
        == 1
    )


# spec: PIPE-PAGES-R020.83
def test_validation_behavior_inventory_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path)
    assert repo.run("config-inventory") == 0
    out = capsys.readouterr().out
    assert f"baseline repository=former-central revision={REVISION} entry-point=central-validate" in out
    assert (
        "behaviors=['root-layout']" in out and "unknown-scope ['behaviors of the former command not recoverable" in out
    )
    line = next(ln for ln in out.splitlines() if ln.startswith("behavior id=root-layout"))
    assert "kind=validation state=mapped hook=root-hygiene projects=['.', 'svc']" in line
    assert (
        "positive:fixture=" in line
        and "exit=0 want=0 output=" in line
        and "negative:fixture=" in line
        and "exit=1 want=1" in line
    )
    assert str(tmp_path) not in out


# spec: PIPE-PAGES-R020.84
def test_validation_behavior_inventory_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path / "good")
    assert repo.run("config-inventory", "--check") == 0
    # removing one behavior mapping from a project fails
    gone = build(tmp_path / "gone", drop_hook=True)
    assert gone.run("config-inventory", "--check") == 1
    assert "configures no hook root-hygiene" in capsys.readouterr().out
    # a planted changed failure exit fails
    planted = build(tmp_path / "planted", [behavior(expected_exit=2)])
    assert planted.run("config-inventory", "--check") == 1
    # an unavailable baseline refuses and never prints a complete-migration receipt
    capsys.readouterr()
    unavailable = build(tmp_path / "unavailable", with_baseline=False)
    assert unavailable.run("config-inventory", "--check") == 2
    captured = capsys.readouterr()
    assert "state=mapped" not in captured.out + captured.err and "migration unproved" in captured.err
