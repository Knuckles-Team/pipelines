"""state-machine-census: the whole-tree mode of the state-machine hooks (manual stage)."""

from __future__ import annotations

from pipelines_hooks.code import state_machine


def main(argv: list[str]) -> int:
    return state_machine.main(["--census", *argv])
