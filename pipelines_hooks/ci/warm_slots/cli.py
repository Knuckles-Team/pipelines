"""warm-slots: render, status, up, down, upgrade and budgets over the one slot configuration."""

from __future__ import annotations

import argparse
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from pipelines_hooks.ci.warm_slots import lifecycle
from pipelines_hooks.ci.warm_slots.budgets import check_budgets, load_timings
from pipelines_hooks.ci.warm_slots.config import SlotConfig, load_config
from pipelines_hooks.ci.warm_slots.definition import DEFAULT_CONFIG
from pipelines_hooks.ci.warm_slots.render import render_runtime
from pipelines_hooks.core.errors import CannotRun

RuntimeFactory = Callable[[SlotConfig], lifecycle.SlotRuntime]
SSH_TIMEOUT_SECONDS = 3600


def ssh_run(host: str, argv: Sequence[str]) -> tuple[int, str]:
    """Run one command on one host over SSH; a transport failure cannot run."""
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", host, *argv],
            capture_output=True,
            text=True,
            check=False,
            timeout=SSH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CannotRun(f"{host}: ssh failed: {exc}") from None
    return result.returncode, result.stdout


def default_runtime(config: SlotConfig) -> lifecycle.SlotRuntime:
    """The plain SSH host adapter; the other runtimes are driven by their rendered manifests."""
    return lifecycle.SshHostRuntime(run=ssh_run)


def _report(findings: Sequence[str], heading: str) -> int:
    if findings:
        print(f"FAIL: {heading}")
        for finding in findings:
            print(f"    {finding}")
        return 1
    return 0


def main(
    argv: list[str],
    *,
    runtime_factory: RuntimeFactory = default_runtime,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    parser = argparse.ArgumentParser(prog="warm-slots", description=__doc__)
    parser.add_argument("command", choices=("render", "status", "up", "down", "upgrade", "budgets"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=None, help=f"the slot configuration (default {DEFAULT_CONFIG})")
    parser.add_argument("--runtime", default=None, help="render for this runtime (default: the configured one)")
    parser.add_argument("--out", type=Path, default=None, help="render into this directory")
    parser.add_argument("--force", action="store_true", help="down: scale down even while a slot is held")
    parser.add_argument("--rust", default="", help="upgrade: the Rust version to install")
    parser.add_argument("--python", default="", help="upgrade: the Python version to install")
    args = parser.parse_args(argv)
    config = load_config(args.config or args.root.resolve() / DEFAULT_CONFIG)
    if args.command == "render":
        files = render_runtime(config, args.runtime)
        for relative, text in sorted(files.items()):
            if args.out is None:
                print(f"# {relative}\n{text}")
            else:
                target = args.out / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
        return 0
    if args.command == "budgets":
        if not config.timings_file:
            raise CannotRun("warm slots: budgets needs timings_file in the configuration")
        status = _report(
            check_budgets(load_timings(Path(config.timings_file)), config.budgets),
            "a warm slot timing is over its budget",
        )
        if status == 0:
            print("warm-slots: OK: every recorded timing is within its budget")
        return status
    runtime = runtime_factory(config)
    if args.command == "status":
        print(lifecycle.format_status(lifecycle.status(config, runtime)))
        return 0
    if args.command == "up":
        return _report(lifecycle.up(config, runtime, clock), "up did not provision every slot")
    if args.command == "down":
        return _report(lifecycle.down(config, runtime, force=args.force), "down refused")
    return _report(lifecycle.upgrade(config, runtime, rust=args.rust, python=args.python), "upgrade failed")
