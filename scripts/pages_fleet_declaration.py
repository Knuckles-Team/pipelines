"""Version-one offline fleet input; declaration ownership remains an activation decision."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pipelines_hooks.core.gitenv import git_text, repo_root
from scripts.readiness.filesystem import _path_parts, _safe_existing_path
from scripts.readiness.urls import _public_url


class ParityError(ValueError):
    """A stable, privacy-safe reason why exact-ref parity is unverified."""


def canonical(value: object) -> str:
    """Stable JSON without machine paths or wall-clock data."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fields(value: object, required: set[str], optional: set[str] = frozenset()) -> None:
    if not isinstance(value, dict):
        raise ParityError("declaration-object-required")
    if not required <= value.keys() or value.keys() - required - optional:
        raise ParityError("declaration-fields-invalid")


def identity(value: dict) -> None:
    repository = value["repository"]
    revision = value["revision"]
    if not isinstance(repository, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repository
    ):
        raise ParityError("repository-invalid")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ParityError("immutable-revision-required")


def consumer(value: object) -> None:
    fields(value, {"repository", "revision", "content_source", "shared_theme_enabled"}, {"site_url"})
    identity(value)
    parts = _path_parts(value["content_source"], "content-source")
    if "/".join(parts) != value["content_source"]:
        raise ParityError("content-source-not-canonical")
    if type(value["shared_theme_enabled"]) is not bool:
        raise ParityError("shared-theme-boolean-required")
    if "site_url" in value:
        _public_url(value["site_url"], "site")


def validate(value: object) -> dict:
    """Reject unknown fields, ambiguous identities and mutable refs before resolution."""
    fields(value, {"schema_version", "pipeline", "consumers"})
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ParityError("schema-version-unsupported")
    fields(value["pipeline"], {"repository", "revision"})
    identity(value["pipeline"])
    consumers = value["consumers"]
    if not isinstance(consumers, list) or not consumers:
        raise ParityError("consumers-required")
    seen = set()
    for item in consumers:
        consumer(item)
        name = item["repository"].lower()
        if name in seen:
            raise ParityError("duplicate-consumer")
        seen.add(name)
    return value


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ParityError("duplicate-json-key")
    return value


def object_git(root: Path, args: list[str]) -> str:
    """Read original objects without replacement refs, fsmonitor hooks or index writes."""
    return git_text(root, ["--no-replace-objects", "--no-optional-locks", "--literal-pathspecs",
                           "-c", "core.fsmonitor=false", *args])


def load(path: Path) -> dict:
    """Only a tracked, committed declaration can supply fleet input to the CLI."""
    root = repo_root(path.parent)
    relative = path.absolute().relative_to(root).as_posix()
    _safe_existing_path(root, relative, "declaration")
    object_git(root, ["ls-files", "--error-unmatch", "--", relative])
    if object_git(root, ["status", "--porcelain", "--", relative]):
        raise ParityError("declaration-overlay")
    text = object_git(root, ["show", f"HEAD:{relative}"])
    return validate(json.loads(text, object_pairs_hook=unique_object))
