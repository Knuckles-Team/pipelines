"""Exact retired standard IDs retain historical evidence without bypassing gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.specs.aliases import canonical_id, load_aliases
from tests.hooks.conftest import Repo

# spec: PIPE-CONNSPEC-R011

_OLD = "ARBORA-A2A-R002.2.2.3.1"
_NEW = "ARBORA-A2A-R002.2.3.1"
_ALIAS = f'"{_OLD}" = "{_NEW}"\n'
_CURRENT_IDS = ("ARBORA-A2A-R002", "ARBORA-A2A-R002.2", "ARBORA-A2A-R002.2.3", _NEW)


def _rows(*ids: str) -> str:
    return "| ID | Requirement |\n|---|---|\n" + "".join(f"| `{rid}` | **Row {rid}.** |\n" for rid in ids)


def _alias_file(root: Path, text: str = _ALIAS) -> None:
    config = root / ".config"
    config.mkdir(exist_ok=True)
    (config / "spec-aliases.toml").write_text(text, encoding="utf-8")


def _current_repo(repo: Repo, *, bound: bool = True) -> str:
    files = {".config/spec-aliases.toml": _ALIAS, "specs/demo/requirements.md": _rows(*_CURRENT_IDS)}
    if bound:
        files["tests/test_transport.py"] = f"# spec: {_NEW}\n"
    return repo.commit(files, "current spec")


def test_standard_alias_preserves_history_and_current_range(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    historical_base = repo.commit({"specs/demo/requirements.md": _rows(_OLD)}, "old spec")
    landed = repo.commit({"pkg/transport.py": "# transport\n"}, f"implement transport\n\nSpec: {_OLD}")
    repo.commit({"tests/test_transport.py": f"# spec: {_OLD}\n"}, f"prove transport\n\nSpec: {_OLD}")
    assert repo.run("spec-status", "--write") == 0
    repo.commit({"specs/demo/status.json": (repo.root / "specs/demo/status.json").read_text()}, "status")
    current_base = _current_repo(repo)
    repo.commit({"pkg/transport.py": "# current transport\n"}, f"current fix\n\nSpec: {_NEW}")

    assert repo.run("spec-trailers", "--base-ref", historical_base) == 0
    historical_output = capsys.readouterr().out
    assert "WARN" in historical_output and _OLD in historical_output and _NEW in historical_output
    assert repo.run("spec-trailers", "--base-ref", current_base) == 0
    assert "WARN" not in capsys.readouterr().out
    assert repo.run("spec-status", "--write") == 0
    status = json.loads((repo.root / "specs/demo/status.json").read_text())
    assert status["requirement_ids"] == list(_CURRENT_IDS)
    row = next(row for row in status["requirements"] if row["id"] == _NEW)
    assert row["delivery_state"] == "VERIFIED"
    assert landed[:12] in row["landed_in"]
    assert row["verified_by"]
    assert repo.run("spec-decomposition") == 0


def test_standard_alias_keeps_old_test_bindings(repo: Repo) -> None:
    base = _current_repo(repo, bound=False)
    repo.commit(
        {"tests/test_transport.py": f"# spec: {_OLD}\n", "pkg/transport.py": "# transport\n"},
        f"transport\n\nSpec: {_OLD}",
    )
    assert repo.run("spec-trailers", "--base-ref", base) == 0
    assert repo.run("spec-status", "--write") == 0
    status = json.loads((repo.root / "specs/demo/status.json").read_text())
    assert status["requirements"][0]["delivery_state"] == "VERIFIED"


def test_standard_alias_coexists_with_legacy_aliases(repo: Repo) -> None:
    _current_repo(repo)
    _alias_file(repo.root, _ALIAS + '"GRAPHOS-" = "ARBORA-"\n"PA-12" = "ARBORA-FLEET-R051"\n')
    aliases = load_aliases(repo.root)
    assert canonical_id(_OLD, aliases) == _NEW
    assert canonical_id("GRAPHOS-A2A-R002.2.3.1", aliases) == _NEW
    assert canonical_id("PA-12", aliases) == "ARBORA-FLEET-R051"
    assert canonical_id(_OLD + ".1", aliases) == _OLD + ".1"
    assert canonical_id(_OLD + "0", aliases) == _OLD + "0"


@pytest.mark.parametrize(
    "requirements, reason",
    [
        (_rows(_OLD, _NEW), "still has a requirement row"),
        (_rows(_NEW) + f"| `{_OLD}` | **Still active.** Mentions RETIRED in prose. |\n", "still has a requirement row"),
        (_rows(_NEW) + f"| `{_OLD}` | **RETIRED: renumbered.** |\n", "still has a requirement row"),
        (
            f"| `{_OLD}` | **RETIRED: renumbered.** |\n" + _rows(_OLD, _NEW),
            "still has a requirement row",
        ),
        (_rows("OTHER-R001"), "not an active"),
        (f"| `{_NEW}` | **RETIRED: replaced.** |\n", "not an active"),
        (f"The current requirement is `{_NEW}`.\n", "not an active"),
        (_rows("OTHER-R001") + f"| `OTHER-R002` | References `{_NEW}`. |\n", "not an active"),
    ],
)
def test_standard_alias_rejects_invalid_current_rows(repo: Repo, requirements: str, reason: str) -> None:
    repo.write("specs/demo/requirements.md", requirements)
    _alias_file(repo.root)
    with pytest.raises(CannotRun, match=reason):
        load_aliases(repo.root)
    assert repo.run("spec-trailers") == 2


@pytest.mark.parametrize(
    "text",
    [
        f'"{_OLD}" = "{_OLD}"\n',
        _ALIAS + f'"{_NEW}" = "{_OLD}"\n',
        _ALIAS + f'"{_NEW}" = "ARBORA-A2A-R003"\n',
        _ALIAS + f'"PA-12" = "{_OLD}"\n',
        _ALIAS + '"ARBORA-" = "OTHER-"\n',
        _ALIAS + '"ARBORA-A2A-" = "OTHER-"\n',
        '"OLD-R001" = "CURRENT-R001"\n"CURRENT-" = "NEW-"\n',
        '"OLD-R001" = "CURRENT-R001"\n"OLD-" = "CURRENT-"\n',
        '"OLD-AREA-R001" = "CURRENT-R001"\n"OLD-" = "CURRENT-"\n"OLD-AREA-" = "OTHER-"\n',
    ],
)
def test_standard_alias_rejects_cycles_chains_and_prefix_collisions(repo: Repo, text: str) -> None:
    repo.write("specs/demo/requirements.md", _rows(_NEW, "CURRENT-R001"))
    _alias_file(repo.root, text)
    with pytest.raises(CannotRun):
        load_aliases(repo.root)
    assert repo.run("spec-trailers") == 2


def test_standard_alias_does_not_rescue_unbound_target(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = _current_repo(repo, bound=False)
    repo.commit({"pkg/transport.py": "# transport\n"}, f"transport\n\nSpec: {_OLD}")
    assert repo.run("spec-trailers", "--base-ref", base) == 1
    output = capsys.readouterr().out
    assert "no bound test" in output and _NEW in output


@pytest.mark.parametrize("unknown", ["ARBORA-A2A-R999", _OLD + ".1", _OLD + "0", "GRAPHOS-A2A-R002.2.2.3.1"])
def test_standard_alias_does_not_rescue_unknown_trailers(
    repo: Repo, capsys: pytest.CaptureFixture[str], unknown: str
) -> None:
    base = _current_repo(repo)
    repo.commit(
        {"pkg/transport.py": "# transport\n", ".config/spec-aliases.toml": _ALIAS + '"GRAPHOS-" = "ARBORA-"\n'},
        f"transport\n\nSpec: {_OLD}, {unknown}",
    )
    assert repo.run("spec-trailers", "--base-ref", base) == 1
    assert "unknown requirement id(s)" in capsys.readouterr().out
