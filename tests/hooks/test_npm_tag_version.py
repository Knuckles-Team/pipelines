"""PIPE-RELEASE-R033: an npm release needs the tag to equal the package version and the version to be unpublished."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.release import npm_tag_version

NAME = "@example/city"


def _package(root: Path, version: str) -> Path:
    (root / "package.json").write_text(json.dumps({"name": NAME, "version": version}), encoding="utf-8")
    return root


def test_tag_and_package_version_must_match_and_existing_versions_refuse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: PIPE-RELEASE-R033
    _package(tmp_path, "1.2.3")
    published: set[tuple[str, str]] = set()
    monkeypatch.setattr(npm_tag_version, "registry_has", lambda name, version: (name, version) in published)

    assert npm_tag_version.main(["--tag", "v1.2.3", "--root", str(tmp_path)]) == 0

    assert npm_tag_version.main(["--tag", "v1.2.4", "--root", str(tmp_path)]) == 1
    assert "TAG_VERSION_MISMATCH" in capsys.readouterr().out
    assert npm_tag_version.main(["--tag", "1.2.3", "--root", str(tmp_path)]) == 1

    published.add((NAME, "1.2.3"))
    assert npm_tag_version.main(["--tag", "v1.2.3", "--root", str(tmp_path)]) == 1
    assert "VERSION_EXISTS" in capsys.readouterr().out

    # The tag check alone never asks the registry.
    assert npm_tag_version.main(["--tag", "v1.2.3", "--root", str(tmp_path), "--skip-registry"]) == 0


def test_an_unreadable_package_cannot_run(tmp_path: Path) -> None:
    # spec: PIPE-RELEASE-R033
    from pipelines_hooks.core.errors import CannotRun

    with pytest.raises(CannotRun):
        npm_tag_version.check(tmp_path, "v1.0.0", lookup=None)
