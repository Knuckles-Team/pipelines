"""Warm slot status, up, down and upgrade through injected adapters (PIPE-GATES-R072, R073)."""

from __future__ import annotations

import json

import pytest
from pipelines_hooks.ci.warm_slots import lifecycle
from pipelines_hooks.ci.warm_slots.budgets import COLD_PRIME, load_timings
from pipelines_hooks.ci.warm_slots.cli import main
from pipelines_hooks.core.errors import CannotRun

from tests.hooks.warm_slot_fixtures import CONFIG_TEXT, config

GIB = 1024**3


class FakeRuntime:
    """An in-memory runtime: records every call and reports what each test arranges."""

    def __init__(self, *, locks=None, free_gib=500, bad_primes=(), bad_hosts=()) -> None:
        self.locks = locks or {}
        self.free = free_gib * GIB
        self.bad_primes, self.bad_hosts = set(bad_primes), set(bad_hosts)
        self.calls: list[tuple[str, str]] = []
        self.disabled: set[str] = set()
        self.dropped: set[str] = set()

    def held_locks(self, slot):
        return tuple(self.locks.get(slot.name, ()))

    def cache_bytes(self, slot):
        return 3 * GIB

    def free_disk_bytes(self, slot):
        return self.free

    def toolchains(self, slot):
        return {"rustc": "1.96.0", "python": "3.14.0"}

    def is_disabled(self, slot):
        return slot.name in self.disabled

    def provision(self, slot):
        self.calls.append(("provision", slot.name))

    def prime(self, slot, command):
        self.calls.append(("prime", f"{slot.name}:{command}"))
        return slot.name not in self.bad_primes

    def disable(self, slot):
        self.disabled.add(slot.name)

    def drop_caches(self, slot):
        self.dropped.add(slot.name)

    def install_toolchain(self, pool, name, version):
        self.calls.append(("install", f"{pool.host}:{name}:{version}"))
        if pool.host in self.bad_hosts:
            raise CannotRun("unreachable")


@pytest.mark.spec("PIPE-GATES-R072")
def test_status_reports_locks_cache_disk_and_toolchains() -> None:
    runtime = FakeRuntime(locks={"alpha-2": ["job-41"]})
    rows = lifecycle.status(config(), runtime)
    assert [row.slot for row in rows] == ["alpha-1", "alpha-2", "beta-1"]
    held = next(row for row in rows if row.slot == "alpha-2")
    assert held.locks == ("job-41",) and held.cache_bytes == 3 * GIB and held.toolchains["rustc"] == "1.96.0"
    text = lifecycle.format_status(rows)
    assert "alpha-2: locks job-41; cache 3.0 GiB; free 500.0 GiB; toolchains python=3.14.0 rustc=1.96.0" in text
    assert "alpha-1: locks none" in text


@pytest.mark.spec("PIPE-GATES-R072")
def test_up_primes_every_slot_at_the_default_branch_head(tmp_path) -> None:
    timings = tmp_path / "timings.json"
    text = f'timings_file = "{timings}"\n' + CONFIG_TEXT
    clock = iter(range(0, 1000, 7))
    runtime = FakeRuntime()
    findings = lifecycle.up(config(text), runtime, lambda: float(next(clock)))
    assert findings == []
    assert [c for c in runtime.calls if c[0] == "prime"] == [
        ("prime", f"{name}:cargo nextest run --no-run") for name in ("alpha-1", "alpha-2", "beta-1")
    ]
    recorded = load_timings(timings)
    assert [(t.measurement, t.subject, t.seconds, t.jobs) for t in recorded] == [
        (COLD_PRIME, "alpha-1", 7.0, 8),
        (COLD_PRIME, "alpha-2", 7.0, 8),
        (COLD_PRIME, "beta-1", 7.0, 8),
    ]
    # Refusals name the slot: a failed prime and a disk below the budget.
    assert lifecycle.up(config(), FakeRuntime(bad_primes={"beta-1"}), lambda: 0.0) == [
        "beta-1: the prime at the default branch head failed"
    ]
    low = lifecycle.up(config(), FakeRuntime(free_gib=150), lambda: 0.0)
    assert low == [
        "alpha-1: free disk 150.0 GiB is below the 200 GiB budget",
        "alpha-2: free disk 150.0 GiB is below the 200 GiB budget",
    ]
    with pytest.raises(CannotRun, match="prime_command"):
        lifecycle.up(
            config(CONFIG_TEXT.replace('prime_command = "cargo nextest run --no-run"\n', "")), runtime, lambda: 0.0
        )


@pytest.mark.spec("PIPE-GATES-R073")
def test_down_refuses_while_a_slot_is_held() -> None:
    runtime = FakeRuntime(locks={"alpha-2": ["job-41"]})
    findings = lifecycle.down(config(), runtime)
    assert findings == ["alpha-2: held by a running job; pass the force flag to scale down anyway"]
    assert runtime.disabled == set() and runtime.dropped == set()


@pytest.mark.spec("PIPE-GATES-R073")
def test_forced_down_disables_and_drops_caches(tmp_path) -> None:
    runtime = FakeRuntime(locks={"alpha-2": ["job-41"]})
    assert lifecycle.down(config(), runtime, force=True) == []
    assert runtime.disabled == runtime.dropped == {"alpha-1", "alpha-2", "beta-1"}
    idle = FakeRuntime()
    path = tmp_path / "slots.toml"
    path.write_text(CONFIG_TEXT, encoding="utf-8")
    assert main(["down", "--config", str(path)], runtime_factory=lambda _c: idle) == 0
    held = FakeRuntime(locks={"beta-1": ["x"]})
    assert main(["down", "--config", str(path)], runtime_factory=lambda _c: held) == 1
    assert main(["down", "--config", str(path), "--force"], runtime_factory=lambda _c: held) == 0


@pytest.mark.spec("PIPE-GATES-R073")
def test_upgrade_installs_the_version_on_every_host(tmp_path, capsys) -> None:
    runtime = FakeRuntime()
    assert lifecycle.upgrade(config(), runtime, rust="1.97.0") == []
    assert runtime.calls == [
        ("install", "alpha.example.invalid:rust:1.97.0"),
        ("install", "beta.example.invalid:rust:1.97.0"),
    ]
    failing = FakeRuntime(bad_hosts={"beta.example.invalid"})
    assert lifecycle.upgrade(config(), failing, rust="1.97.0", python="3.15") == [
        "beta.example.invalid: rust 1.97.0 failed: unreachable",
        "beta.example.invalid: python 3.15 failed: unreachable",
    ]
    with pytest.raises(CannotRun, match="rust or python"):
        lifecycle.upgrade(config(), runtime)
    path = tmp_path / "slots.toml"
    path.write_text(CONFIG_TEXT, encoding="utf-8")
    assert main(["upgrade", "--config", str(path), "--rust", "1.97.0"], runtime_factory=lambda _c: FakeRuntime()) == 0
    assert main(["upgrade", "--config", str(path), "--rust", "1.97.0"], runtime_factory=lambda _c: failing) == 1
    assert "beta.example.invalid" in capsys.readouterr().out


def test_the_ssh_adapter_issues_the_slot_commands_and_refuses_an_unsafe_path() -> None:
    sent: list[tuple[str, tuple[str, ...]]] = []

    def run(host, argv):
        sent.append((host, tuple(argv)))
        return 0, "Avail\n  900\n" if argv[0] == "df" else ""

    runtime = lifecycle.SshHostRuntime(run=run)
    slot = lifecycle.slots_of(config())[0]
    assert runtime.free_disk_bytes(slot) == 900
    runtime.drop_caches(slot)
    assert sent[-1] == (
        "alpha.example.invalid",
        (
            "rm",
            "-rf",
            "/var/lib/warm-slots/alpha/slot-1/target",
            "/var/lib/warm-slots/alpha/slot-1/runs",
            "/var/lib/warm-slots/alpha/slot-1/sccache",
        ),
    )
    unsafe = lifecycle.Slot(slot.pool.__class__(**{**slot.pool.__dict__, "cache_root": "/tmp"}), 1)
    with pytest.raises(CannotRun, match="unsafe cache path"):
        runtime.drop_caches(unsafe)
    assert json.dumps(sent)
