"""An engine release proves the newest released SDK still imports (PIPE-RELEASE-R024)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from scripts.release import consumer_import as ci  # noqa: E402
from scripts.release.errors import ReleaseError  # noqa: E402


def _probe(failures: list[dict], requires: list[str]):
    return lambda venv, package, distribution: {"failures": failures, "requires": requires}


# spec: PIPE-RELEASE-R024
def test_removed_symbol_fails_and_is_named() -> None:
    broken = [{"module": "sdk.client", "error": "ImportError: cannot import name 'GraphClient' from 'engine.api'"}]
    with pytest.raises(ReleaseError, match="removed symbol GraphClient"):
        ci.check_consumer_import("engine==2.0.0", "sdk", "sdk", install=lambda *_: None, probe=_probe(broken, []))
    attr = [{"module": "sdk.x", "error": "AttributeError: module 'engine' has no attribute 'gone'"}]
    with pytest.raises(ReleaseError, match="removed symbol gone"):
        ci.check_consumer_import("engine==2.0.0", "sdk", "sdk", install=lambda *_: None, probe=_probe(attr, []))
    assert (
        ci.check_consumer_import(
            "engine==2.0.0", "sdk", "sdk", install=lambda *_: None, probe=_probe([], ["engine<3,>=2"])
        )
        == []
    )


# spec: PIPE-RELEASE-R024
def test_missing_ceiling_is_reported() -> None:
    assert ci.missing_ceiling(["engine>=2"], "engine") is True
    assert ci.missing_ceiling(["engine>=2,<3"], "engine") is False
    assert ci.missing_ceiling(["engine~=2.1"], "engine") is False
    assert ci.missing_ceiling(["other>=1"], "engine") is False
    found = ci.check_consumer_import(
        "engine==2.0.0", "sdk", "sdk", install=lambda *_: None, probe=_probe([], ["engine>=2"])
    )
    assert found == ["sdk declares no ceiling on engine"]


def test_the_real_probe_imports_a_package_and_names_a_broken_module(tmp_path: Path) -> None:
    pkg = tmp_path / "fixturesdk"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "good.py").write_text("X = 1\n")
    (pkg / "bad.py").write_text("from os import not_a_real_symbol\n")
    (pkg / "_private.py").write_text("raise RuntimeError('never imported')\n")
    import subprocess

    done = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            f"import sys; sys.path.insert(0, {str(tmp_path)!r}); sys.argv=['p','fixturesdk','pip']; exec({ci._PROBE!r})",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    import json

    result = json.loads(done.stdout)
    assert [f["module"] for f in result["failures"]] == ["fixturesdk.bad"]
    assert ci.removed_symbol(result["failures"][0]["error"]) == "not_a_real_symbol"
