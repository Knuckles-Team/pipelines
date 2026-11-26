"""Warm slot lifecycle: ``status``, ``up``, ``down`` and ``upgrade`` (PIPE-GATES-R072, R073).

Every command runs through an injected :class:`SlotRuntime` adapter, so the
same logic drives any runtime; :class:`SshHostRuntime` is the plain SSH host
adapter and takes an injected command runner. A slot is named
``<pool>-<number>`` and keeps its target directory, runs and sccache under
``<cache root>/slot-<number>``; its held locks are the files in that
directory's ``locks`` folder. Timings of ``up`` go to the timings file of
``budgets``. The clock is injected; nothing sleeps.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pipelines_hooks.ci.warm_slots.budgets import COLD_PRIME, Timing, record_timing
from pipelines_hooks.ci.warm_slots.config import Pool, SlotConfig
from pipelines_hooks.core.errors import CannotRun

GIB = 1024**3
DISABLED_MARKER = "DISABLED"


@dataclass(frozen=True)
class Slot:
    """One slot of one pool."""

    pool: Pool
    number: int

    @property
    def name(self) -> str:
        return f"{self.pool.name}-{self.number}"

    @property
    def directory(self) -> str:
        return f"{self.pool.cache_root.rstrip('/')}/slot-{self.number}"


def slots_of(config: SlotConfig) -> list[Slot]:
    """Every slot of every pool, in pool then number order."""
    return [Slot(pool, number) for pool in config.pools for number in range(1, pool.slots + 1)]


@dataclass(frozen=True)
class SlotStatus:
    """What ``status`` reports for one slot."""

    slot: str
    locks: tuple[str, ...]
    cache_bytes: int
    free_disk_bytes: int
    toolchains: dict[str, str]
    disabled: bool = False


class SlotRuntime(Protocol):
    """The reach into one runtime's slots; the lifecycle commands use nothing else."""

    def held_locks(self, slot: Slot) -> tuple[str, ...]: ...
    def cache_bytes(self, slot: Slot) -> int: ...
    def free_disk_bytes(self, slot: Slot) -> int: ...
    def toolchains(self, slot: Slot) -> dict[str, str]: ...
    def is_disabled(self, slot: Slot) -> bool: ...
    def provision(self, slot: Slot) -> None: ...
    def prime(self, slot: Slot, command: str) -> bool: ...
    def disable(self, slot: Slot) -> None: ...
    def drop_caches(self, slot: Slot) -> None: ...
    def install_toolchain(self, pool: Pool, name: str, version: str) -> None: ...


def status(config: SlotConfig, runtime: SlotRuntime) -> list[SlotStatus]:
    """Each slot with its held locks, cache size, free disk and installed toolchains."""
    return [
        SlotStatus(
            slot=slot.name,
            locks=runtime.held_locks(slot),
            cache_bytes=runtime.cache_bytes(slot),
            free_disk_bytes=runtime.free_disk_bytes(slot),
            toolchains=runtime.toolchains(slot),
            disabled=runtime.is_disabled(slot),
        )
        for slot in slots_of(config)
    ]


def format_status(rows: Sequence[SlotStatus]) -> str:
    """One line per slot."""
    lines = []
    for row in rows:
        locks = ",".join(row.locks) or "none"
        tools = " ".join(f"{name}={version}" for name, version in sorted(row.toolchains.items())) or "none"
        state = " DISABLED" if row.disabled else ""
        lines.append(
            f"{row.slot}{state}: locks {locks}; cache {row.cache_bytes / GIB:.1f} GiB; "
            f"free {row.free_disk_bytes / GIB:.1f} GiB; toolchains {tools}"
        )
    return "\n".join(lines)


def up(config: SlotConfig, runtime: SlotRuntime, clock: Callable[[], float]) -> list[str]:
    """Provision and prime every slot at the default branch head; findings name each slot that failed.

    A slot whose free disk is below the cache budget is not primed. The
    cold-prime time of each primed slot is recorded when the configuration
    names a timings file.
    """
    findings: list[str] = []
    if not config.prime_command:
        raise CannotRun("warm slots: up needs prime_command in the configuration")
    for slot in slots_of(config):
        budget = slot.pool.cache_budget_gb * GIB
        free = runtime.free_disk_bytes(slot)
        if free < budget:
            findings.append(
                f"{slot.name}: free disk {free / GIB:.1f} GiB is below the {slot.pool.cache_budget_gb} GiB budget"
            )
            continue
        runtime.provision(slot)
        started = clock()
        if not runtime.prime(slot, config.prime_command):
            findings.append(f"{slot.name}: the prime at the default branch head failed")
            continue
        if config.timings_file:
            record_timing(
                Path(config.timings_file),
                Timing(COLD_PRIME, round(clock() - started, 3), slot.name, config.jobs_per_slot),
            )
    return findings


def down(config: SlotConfig, runtime: SlotRuntime, *, force: bool = False) -> list[str]:
    """Scale the pool to zero: disable every slot and drop its targets, runs and sccache.

    A held slot refuses the whole command, naming it, unless ``force`` is set;
    a refusal changes nothing.
    """
    slots = slots_of(config)
    if not force:
        held = [slot.name for slot in slots if runtime.held_locks(slot)]
        if held:
            return [f"{name}: held by a running job; pass the force flag to scale down anyway" for name in held]
    for slot in slots:
        runtime.disable(slot)
        runtime.drop_caches(slot)
    return []


def upgrade(config: SlotConfig, runtime: SlotRuntime, *, rust: str = "", python: str = "") -> list[str]:
    """Install a new Rust or Python version on every slot host; findings name each host that failed."""
    if not rust and not python:
        raise CannotRun("warm slots: upgrade needs a rust or python version")
    findings = []
    for pool in config.pools:
        for name, version in (("rust", rust), ("python", python)):
            if not version:
                continue
            try:
                runtime.install_toolchain(pool, name, version)
            except CannotRun as exc:
                findings.append(f"{pool.host or pool.name}: {name} {version} failed: {exc}")
    return findings


#: One remote command: ``(host, argv) -> (exit status, stdout)``.
RemoteRun = Callable[[str, Sequence[str]], tuple[int, str]]


def _safe_directory(directory: str) -> str:
    path = Path(directory)
    if not path.is_absolute() or ".." in path.parts or len(path.parts) < 4:
        raise CannotRun(f"warm slots: refusing to act on the unsafe cache path {directory!r}")
    return directory


@dataclass
class SshHostRuntime:
    """The plain SSH host adapter: each slot is a directory on a host, reached through ``run``."""

    run: RemoteRun
    jobs_env: dict[str, str] = field(default_factory=dict)

    def _out(self, slot: Slot, *argv: str) -> str:
        status, output = self.run(slot.pool.host, argv)
        if status != 0:
            raise CannotRun(f"{slot.name}: {' '.join(argv[:2])} exited {status}")
        return output

    def held_locks(self, slot: Slot) -> tuple[str, ...]:
        status, output = self.run(slot.pool.host, ("ls", "-1", f"{_safe_directory(slot.directory)}/locks"))
        return tuple(line for line in output.splitlines() if line) if status == 0 else ()

    def cache_bytes(self, slot: Slot) -> int:
        status, output = self.run(slot.pool.host, ("du", "-sb", _safe_directory(slot.directory)))
        return int(output.split()[0]) if status == 0 and output.split() else 0

    def free_disk_bytes(self, slot: Slot) -> int:
        output = self._out(slot, "df", "--output=avail", "-B1", slot.pool.cache_root)
        return int(output.splitlines()[-1].strip())

    def toolchains(self, slot: Slot) -> dict[str, str]:
        found = {}
        for name, argv in (
            ("rustc", ("rustc", "--version")),
            ("python", ("python3", "--version")),
            ("nextest", ("cargo", "nextest", "--version")),
            ("sccache", ("sccache", "--version")),
        ):
            status, output = self.run(slot.pool.host, argv)
            if status == 0 and output.strip():
                found[name] = output.strip().splitlines()[0].split()[-1]
        return found

    def is_disabled(self, slot: Slot) -> bool:
        status, _ = self.run(slot.pool.host, ("test", "-e", f"{slot.pool.cache_root.rstrip('/')}/{DISABLED_MARKER}"))
        return status == 0

    def provision(self, slot: Slot) -> None:
        self._out(
            slot,
            "mkdir",
            "-p",
            f"{_safe_directory(slot.directory)}/locks",
            f"{slot.directory}/target",
            f"{slot.directory}/sccache",
        )

    def prime(self, slot: Slot, command: str) -> bool:
        status, _ = self.run(
            slot.pool.host,
            (
                "env",
                f"CARGO_TARGET_DIR={slot.directory}/target",
                f"SCCACHE_DIR={slot.directory}/sccache",
                *shlex.split(command),
            ),
        )
        return status == 0

    def disable(self, slot: Slot) -> None:
        self._out(slot, "touch", f"{slot.pool.cache_root.rstrip('/')}/{DISABLED_MARKER}")

    def drop_caches(self, slot: Slot) -> None:
        directory = _safe_directory(slot.directory)
        self._out(slot, "rm", "-rf", f"{directory}/target", f"{directory}/runs", f"{directory}/sccache")

    def install_toolchain(self, pool: Pool, name: str, version: str) -> None:
        argv = {"rust": ("rustup", "toolchain", "install", version), "python": ("uv", "python", "install", version)}[
            name
        ]
        status, output = self.run(pool.host, argv)
        if status != 0:
            raise CannotRun(output.strip()[:200] or f"exit {status}")
