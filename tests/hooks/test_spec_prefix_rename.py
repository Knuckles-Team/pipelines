"""spec-prefix-rename rewrites retired spec ID prefixes deterministically and idempotently."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.specs.aliases import load_aliases
from pipelines_hooks.specs.prefix_rename import main

# Old prefixes are assembled so the codemod, run on this repository, never rewrites its own fixtures.
_EG = "E" + "G-"
_AU = "A" + "U-"
_SDK = "S" + "DK-"
_WEBUI = "WEB" + "UI-"
_FINUI = "FIN-" + "UI-"
_TUI = "T" + "UI-"
_GENIUSBOT = "GENIUS" + "BOT-"
_GRAPHOS = "GRAPH" + "OS-"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _write(
        tmp_path,
        f"specs/{_SDK}CONNECTOR-CONTROL/requirements.md",
        f"| `{_SDK}CONNECTOR-CONTROL-R001` | Row. Depends-on: {_EG}STORE-R002.1, {_AU}RUN-R003, {_FINUI}CHARTS-R004. |\n",
    )
    _write(tmp_path, f"specs/{_SDK}CONNECTOR-CONTROL/status.json", f'{{"spec_id": "{_SDK}CONNECTOR-CONTROL"}}\n')
    _write(
        tmp_path, "specs/identity/spec.md", f"# {_EG}IDENTITY - Title\n\n`{_EG}IDENTITY-R007.2` and {_EG}IDENTITY.\n"
    )
    _write(
        tmp_path,
        "tests/test_x.py",
        f'@pytest.mark.spec("{_SDK}CONNECTOR-CONTROL-R001")\ndef test_a():\n    pass  # spec: {_WEBUI}VIEW-R001\n'
        f"# {_TUI}KEYS-R010 {_GENIUSBOT}CHAT-R002 {_GRAPHOS}FLEET-R051\n",
    )
    _write(tmp_path, "docs/notes.md", f"Ignore {_EG}1 and {_AU}ish and X{_EG}FOO-R001 and {_EG}FOO-R0012.\n")
    _write(tmp_path, "CHANGELOG.md", f"## [Unreleased]\n- {_EG}A-R001\n\n## [1.0.0]\n- {_EG}A-R001\n")
    _write(tmp_path, "uv.lock", f"{_EG}A-R001\n")
    (tmp_path / "blob.bin").write_bytes(b"\0" + f"{_EG}A-R001".encode())
    _write(tmp_path, ".config/spec-aliases.toml", f'"{_GRAPHOS}" = "ARBORA-"\n"OLD-1" = "{_EG}A-R001"\n')
    _git(tmp_path, "add", "-A")
    return tmp_path


def _run(root: Path, repo_name: str) -> None:
    assert main(["--root", str(root), "--repo", repo_name]) == 0


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".git/" not in p.as_posix()
    }


@pytest.mark.spec("PIPE-CONNSPEC-R011")
def test_rewrites_refs_bindings_and_renames_spec_dir(repo: Path) -> None:
    _run(repo, "other")
    assert not (repo / f"specs/{_SDK}CONNECTOR-CONTROL").exists()
    requirements = (repo / "specs/SCION-CONNECTOR-CONTROL/requirements.md").read_text()
    assert "`SCION-CONNECTOR-CONTROL-R001`" in requirements
    assert "MEDULLA-STORE-R002.1, MERISTEM-RUN-R003, OVERSTORY-CHARTS-R004" in requirements
    assert '"spec_id": "SCION-CONNECTOR-CONTROL"' in (repo / "specs/SCION-CONNECTOR-CONTROL/status.json").read_text()
    spec = (repo / "specs/identity/spec.md").read_text()
    assert "# MEDULLA-IDENTITY - Title" in spec and "`MEDULLA-IDENTITY-R007.2`" in spec
    test = (repo / "tests/test_x.py").read_text()
    assert '@pytest.mark.spec("SCION-CONNECTOR-CONTROL-R001")' in test
    assert "# spec: OVERSTORY-VIEW-R001" in test
    assert "TUIG-KEYS-R010 AXIL-CHAT-R002 ARBORA-FLEET-R051" in test


@pytest.mark.spec("PIPE-CONNSPEC-R011")
def test_ignores_non_ids_history_binary_lock_and_released_changelog(repo: Path) -> None:
    _run(repo, "other")
    assert (
        repo / "docs/notes.md"
    ).read_text() == f"Ignore {_EG}1 and {_AU}ish and X{_EG}FOO-R001 and {_EG}FOO-R0012.\n"
    changelog = (repo / "CHANGELOG.md").read_text()
    assert "- MEDULLA-A-R001\n\n## [1.0.0]\n- " + _EG + "A-R001" in changelog
    assert (repo / "uv.lock").read_text() == f"{_EG}A-R001\n"
    assert (repo / "blob.bin").read_bytes().startswith(b"\0" + _EG.encode())


@pytest.mark.spec("PIPE-CONNSPEC-R011")
def test_alias_only_in_owner_and_keys_untouched(repo: Path) -> None:
    _run(repo, "other")
    other = (repo / ".config/spec-aliases.toml").read_text()
    assert f'"{_EG}"' not in other and f'"{_SDK}"' not in other
    assert f'"{_GRAPHOS}" = "ARBORA-"' in other and '"OLD-1" = "MEDULLA-A-R001"' in other


@pytest.mark.spec("PIPE-CONNSPEC-R011")
def test_owner_repo_records_its_prefix_alias(repo: Path) -> None:
    _run(repo, "scion-sdk")
    aliases = load_aliases(repo)
    assert aliases[_SDK] == "SCION-"
    assert _EG not in aliases and _AU not in aliases


@pytest.mark.spec("PIPE-CONNSPEC-R011")
def test_second_run_changes_nothing(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(repo, "medulla")
    first = _snapshot(repo)
    capsys.readouterr()
    _run(repo, "medulla")
    assert _snapshot(repo) == first
    assert "files changed: 0" in capsys.readouterr().out
    assert load_aliases(repo)[_EG] == "MEDULLA-"


@pytest.mark.spec("PIPE-CONNSPEC-R011")
def test_summary_counts_ids_per_prefix(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    _run(repo, "other")
    out = capsys.readouterr().out
    assert f"{_SDK} -> SCION-: 2 rewritten" in out
    assert f"{_FINUI} -> OVERSTORY-: 1 rewritten" in out
    assert "renamed specs/" + _SDK + "CONNECTOR-CONTROL -> specs/SCION-CONNECTOR-CONTROL" in out


@pytest.mark.spec("PIPE-CONNSPEC-R011")
def test_bare_prefix_row_id_does_not_rewrite_prose(repo: Path) -> None:
    _write(repo, "docs/bare.md", f"`{_AU}R001` and the word {_AU[:-1]} stay as prose except the ID.\n")
    _run(repo, "other")
    assert (
        repo / "docs/bare.md"
    ).read_text() == f"`MERISTEM-R001` and the word {_AU[:-1]} stay as prose except the ID.\n"


@pytest.mark.spec("PIPE-CONNSPEC-R011")
def test_bare_prefix_spec_id_follows_in_spec_id_field_and_title(repo: Path) -> None:
    _write(repo, "specs/finance/status.json", f'{{"spec_id": "{_FINUI[:-1]}"}}\n')
    _write(repo, "specs/finance/spec.md", f"# {_FINUI[:-1]} — Finance\n")
    _write(repo, "specs/finance/requirements.md", f"| `{_FINUI}R001` | Row. |\n")
    _run(repo, "other")
    assert (repo / "specs/finance/status.json").read_text() == '{"spec_id": "OVERSTORY"}\n'
    assert (repo / "specs/finance/spec.md").read_text() == "# OVERSTORY — Finance\n"
    assert "`OVERSTORY-R001`" in (repo / "specs/finance/requirements.md").read_text()


@pytest.mark.spec("PIPE-CONNSPEC-R011")
def test_range_of_row_ids_rewrites_both_ends(repo: Path) -> None:
    _write(repo, "docs/range.md", f"{_SDK}CONNECTOR-CONTROL-R014.18-R014.20\n")
    _run(repo, "other")
    assert (repo / "docs/range.md").read_text() == "SCION-CONNECTOR-CONTROL-R014.18-R014.20\n"
