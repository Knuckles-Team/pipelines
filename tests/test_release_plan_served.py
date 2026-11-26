"""The release plan reaches the engine through a served endpoint (PIPE-RELEASE-R025.7)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from pipelines_hooks.verdict_publish import post_operation  # noqa: E402
from scripts import release_scope as rs  # noqa: E402
from tests.hooks.arbora_loopback import Loopback, serving  # noqa: E402
from tests.test_release_plan import two_project_rows  # noqa: E402


# spec: PIPE-RELEASE-R025.7
def test_published_plan_answers_rows_per_repository_through_ask(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = two_project_rows()
    releases = tmp_path / "releases"
    releases.mkdir()
    (releases / "P1.yml").write_text(json.dumps(rs.manifest("P1", ["Q-B-R001"], rows)))
    with serving(Loopback()) as engine, mock.patch.object(rs, "all_rows", return_value=rows):
        code = rs.main(
            [
                "--workspace",
                str(tmp_path),
                "--releases",
                str(releases),
                "--plan",
                "P1",
                "--publish",
                "--endpoint",
                engine.endpoint,
            ]
        )
        engine_rows = post_operation(engine.endpoint, "", "release.rows", {"repository": "engine"})
        door_rows = post_operation(engine.endpoint, "", "release.rows", {"repository": "door"})
        unknown = post_operation(engine.endpoint, "", "release.rows", {"repository": "absent"})
    assert code == 0
    assert "published P1" in capsys.readouterr().err
    assert [op for op, _, _ in engine.calls][0] == "source.release_graph"
    assert engine_rows == {"rows": ["P-A-R001", "P-A-R002"]}
    assert door_rows == {"rows": ["Q-B-R001"]}
    assert unknown == {"rows": []}
