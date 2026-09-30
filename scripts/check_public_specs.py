"""Validate pipeline-owned public specs without network or live environments."""

from __future__ import annotations

import re
import sys
from importlib import import_module
from pathlib import Path
from urllib.parse import unquote, urlsplit

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

status_errors = import_module("scripts.public_spec_status").status_errors

FILES = ("spec.md", "plan.md", "test-spec.md", "tasks.md", "status.json")
PRIVATE = re.compile(r"plans/|gitlab|homelab|(?:file://|/(?:home|Users|tmp|workspace)/)|\.arpa\b", re.I)
LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


def document_errors(root: Path, path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    errors = []
    if len(content.strip()) < 120:
        errors.append(f"{path}: incomplete document")
    if PRIVATE.search(content):
        errors.append(f"{path}: private or local reference")
    for target in LINK.findall(content):
        url = urlsplit(target)
        if url.scheme:
            if url.scheme != "https" or url.hostname is None:
                errors.append(f"{path}: non-public URL")
            continue
        if target.startswith("#"):
            continue
        local = (path.parent / unquote(url.path)).resolve()
        if not local.is_relative_to(root.resolve()) or not local.exists():
            errors.append(f"{path}: broken local link {target}")
    return errors


def _template_errors(specs: Path) -> list[str]:
    template = specs / "_template"
    return [f"{template / filename}: missing template file" for filename in FILES if not (template / filename).is_file()]


def _feature_file_errors(root: Path, feature: Path, index: str) -> list[str]:
    errors = []
    for filename in FILES:
        path = feature / filename
        if not path.is_file():
            errors.append(f"{path}: missing owner contract")
        elif filename != "status.json":
            errors.extend(document_errors(root, path))
    if f"]({feature.name}/spec.md)" not in index:
        errors.append(f"{feature}: absent from index")
    return errors


def _ownership_errors(status: Path, used: set[str], spec_ids: set[str]) -> list[str]:
    """Status errors plus spec-ID and requirement-owner uniqueness across features."""
    errors, ids, spec_id = status_errors(status)
    if spec_id in spec_ids:
        errors.append(f"{status}: duplicate spec ID {spec_id}")
    spec_ids.add(spec_id)
    for item in ids:
        if item in used:
            errors.append(f"{status}: duplicate requirement owner {item}")
        used.add(item)
    return errors


def problems(root: Path) -> list[str]:
    specs = root / "specs"
    errors = _template_errors(specs)
    index = (specs / "README.md").read_text(encoding="utf-8")
    used: set[str] = set()
    spec_ids: set[str] = set()
    for feature in sorted(path for path in specs.iterdir() if path.is_dir() and path.name != "_template"):
        errors.extend(_feature_file_errors(root, feature, index))
        status = feature / "status.json"
        if status.is_file():
            errors.extend(_ownership_errors(status, used, spec_ids))
    errors.extend(document_errors(root, specs / "README.md"))
    return errors


def main() -> int:
    errors = problems(Path(__file__).resolve().parents[1])
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Public pipeline specs are structurally complete and self-contained.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
