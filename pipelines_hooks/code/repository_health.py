"""Deterministic repository health over measured analyzer receipts.

Scored categories (dead code, secrets, dependency risk, complexity hotspots, untested surfaces)
carry positive integer weights; lint, import-order and type are required code phases whose
failures set the verdict and head the fix list but never enter the arithmetic.  Each adapter
declares its version, scope, rules, severity mapping, requiredness and evidence kind and reads
a receipt of one measured run.  A stale or malformed receipt, an unknown severity, a missing
required adapter or dependency-risk evidence that is not an advisory match is ``CannotRun``;
an unchecked scored category makes the score unavailable, never zero.  Secret values never
enter a report: adapters keep only location, rule and an evidence digest.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.validation_report import (
    CheckRecord,
    Counts,
    Evidence,
    HealthCategory,
    HealthFix,
    HealthSummary,
    RuleRecord,
)
from pipelines_hooks.supply_chain.finding import Finding

POLICY_VERSION = 1
SCORED = ("dead-code", "secrets", "dependency-risk", "complexity", "untested")
UNSCORED = ("lint", "import-order", "type")
SEVERITIES = ("critical", "high", "medium", "low")
EVIDENCE_KINDS = {
    "dead-code": "candidate",
    "secrets": "measured",
    "dependency-risk": "advisory",
    "complexity": "measured",
    "untested": "coverage",
}


@dataclass(frozen=True)
class Adapter:
    category: str
    version: str
    scope: tuple[str, ...]
    rules: tuple[str, ...]
    severity_map: dict[str, str]
    required: bool
    evidence_kind: str
    receipt: str


@dataclass(frozen=True)
class HealthPolicy:
    weights: dict[str, int]
    penalties: dict[str, int]
    block_at: str
    adapters: tuple[Adapter, ...]


def load_policy(path: Path) -> HealthPolicy:
    try:
        table = tomllib.loads(path.read_text(encoding="utf-8"))
        if table["version"] != POLICY_VERSION:
            raise ValueError("unsupported version")
        weights = {k: v for k, v in table["weights"].items()}
        penalties = dict(table["penalties"])
        adapters = tuple(
            Adapter(
                a["category"],
                a["version"],
                tuple(a["scope"]),
                tuple(a["rules"]),
                dict(a["severity_map"]),
                bool(a.get("required", True)),
                a["evidence_kind"],
                a["receipt"],
            )
            for a in table["adapters"]
        )
        block_at = table.get("block_at", "high")
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as exc:
        raise CannotRun(f"{path.name}: health policy is unreadable: {exc!r}") from exc
    if set(weights) != set(SCORED) or any(
        isinstance(w, bool) or not isinstance(w, int) or w < 1 for w in weights.values()
    ):
        raise CannotRun(f"{path.name}: weights must be positive integers for exactly {list(SCORED)}")
    if set(penalties) != set(SEVERITIES) or any(not isinstance(p, int) or p < 0 for p in penalties.values()):
        raise CannotRun(f"{path.name}: penalties must be nonnegative integers for {list(SEVERITIES)}")
    if block_at not in SEVERITIES:
        raise CannotRun(f"{path.name}: block_at must be one of {list(SEVERITIES)}")
    for adapter in adapters:
        if adapter.category not in SCORED:
            raise CannotRun(f"{path.name}: adapter category {adapter.category!r} is not a scored category")
        if not set(adapter.severity_map.values()) <= set(SEVERITIES):
            raise CannotRun(f"{path.name}: adapter {adapter.category} maps to an unknown severity")
    return HealthPolicy(weights, penalties, block_at, adapters)


def supply_chain_receipt(findings: list[Finding], *, snapshot: str, version: str) -> dict[str, object]:
    """Adapt supply-chain gate findings to the receipt shape; the message (which may hold a value) is dropped."""
    return {
        "snapshot": snapshot,
        "version": version,
        "findings": [{"rule": f.rule, "severity": "high", "path": f.path, "line": f.line or None} for f in findings],
    }


def _read(adapter: Adapter, root: Path, snapshot: str) -> list[dict[str, object]] | None:
    path = root / adapter.receipt
    if not path.is_file():
        if adapter.required:
            raise CannotRun(f"health adapter {adapter.category}: required receipt {adapter.receipt} is missing")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        found, bound, version = list(data["findings"]), data["snapshot"], data["version"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CannotRun(f"health adapter {adapter.category}: malformed receipt {adapter.receipt}: {exc!r}") from exc
    if bound != snapshot or version != adapter.version:
        raise CannotRun(f"health adapter {adapter.category}: stale receipt (snapshot {bound!r}, adapter {version!r})")
    if adapter.category == "dependency-risk" and adapter.evidence_kind != "advisory":
        raise CannotRun("dependency-risk needs advisory evidence; dependency-format checks are not vulnerability proof")
    return found


def evaluate(
    root: Path, policy: HealthPolicy, snapshot: str, required_phases: Mapping[str, Counts | None]
) -> tuple[list[CheckRecord], HealthSummary]:
    checks: list[CheckRecord] = []
    categories: dict[str, HealthCategory] = {}
    fixes: list[tuple[tuple[object, ...], HealthFix]] = []
    adapters = {a.category: a for a in policy.adapters}
    for category in SCORED:
        adapter = adapters.get(category)
        weight = policy.weights[category]
        if adapter is None:
            categories[category] = HealthCategory(status="unchecked", weight=weight, reason="no adapter declared")
            continue
        raw = _read(adapter, root, snapshot)
        if raw is None:
            categories[category] = HealthCategory(
                status="skipped", weight=weight, reason="optional adapter has no receipt"
            )
            continue
        seen: set[tuple[object, ...]] = set()
        by_rule: dict[str, list[tuple[str, Evidence]]] = {}
        for item in raw:
            try:
                rule, original, path = str(item["rule"]), str(item["severity"]), str(item["path"])
            except KeyError as exc:
                raise CannotRun(f"health adapter {category}: finding without {exc}") from exc
            if rule not in adapter.rules:
                raise CannotRun(f"health adapter {category}: finding for undeclared rule {rule!r}")
            severity = adapter.severity_map.get(original) or (original if original in SEVERITIES else None)
            if severity is None:
                raise CannotRun(f"health adapter {category}: unknown severity {original!r} for rule {rule}")
            line = item.get("line")
            key = (category, rule, path, line, item.get("digest"))
            if key in seen:
                continue
            seen.add(key)
            evidence = Evidence(
                path=path,
                line=line if isinstance(line, int) and line > 0 else None,
                observed=str(item.get("digest", "")) or None,
                detail=f"{severity} ({adapter.evidence_kind})",
            )
            by_rule.setdefault(rule, []).append((severity, evidence))
            blocking = SEVERITIES.index(severity) <= SEVERITIES.index(policy.block_at)
            fixes.append(
                (
                    (not blocking, SEVERITIES.index(severity), category, path, line or 0, rule),
                    HealthFix(
                        rank=1,
                        category=category,
                        rule=rule,
                        severity=severity,
                        blocking=blocking,
                        path=path,
                        line=line if isinstance(line, int) and line > 0 else None,
                        suggestion=f"resolve {rule} at {path}",
                    ),
                )
            )
        records = []
        for rule in adapter.rules:
            items = by_rule.get(rule, [])
            blocked = [e for s, e in items if SEVERITIES.index(s) <= SEVERITIES.index(policy.block_at)]
            if blocked:
                records.append(
                    RuleRecord(
                        rule=rule,
                        outcome="fail",
                        reason=f"{len(blocked)} blocking finding(s)",
                        evidence=tuple(e for _, e in items),
                    )
                )
            else:
                records.append(
                    RuleRecord(
                        rule=rule,
                        outcome="pass",
                        reason=f"{len(items)} non-blocking finding(s) scored",
                        evidence=tuple(e for _, e in items),
                    )
                )
        checks.append(
            CheckRecord(
                category=category,
                identity=f"{category}@{adapter.version}",
                required=adapter.required,
                scope=adapter.scope,
                rules=tuple(records),
                policy_digest=adapter.evidence_kind,
            )
        )
        penalty = sum(policy.penalties[s] for items in by_rule.values() for s, _ in items)
        categories[category] = HealthCategory(
            status="measured",
            weight=weight,
            findings=sum(len(v) for v in by_rule.values()),
            penalty=penalty,
            score=max(0, 100 - penalty),
        )
    measured = [c for c in categories.values() if c.status == "measured"]
    available = len(measured) == len(SCORED)
    total = sum(policy.weights.values())
    score = round(sum((c.weight or 0) * (c.score or 0) for c in measured) / total) if available else None
    ordered = [fix.model_copy(update={"rank": i}) for i, (_, fix) in enumerate(sorted(fixes, key=lambda p: p[0]), 1)]
    summary = HealthSummary(
        policy_version=POLICY_VERSION,
        weights=policy.weights,
        penalties=policy.penalties,
        score=score,
        score_available=available,
        coverage=len(measured) / len(SCORED),
        categories=categories,
        unscored={name: required_phases.get(name) for name in UNSCORED},
        fixes=tuple(ordered),
    )
    return checks, summary
