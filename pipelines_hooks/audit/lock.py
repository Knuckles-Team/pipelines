"""Parse a bounded ``uv.lock`` into exact PyPI package/version pairs."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

MAX_LOCK_BYTES = 64 * 1024 * 1024
MAX_PACKAGES = 10_000
PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class AuditError(RuntimeError):
    """Stable audit failure that omits endpoints, credentials and local paths."""


def normalise_package(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _artifacts(item: dict[str, Any]) -> list[Any]:
    wheels = item.get("wheels", [])
    if not isinstance(wheels, list):
        raise AuditError("dependency lock artifact inventory is invalid")
    artifacts = ([item["sdist"]] if "sdist" in item else []) + wheels
    if not artifacts:
        raise AuditError("dependency lock registry package has no hashed artifact")
    return artifacts


def _verified_artifact(artifact: object) -> bool:
    if not isinstance(artifact, dict):
        return False
    url, digest = artifact.get("url"), artifact.get("hash")
    return isinstance(url, str) and url.startswith("https://") and isinstance(digest, str) and bool(SHA256_RE.fullmatch(digest))


def _validate_registry_artifacts(item: dict[str, Any]) -> None:
    source = item.get("source")
    if not isinstance(source, dict) or "registry" not in source:
        return
    if not isinstance(source["registry"], str) or not source["registry"].startswith("https://"):
        raise AuditError("dependency lock contains an insecure registry source")
    if not all(_verified_artifact(artifact) for artifact in _artifacts(item)):
        raise AuditError("dependency lock contains an unverified artifact")


def _read_document(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise AuditError("dependency lock is unreadable") from None
    if size <= 0 or size > MAX_LOCK_BYTES or path.is_symlink():
        raise AuditError("dependency lock is unavailable or exceeds its safe bound")
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise AuditError("dependency lock is unreadable") from None


def _resolved(item: object) -> tuple[str, str] | None:
    if not isinstance(item, dict):
        raise AuditError("dependency lock package inventory is invalid")
    _validate_registry_artifacts(item)
    source, name, version = item.get("source"), item.get("name"), item.get("version")
    if not isinstance(source, dict) or "registry" not in source or not isinstance(name, str) or not isinstance(version, str):
        return None
    name = normalise_package(name)
    if not PACKAGE_RE.fullmatch(name) or not version or len(version) > 128:
        raise AuditError("dependency lock contains an invalid package identity")
    return name, version


def parse_lock(path: Path) -> tuple[tuple[str, str], ...]:
    """Every exact registry package/version pair (uv may select several per marker)."""
    packages = _read_document(path).get("package")
    if not isinstance(packages, list) or len(packages) > MAX_PACKAGES:
        raise AuditError("dependency lock package inventory is invalid")
    resolved = {pair for pair in (_resolved(item) for item in packages) if pair is not None}
    if not resolved:
        raise AuditError("dependency lock contains no auditable packages")
    return tuple(sorted(resolved))
