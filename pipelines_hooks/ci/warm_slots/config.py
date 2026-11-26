"""The one warm slot configuration file, read once for every runtime (PIPE-GATES-R071).

One file holds the slot definition (the image), and per host or pool the
slot count, the cache root, the cache size budget and the auto-selection
flag. The same values render for Kubernetes, Docker Compose, rootless
Podman and the plain SSH host mode, and the lifecycle commands read them.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.ci.warm_slots.budgets import Budgets
from pipelines_hooks.ci.warm_slots.definition import SlotDefinition
from pipelines_hooks.core.errors import CannotRun

RUNTIMES = ("kubernetes", "compose", "podman", "ssh")
DEFAULT_RUNTIME = "kubernetes"


@dataclass(frozen=True)
class Pool:
    """One host or pool of slots."""

    name: str
    slots: int
    cache_root: str
    cache_budget_gb: int
    auto_select: bool
    cache_filesystem: str = ""
    host: str = ""
    node: str = ""


@dataclass(frozen=True)
class SlotConfig:
    """The shared configuration: definition, runtime settings, pools and budgets."""

    definition: SlotDefinition
    pools: tuple[Pool, ...]
    runtime: str = DEFAULT_RUNTIME
    namespace: str = ""
    repository_url: str = ""
    runner_label: str = "warm-slot"
    prime_command: str = ""
    jobs_per_slot: int = 8
    timings_file: str = ""
    budgets: Budgets = Budgets()


def _table(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CannotRun(f"warm slots: {label} must be a table")
    return value


def _count(table: Mapping[str, object], key: str, label: str) -> int:
    value = table.get(key)
    if type(value) is not int or value < 1:
        raise CannotRun(f"warm slots: {label}.{key} must be an integer of at least 1")
    return value


def parse_config(document: Mapping[str, object]) -> SlotConfig:
    """Build the configuration from one parsed TOML document; a malformed value names its field."""
    pools = []
    raw_pools = document.get("pool")
    if not isinstance(raw_pools, list) or not raw_pools:
        raise CannotRun("warm slots: the configuration needs at least one [[pool]]")
    for index, raw in enumerate(raw_pools):
        table = _table(raw, f"pool[{index}]")
        name = str(table.get("name", ""))
        label = f"pool {name or index}"
        if not name:
            raise CannotRun(f"warm slots: {label}.name is required")
        pools.append(
            Pool(
                name=name,
                slots=_count(table, "slots", label),
                cache_root=str(table.get("cache_root", "")),
                cache_budget_gb=_count(table, "cache_budget_gb", label),
                auto_select=bool(table.get("auto_select", False)),
                cache_filesystem=str(table.get("cache_filesystem", "")),
                host=str(table.get("host", "")),
                node=str(table.get("node", "")),
            )
        )
    limits = _table(document.get("budgets", {}), "budgets")
    defaults = Budgets()
    budgets = Budgets(
        warm_check_seconds=float(limits.get("warm_check_seconds", defaults.warm_check_seconds)),  # type: ignore[arg-type]
        cold_prime_seconds=float(limits.get("cold_prime_seconds", defaults.cold_prime_seconds)),  # type: ignore[arg-type]
        pr_wall_seconds=float(limits.get("pr_wall_seconds", defaults.pr_wall_seconds)),  # type: ignore[arg-type]
    )
    runtime = str(document.get("runtime", DEFAULT_RUNTIME))
    if runtime not in RUNTIMES:
        raise CannotRun(f"warm slots: runtime {runtime!r} is not one of {', '.join(RUNTIMES)}")
    return SlotConfig(
        definition=SlotDefinition.from_mapping(_table(document.get("image", {}), "image")),
        pools=tuple(pools),
        runtime=runtime,
        namespace=str(document.get("namespace", "")),
        repository_url=str(document.get("repository_url", "")),
        runner_label=str(document.get("runner_label", "warm-slot")),
        prime_command=str(document.get("prime_command", "")),
        jobs_per_slot=int(document.get("jobs_per_slot", 8)),  # type: ignore[call-overload]
        timings_file=str(document.get("timings_file", "")),
        budgets=budgets,
    )


def load_config(path: Path) -> SlotConfig:
    """Read the one configuration file; unreadable or malformed input cannot run."""
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"warm slots: cannot read {path.name}: {exc}") from None
    return parse_config(document)
