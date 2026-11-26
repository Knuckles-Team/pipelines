"""candidate-sandbox: smoke the candidate once and publish exactly those artifacts (PIPE-RELEASE-R032)."""

from __future__ import annotations

import json
import sys

from pipelines_hooks.release import candidate_sandbox as cs
from tests.hooks.conftest import Repo

PASS = [sys.executable, "-c", "pass"]
FAIL = [sys.executable, "-c", "raise SystemExit(1)"]


def _declare(repo: Repo, failing: str = "") -> None:
    steps = {name: (FAIL if name == failing else PASS) for name in cs.DEFAULT_STEPS}
    build = [sys.executable, "-c", "open('x.whl','wb').write(b'wheel')"]
    toml = (
        '[project]\nname = "x"\nversion = "1"\n\n[tool.pipelines.candidate_sandbox]\n'
        f"build = {json.dumps(build)}\n"
        f'artifacts = ["*.whl"]\nstart = {json.dumps([sys.executable, "-c", "import time; time.sleep(30)"])}\n'
    )
    for name, argv in steps.items():
        toml += "\n[tool.pipelines.candidate_sandbox.steps]\n" if name == cs.DEFAULT_STEPS[0] else ""
        toml += f"{json.dumps(name)} = {json.dumps(argv)}\n"
    repo.commit({"pyproject.toml": toml})


# spec: PIPE-RELEASE-R032
def test_a_failed_smoke_step_blocks_publish(repo: Repo, capsys) -> None:
    steps = {n: PASS for n in cs.DEFAULT_STEPS} | {"write": FAIL}
    assert cs.smoke(steps, cs.DEFAULT_STEPS, lambda argv: 1 if argv is FAIL else 0) == ["write: the smoke step failed"]
    assert cs.smoke({"health": PASS}, ["health", "read"], lambda argv: 0) == ["read: the step is not declared"]
    _declare(repo, failing="sign-in")
    assert repo.run("candidate-sandbox", "smoke") == 1
    assert "CANDIDATE_REFUSED sign-in" in capsys.readouterr().err
    _declare(repo)
    assert repo.run("candidate-sandbox", "smoke") == 0


# spec: PIPE-RELEASE-R032
def test_publish_digest_must_match_the_built_digest(repo: Repo, capsys) -> None:
    _declare(repo)
    assert repo.run("candidate-sandbox", "build") == 0
    recorded = json.loads((repo.root / "candidate-digests.json").read_text())
    assert list(recorded) == ["x.whl"]
    assert repo.run("candidate-sandbox", "verify") == 0
    (repo.root / "x.whl").write_bytes(b"tampered")
    assert repo.run("candidate-sandbox", "verify") == 1
    assert "publish digest differs from the built digest" in capsys.readouterr().err
    assert cs.verify({"a": "1"}, {"a": "1"}) == [] and cs.verify({"a": "1"}, {}) == [
        "a: recorded artifact is not published"
    ]
