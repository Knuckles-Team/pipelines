"""Fixtures that model a caller without pipeline-owned action files."""

from __future__ import annotations

import shutil
from pathlib import Path


def external_caller(tmp_path: Path, root: Path, name: str, workflow: str) -> Path:
    caller = tmp_path / name
    workflow_dir = caller / ".github/workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "release.yml").write_text(workflow, encoding="utf-8")
    contract_actions = caller / ".pipeline-contract/.github/actions"
    contract_actions.mkdir(parents=True)
    for action in (root / ".github/actions").iterdir():
        if action.is_dir():
            shutil.copytree(action, contract_actions / action.name)
    return caller
