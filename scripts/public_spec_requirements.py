"""Validate the per-requirement delivery register in a public ``status.json``."""

from __future__ import annotations

from pathlib import Path

from scripts.public_spec_status import DELIVERY, _load_status, _merged_head, _valid_evidence


def _entry_errors(path: Path, entry: dict, defined: str) -> list[str]:
    """One requirement entry: a title, a state, public receipts and a definition."""
    label = f"{path}: {entry.get('id')}"
    errors: list[str] = []
    valid = _valid_evidence(path, entry, errors)
    state = entry.get("delivery_state")
    if state not in DELIVERY or not entry.get("title"):
        errors.append(f"{label}: title and delivery state required")
    if state in {"LANDED", "CLOSED"} and not _merged_head(valid):
        errors.append(f"{label}: merged-head evidence required")
    if f"`{entry.get('id')}`" not in defined:
        errors.append(f"{label}: missing from requirements.md")
    return errors


def _hand_written_entries(data: dict | None) -> object:
    """Requirement entries to check here, or ``None`` when there are none.

    Schema 2 entries are generated and gated by ``pipelines-hook spec-status``.
    """
    if not data or data.get("schema_version") == 2:
        return None
    return data.get("requirements")


def requirement_errors(path: Path) -> list[str]:
    """Per-requirement delivery entries match the declared IDs, in order."""
    data, _failure = _load_status(path)
    entries = _hand_written_entries(data)
    if entries is None:
        return []
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        return [f"{path}: requirements must be an array of objects"]
    errors = []
    if [entry.get("id") for entry in entries] != data.get("requirement_ids"):
        errors.append(f"{path}: requirements must match requirement IDs in order")
    register = path.parent / "requirements.md"
    defined = register.read_text(encoding="utf-8") if register.is_file() else ""
    for entry in entries:
        errors.extend(_entry_errors(path, entry, defined))
    return errors
