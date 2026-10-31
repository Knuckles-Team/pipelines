"""Evaluate the ordered changeset migration waves (PIPE-GATES-R006.1-.4).

The evaluator consumes a receipt ledger, rather than treating a status flag as
evidence.  A wave-one receipt contains twenty ``source.land`` changesets, and
each changeset binds the mirror tree hash to its changeset tree hash.  It also
records the ``PIPE-GATES-R002`` auto-revert rehearsal and the observed period
with no mirror divergence.  Later waves reuse that same exit contract for the
repositories they move.  Missing, malformed, or contradictory receipts are
findings, so an incomplete ledger cannot qualify a wave.

The ledger shape is deliberately small and serialisable::

    {
        "verified_specs": ["MEDULLA-SCM-R001", ...],
        "waves": {"1": {"changesets": [...],
                         "auto_revert_rehearsal": {
                             "gate_id": "PIPE-GATES-R002", "result": "passed"
                         },
                         "mirror_no_divergence_days": 7}},
        "connectors": [{"name": "small", "wave": 2, "source_lines": 42,
                        ...wave-one fields..., "release_tree_hash": "..."}],
        "repositories": [{"name": "pipelines", "wave": 4,
                           ...wave-one fields...}]
    }

The module does not fetch repositories or infer historical migration claims;
callers must supply the receipts produced by the migration system.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pipelines_hooks.core.errors import CannotRun

_WAVES = frozenset({"1", "2", "3", "4"})
_CHANGESETS_PER_EXIT = 20
_MIN_NO_DIVERGENCE_DAYS = 7
_TREE_HASH = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")

_WAVE_ONE_ENTRY = frozenset(
    {
        "MEDULLA-SCM-R001",
        "MEDULLA-SCM-R002",
        "MEDULLA-SCM-R003",
        "MEDULLA-SCM-R004",
        "MEDULLA-SCM-R010",
        "RM-SCM-R001",
        "RM-SCM-R002",
        "ARBORA-OPS-R848.2",
        "ARBORA-OPS-R849",
    }
)
_WAVE_FOUR_REPOSITORIES = ("universal-skills", "pipelines", "Overstory", "Tuig", "Axil")


@dataclass(frozen=True)
class WaveResult:
    """One wave's deterministic verdict and its actionable findings."""

    wave: str
    findings: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Whether every entry and exit criterion had a valid receipt."""

        return not self.findings


def _mapping(value: object, label: str, findings: list[str]) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        findings.append(f"{label}: expected an object")
        return None
    return value


def _strings(value: object, label: str, findings: list[str]) -> set[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        findings.append(f"{label}: expected a list of strings")
        return set()
    values = list(value)
    if any(not isinstance(item, str) or not item for item in values):
        findings.append(f"{label}: expected a list of non-empty strings")
        return set()
    return set(values)


def _record(ledger: Mapping[str, object], key: str, findings: list[str]) -> Mapping[str, object] | None:
    waves = _mapping(ledger.get("waves"), "waves", findings)
    if waves is None:
        return None
    value = waves.get(key)
    return _mapping(value, f"waves[{key!r}]", findings)


def _require_specs(ledger: Mapping[str, object], required: set[str], label: str, findings: list[str]) -> None:
    verified = _strings(ledger.get("verified_specs"), "verified_specs", findings)
    missing = sorted(required - verified)
    if missing:
        findings.append(f"{label}: missing verified prerequisite(s): {', '.join(missing)}")


def _hash(value: object, label: str, findings: list[str]) -> str | None:
    if not isinstance(value, str) or _TREE_HASH.fullmatch(value) is None:
        findings.append(f"{label}: expected a 40- or 64-character lowercase tree hash")
        return None
    return value


def _wave_one_exit(record: Mapping[str, object], label: str) -> list[str]:
    """Check the reusable exit contract for one migration scope."""

    findings: list[str] = []
    raw_changesets = record.get("changesets")
    if isinstance(raw_changesets, (str, bytes)) or not isinstance(raw_changesets, Sequence):
        findings.append(f"{label}.changesets: expected exactly {_CHANGESETS_PER_EXIT} receipts")
        changesets: list[object] = []
    else:
        changesets = list(raw_changesets)
        if len(changesets) != _CHANGESETS_PER_EXIT:
            findings.append(
                f"{label}.changesets: expected exactly {_CHANGESETS_PER_EXIT} receipts, got {len(changesets)}"
            )

    seen_ids: set[str] = set()
    final_mirror_hash: str | None = None
    for index, raw in enumerate(changesets):
        item = _mapping(raw, f"{label}.changesets[{index}]", findings)
        if item is None:
            continue
        changeset_id = item.get("id")
        if not isinstance(changeset_id, str) or not changeset_id:
            findings.append(f"{label}.changesets[{index}].id: required")
        elif changeset_id in seen_ids:
            findings.append(f"{label}.changesets[{index}].id: duplicate {changeset_id!r}")
        else:
            seen_ids.add(changeset_id)
        if item.get("landed_via") != "source.land":
            findings.append(f"{label}.changesets[{index}].landed_via: expected 'source.land'")
        tree_hash = _hash(item.get("tree_hash"), f"{label}.changesets[{index}].tree_hash", findings)
        mirror_hash = _hash(item.get("mirror_tree_hash"), f"{label}.changesets[{index}].mirror_tree_hash", findings)
        if index == len(changesets) - 1:
            final_mirror_hash = mirror_hash
        if tree_hash is not None and mirror_hash is not None and tree_hash != mirror_hash:
            findings.append(f"{label}.changesets[{index}]: mirror tree hash differs from changeset tree hash")

    declared_mirror_hash = _hash(record.get("mirror_tree_hash"), f"{label}.mirror_tree_hash", findings)
    if declared_mirror_hash is not None and final_mirror_hash is not None and declared_mirror_hash != final_mirror_hash:
        findings.append(f"{label}: declared mirror tree hash differs from the final changeset mirror hash")

    rehearsal = _mapping(record.get("auto_revert_rehearsal"), f"{label}.auto_revert_rehearsal", findings)
    if rehearsal is not None:
        if rehearsal.get("gate_id") != "PIPE-GATES-R002":
            findings.append(f"{label}.auto_revert_rehearsal.gate_id: expected 'PIPE-GATES-R002'")
        if rehearsal.get("result") != "passed":
            findings.append(f"{label}.auto_revert_rehearsal.result: expected 'passed'")

    no_divergence_days = record.get("mirror_no_divergence_days")
    if type(no_divergence_days) is not int or no_divergence_days < _MIN_NO_DIVERGENCE_DAYS:
        findings.append(f"{label}.mirror_no_divergence_days: expected an integer >= {_MIN_NO_DIVERGENCE_DAYS}")
    return findings


def _records(ledger: Mapping[str, object], key: str, findings: list[str]) -> list[Mapping[str, object]]:
    raw = ledger.get(key)
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        findings.append(f"{key}: expected a non-empty list")
        return []
    result: list[Mapping[str, object]] = []
    for index, item in enumerate(raw):
        parsed = _mapping(item, f"{key}[{index}]", findings)
        if parsed is not None:
            result.append(parsed)
    if not result:
        findings.append(f"{key}: expected a non-empty list")
    return result


def _entry_result(ledger: Mapping[str, object], wave: str) -> list[str]:
    """Evaluate all preceding wave exits needed before ``wave`` can start."""

    if wave == "1":
        return []
    previous = evaluate_wave(str(int(wave) - 1), ledger)
    return [f"entry prerequisite {previous.wave}: {finding}" for finding in previous.findings]


def evaluate_wave(wave: str, ledger: Mapping[str, object]) -> WaveResult:
    """Evaluate one of the first four ordered migration waves.

    The result is a refusal when a prerequisite receipt is absent or any
    receipt contradicts the wave contract.  ``wave`` is a string because it
    mirrors the JSON ledger keys; unsupported values are caller errors.
    """

    if wave not in _WAVES:
        raise CannotRun(f"migration waves: unsupported wave {wave!r}; supported waves are 1, 2, 3 and 4")
    if not isinstance(ledger, Mapping):
        raise CannotRun("migration waves: ledger must be an object")

    findings = _entry_result(ledger, wave)
    if wave == "1":
        _require_specs(ledger, set(_WAVE_ONE_ENTRY), "wave 1 entry", findings)
        record = _record(ledger, "1", findings)
        if record is not None:
            findings.extend(_wave_one_exit(record, "waves['1']"))
    elif wave == "2":
        _require_specs(ledger, {"MEDULLA-SCM-R007"}, "wave 2 entry", findings)
        connectors = [item for item in _records(ledger, "connectors", findings) if item.get("wave") == 2]
        if not connectors:
            findings.append("wave 2 exit: no wave-2 connector receipts")
        for index, connector in enumerate(connectors):
            label = f"connectors[wave=2][{index}]"
            lines = connector.get("source_lines")
            if type(lines) is not int or lines < 0 or lines >= 10_000:
                findings.append(f"{label}.source_lines: expected an integer below 10000")
            findings.extend(_wave_one_exit(connector, label))
    elif wave == "3":
        _require_specs(ledger, {"MEDULLA-SCM-R011"}, "wave 3 entry", findings)
        connectors = [item for item in _records(ledger, "connectors", findings) if item.get("wave") == 3]
        if not connectors:
            findings.append("wave 3 exit: no wave-3 connector receipts")
        for index, connector in enumerate(connectors):
            label = f"connectors[wave=3][{index}]"
            findings.extend(_wave_one_exit(connector, label))
            release_hash = _hash(connector.get("release_tree_hash"), f"{label}.release_tree_hash", findings)
            mirror_hash = _hash(connector.get("mirror_tree_hash"), f"{label}.mirror_tree_hash", findings)
            if release_hash is not None and mirror_hash is not None and release_hash != mirror_hash:
                findings.append(f"{label}: release tree differs from mirror tree")
    else:
        _require_specs(ledger, {"PIPE-GATES-R003"}, "wave 4 entry", findings)
        repositories = [item for item in _records(ledger, "repositories", findings) if item.get("wave") == 4]
        by_name: dict[str, list[Mapping[str, object]]] = {}
        for item in repositories:
            name = item.get("name")
            if isinstance(name, str):
                by_name.setdefault(name, []).append(item)
        for name in _WAVE_FOUR_REPOSITORIES:
            rows = by_name.get(name, [])
            if len(rows) != 1:
                findings.append(f"wave 4 exit: expected one receipt for {name!r}, got {len(rows)}")
            for index, repository in enumerate(rows):
                findings.extend(_wave_one_exit(repository, f"repositories[{name!r}][{index}]"))

    return WaveResult(wave=wave, findings=tuple(findings))


__all__ = ["WaveResult", "evaluate_wave"]
