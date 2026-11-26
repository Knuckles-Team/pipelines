"""Role closure against the package owner's role export (PIPE-RELEASE-R005.7 to R005.12 are built but left unbound).

The owner export is not published yet (an open dependency on the meristem package-owner export), so the
rows stay unbound: these tests build against the row shape and assert the refusal while the export is absent.
"""

from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.release import role_closure
from pipelines_hooks.release.role_closure import canonical_digest, evaluate, main, parse_export

ROOT = Path(__file__).parents[2]
TARGET = "linux-x86_64"
CONTRACT = {"version": 1, "roles": [{"role": "base", "extra": None}, {"role": "mcp", "extra": "mcp"}]}


def dist(name: str, modules: list[str], platform: str = TARGET) -> dict:
    return {"name": name, "version": "1.0", "platform": platform, "modules": modules}


def make_export(**overrides) -> dict:
    shared = [dist("medulla", ["medulla_pkg"]), dist("shared-dep", ["shared_dep"])]
    body = {
        "targets": [TARGET],
        "roles": [
            {"role": "base", "root": "app", "extras": [], "entry_modules": ["medulla_pkg"], "closure": shared},
            {
                "role": "mcp",
                "root": "app",
                "extras": ["mcp"],
                "entry_modules": ["medulla_pkg"],
                "closure": [*shared, dist("mcp-extra", ["mcp_extra"])],
            },
        ],
    }
    body.update(overrides)
    return {
        "schema": 1,
        "repository": "Knuckles-Team/example",
        "revision": "a" * 40,
        "digest": canonical_digest(body),
        "lock_sha256": hashlib.sha256(b"lock").hexdigest(),
        **body,
    }


def make_wheel(directory: Path, name: str, modules: list[str]) -> None:
    norm = name.replace("-", "_")
    info = f"{norm}-1.0.dist-info"
    with zipfile.ZipFile(directory / f"{norm}-1.0-py3-none-any.whl", "w") as wheel:
        for module in modules:
            wheel.writestr(f"{module}/__init__.py", "")
        wheel.writestr(f"{info}/METADATA", f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n")
        wheel.writestr(
            f"{info}/WHEEL", "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        )
        wheel.writestr(f"{info}/RECORD", "")


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    (tmp_path / "wheels").mkdir()
    (tmp_path / "lock").write_bytes(b"lock")
    (tmp_path / "contract.json").write_text(json.dumps(CONTRACT))
    return tmp_path


def write_export(work: Path, export: dict) -> Path:
    path = work / "export.json"
    path.write_text(json.dumps(export))
    return path


def argv(work: Path) -> list[str]:
    return [
        "--export", str(work / "export.json"), "--contract", str(work / "contract.json"),
        "--wheel-dir", str(work / "wheels"), "--lock", str(work / "lock"),
    ]  # fmt: skip


def installing_prober(importable: dict[str, set[str]]):
    """A prober whose environment can import exactly the closure it was given plus ``importable``."""

    def probe(role, wheel_dir, closure, imports):
        have = {m for d in closure for m in d.modules} | importable.get(role.role, set())
        return [f"{d.name}==1.0" for d in closure], {m: m in have for m in imports}

    return probe


def test_role_extra_closure_model() -> None:
    manifest = parse_export(make_export())
    assert (manifest.repository, manifest.revision) == ("Knuckles-Team/example", "a" * 40)
    assert [r.role for r in manifest.roles] == ["base", "mcp"]
    mcp = manifest.roles[1]
    assert (mcp.root, mcp.extras, mcp.entry_modules) == ("app", ("mcp",), ("medulla_pkg",))
    assert {d.name for d in mcp.closure} == {"medulla", "shared-dep", "mcp-extra"}
    tampered = make_export()
    tampered["roles"][0]["root"] = "other"
    with pytest.raises(CannotRun, match="export-digest"):
        parse_export(tampered)
    role_closure.check_role_set(manifest, ["base", "mcp"])
    with pytest.raises(CannotRun, match="role-set"):
        role_closure.check_role_set(manifest, ["base", "mcp", "ui"])


def test_role_extra_closure_behavior(workdir: Path) -> None:
    manifest = parse_export(make_export())
    base, mcp = manifest.roles
    required, forbidden, negative = role_closure.import_plan(manifest, base, TARGET)
    assert forbidden == ["mcp_extra"] and negative
    assert "shared_dep" in required
    # A package shared with the unselected role stays allowed for both roles.
    assert "shared_dep" not in role_closure.import_plan(manifest, mcp, TARGET)[1]
    status, report = evaluate(manifest, _wheels(workdir), workdir / "lock", installing_prober({}))
    assert status == 0 and report["status"] == "pass"
    # Real isolated environments from real wheel bytes.
    for name, modules in (("medulla", ["medulla_pkg"]), ("shared-dep", ["shared_dep"]), ("mcp-extra", ["mcp_extra"])):
        make_wheel(workdir / "wheels", name, modules)
    assert main(argv(workdir) if write_export(workdir, make_export()) else []) == 0


def _wheels(work: Path) -> Path:
    make_wheel(work / "wheels", "medulla", ["medulla_pkg"])
    return work / "wheels"


def test_role_extra_closure_wiring() -> None:
    assert GATES["role-closure"] == "pipelines_hooks.release.role_closure"
    hooks = (ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    assert "- id: role-closure" in hooks and "entry: pipelines-hook role-closure" in hooks
    assert callable(role_closure.main)


def test_role_extra_closure_refusal(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _wheels(workdir)
    # The package owner has not published its export: exit 2, never a pass.
    assert main(argv(workdir)) == 2
    assert "owner-export-missing" in capsys.readouterr().err
    write_export(workdir, make_export())
    assert main(argv(workdir), installing_prober({})) == 0
    # A role omitted from the export.
    omitted = make_export(roles=make_export()["roles"][:1])
    write_export(workdir, omitted)
    assert main(argv(workdir), installing_prober({})) == 2
    assert "role-set" in capsys.readouterr().err
    # Incomplete target coverage and an unresolved version.
    for broken, reason in (
        ({"targets": [TARGET, "macos-arm64"]}, "incomplete-targets"),
        ({"roles": _with(lambda r: r[1]["closure"][0].update(version=""))}, "unresolved-version"),
        ({"roles": _with(lambda r: r[0]["closure"].pop(0))}, "missing-mandatory"),
    ):
        write_export(workdir, make_export(**broken))
        assert main(argv(workdir), installing_prober({})) == 2
        assert reason in capsys.readouterr().err
    # A stale lock.
    write_export(workdir, make_export())
    (workdir / "lock").write_bytes(b"changed")
    assert main(argv(workdir), installing_prober({})) == 2
    assert "stale-lock" in capsys.readouterr().err
    (workdir / "lock").write_bytes(b"lock")
    # A missing required import and a successful excluded import exit 1.
    write_export(workdir, make_export())
    missing = installing_prober({})

    def drop(role, wheel_dir, closure, imports):
        installed, outcomes = missing(role, wheel_dir, closure, imports)
        return installed, {**outcomes, "shared_dep": False}

    assert main(argv(workdir), drop) == 1
    assert main(argv(workdir), installing_prober({"base": {"mcp_extra"}})) == 1
    assert "excluded import mcp_extra succeeded" in capsys.readouterr().out


def _with(change):
    roles = copy.deepcopy(make_export()["roles"])
    change(roles)
    return roles


def test_role_extra_closure_evidence(workdir: Path) -> None:
    _wheels(workdir)
    manifest = parse_export(make_export())
    status, report = evaluate(manifest, workdir / "wheels", workdir / "lock", installing_prober({}))
    assert status == 0
    assert report["export_digest"] == manifest.digest and report["lock_sha256"] == manifest.lock_sha256
    assert set(report["artifacts"]) == {"medulla-1.0-py3-none-any.whl"}
    by_role = {item["role"]: item for item in report["roles"]}
    assert by_role["mcp"]["extras"] == ["mcp"] and by_role["base"]["extras"] == []
    assert by_role["base"]["mandatory"] == ["medulla"]
    assert "mcp-extra==1.0" in by_role["mcp"]["installed"] and "mcp-extra==1.0" not in by_role["base"]["installed"]
    assert by_role["base"]["imports"]["mcp_extra"] is False and by_role["mcp"]["imports"]["mcp_extra"] is True
    # The mcp role excludes nothing that base has, so its negative case is reported absent, not invented.
    assert any(item.startswith("mcp/") for item in report["limitations"])
    assert not any(item.startswith("base/") for item in report["limitations"])


def test_role_extra_closure_cli(workdir: Path) -> None:
    for name, modules in (("medulla", ["medulla_pkg"]), ("shared-dep", ["shared_dep"]), ("mcp-extra", ["mcp_extra"])):
        make_wheel(workdir / "wheels", name, modules)
    write_export(workdir, make_export())
    assert main(argv(workdir)) == 0
    # The shared dependency stays importable in the role that excludes the extra.
    # A wheel that leaks an excluded module into the base role blocks readiness.
    make_wheel(workdir / "wheels", "shared-dep", ["shared_dep", "mcp_extra"])
    assert main(argv(workdir)) == 1
    # A mandatory dependency missing from the exported closure blocks readiness.
    write_export(workdir, make_export(roles=_with(lambda r: r[0]["closure"].pop(0))))
    assert main(argv(workdir)) == 2
