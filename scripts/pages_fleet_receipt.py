"""Deterministic verification and separately timestamped readable presentation."""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.pages_fleet_declaration import canonical, digest


def receipt(verification: dict, *, generated_at: str | None = None, previous: dict | None = None) -> dict:
    """Keep previous evidence immutable; describe its currency against this input."""
    result = {"schema_version": 1, "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
              "verification": verification, "verification_sha256": digest(canonical(verification).encode()),
              "previous": None}
    if previous is not None:
        old = previous["verification"]
        result["previous"] = {"verification_sha256": digest(canonical(old).encode()),
                              "fleet_sha256": old["fleet_sha256"],
                              "status": "historical" if old["fleet_sha256"] != verification["fleet_sha256"] else "same-input"}
    return result


def render_receipt(value: dict) -> str:
    data = value["verification"]
    lines = ["# Offline Pages fleet parity", "", f"Generated: {value['generated_at']}", "",
             f"Result: **{data['status']}** (offline fixtures; public source availability is unverified).",
             f"Fleet SHA-256: `{data['fleet_sha256']}`", f"Pipeline: `{data['pipeline']['revision']}`", "",
             "| Consumer / commit | Tree | Result |", "|---|---|---|"]
    for item in data["consumers"]:
        lines.append(f"| [{item['repository']} / {item['commit']}]({item['commit_url']}) | {item['tree']} | {item['status']} |")
    for item in data["consumers"]:
        lines.append(f"\n## {item['repository']}\n")
        if item["reason"]:
            lines.append(f"\n{item['repository']}: {item['reason']}\n")
        for asset in item["assets"]:
            lines.append(f"\n- `{asset['path']}`: {asset['status']} ({asset['reason'] or 'identical'}); "
                         f"expected `{asset['expected_sha256']}`, actual `{asset['actual_sha256']}`")
    if data["reason"]:
        lines.append(f"\nUnverified: {data['reason']}")
    if value["previous"]:
        lines.append(f"\nPrevious receipt: {value['previous']['status']} ({value['previous']['verification_sha256']})")
    return "\n".join(lines) + "\n"
