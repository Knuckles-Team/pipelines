"""The published hook catalogue, the CLI registry and this repository's self-run agree."""

from __future__ import annotations

import yaml

from pipelines_hooks.cli import GATES
from tests.hooks.conftest import HOOK_REPOSITORY


def _catalogue() -> dict[str, dict]:
    hooks = yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    return {hook["id"]: hook for hook in hooks}


def test_every_catalogue_entry_runs_a_registered_gate() -> None:
    for hook_id, hook in _catalogue().items():
        command = hook["entry"].split()
        assert command[0] == "pipelines-hook", hook_id
        assert command[1] in GATES, hook_id


def test_every_registered_gate_is_published() -> None:
    published = {hook["entry"].split()[1] for hook in _catalogue().values()}
    assert published == set(GATES)


def test_this_repository_runs_its_hooks_with_the_published_entries() -> None:
    config = yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    local = {hook["id"]: hook for repo in config["repos"] if repo["repo"] == "local" for hook in repo["hooks"]}
    catalogue = _catalogue()
    self_run = {hook_id: hook for hook_id, hook in local.items() if hook_id in catalogue}
    assert self_run, "the repository runs none of its own hooks"
    for hook_id, hook in self_run.items():
        assert hook["entry"].endswith(catalogue[hook_id]["entry"]), hook_id
