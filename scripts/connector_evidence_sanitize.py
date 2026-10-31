"""Neutralize personal identity in captured connector evidence fixtures (PIPE-GATES-R016.118).

Consumer-train evidence (``tests/fixtures/connector_spec_delivery/*.json``) snapshots
connector source files, generated status and hosted-run receipts. This repository is
public, so a capture never persists who authored a file or a commit: skill
``author:`` metadata, ``[[project.authors]]`` entries and commit ``author`` objects
become the neutral maintainer identity, and every content digest that covers a
rewritten file (``sha256``, ``bytes``, ``git_blob_sha``, ``status_file_sha256``) is
recomputed so the evidence stays self-consistent.

Run it on every capture before committing it:

    python scripts/connector_evidence_sanitize.py tests/fixtures/connector_spec_delivery/*.json tests/test_connector_consumer_*.py

A digest that pins a rewritten file anywhere in the evidence (or in a consumer test module)
follows the new content, with the byte count beside it.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

NEUTRAL_NAME = "Repository Maintainers"
NEUTRAL_EMAIL = "maintainers@example.invalid"

_SKILL_AUTHOR = re.compile(r"(?m)^(?P<indent>[ \t]*)author:[ \t]*(?!Repository Maintainers$)\S.*$")
_TOML_AUTHORS = re.compile(r"(?ms)^\[\[project\.authors\]\]\n(?P<body>(?:(?!^\[).)*)")
_TOML_FIELD = re.compile(r'(?m)^(?P<key>name|email)[ \t]*=[ \t]*"[^"\n]*"')


def sanitize_text(text: str) -> str:
    """The text with skill and package author identity replaced by the neutral maintainer."""
    if text.startswith("---\n") and (end := text.find("\n---", 3)) > 0:
        # Only YAML front matter carries a skill's `author:`; body text and code are left as captured.
        front = _SKILL_AUTHOR.sub(lambda m: f"{m.group('indent')}author: {NEUTRAL_NAME}", text[:end])
        text = front + text[end:]

    def _authors(match: re.Match[str]) -> str:
        body = _TOML_FIELD.sub(
            lambda f: f'{f.group("key")} = "{NEUTRAL_NAME if f.group("key") == "name" else NEUTRAL_EMAIL}"',
            match.group("body"),
        )
        return "[[project.authors]]\n" + body

    return _TOML_AUTHORS.sub(_authors, text)


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


class Remap:
    """Old -> new digests (and byte counts) of every rewritten file, applied across all evidence."""

    def __init__(self) -> None:
        self.digests: dict[str, str] = {}
        self.sizes: dict[str, tuple[int, int]] = {}

    def record(self, old: str, new: str, sizes: tuple[int, int]) -> None:
        if old != new:
            self.digests[old] = new
            self.sizes[old] = sizes

    def content(self, node: dict[str, Any]) -> None:
        old = node["content"].encode("utf-8")
        clean = sanitize_text(node["content"])
        if clean == node["content"]:
            return
        node["content"] = clean
        self._rewritten(old, clean.encode("utf-8"))

    def encoded(self, node: dict[str, Any]) -> None:
        """A base64 ``data`` record of a UTF-8 text file (binary data is left as captured)."""
        try:
            old = base64.b64decode(node["data"], validate=True)
            text = old.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return
        clean = sanitize_text(text)
        if clean != text:
            node["data"] = base64.b64encode(clean.encode("utf-8")).decode("ascii")
            self._rewritten(old, clean.encode("utf-8"))

    def _rewritten(self, old: bytes, new: bytes) -> None:
        sizes = (len(old), len(new))
        self.record(hashlib.sha256(old).hexdigest(), hashlib.sha256(new).hexdigest(), sizes)
        self.record(_git_blob_sha(old), _git_blob_sha(new), sizes)

    def status(self, node: dict[str, Any]) -> None:
        sources = node.get("status_source")
        if not isinstance(sources, dict):
            return
        for relative, content in list(sources.items()):
            if isinstance(content, str) and (clean := sanitize_text(content)) != content:
                sources[relative] = clean
                old, new = content.encode("utf-8"), clean.encode("utf-8")
                self.record(hashlib.sha256(old).hexdigest(), hashlib.sha256(new).hexdigest(), (len(old), len(new)))


def _neutral_person(node: dict[str, Any]) -> dict[str, Any]:
    node = {k: v for k, v in node.items() if k != "username"}
    if "name" in node:
        node["name"] = NEUTRAL_NAME
    if "email" in node:
        node["email"] = NEUTRAL_EMAIL
    return node


def _rewrite(node: Any, remap: Remap, key: str = "") -> Any:
    """Phase 1: neutralize identities, collecting the digest of every rewritten file."""
    if isinstance(node, list):
        return [_rewrite(item, remap, key) for item in node]
    if not isinstance(node, dict):
        return node
    if key in {"author", "committer"} and set(node) <= {"name", "email", "username", "date"}:
        return _neutral_person(node)
    out = {k: _rewrite(v, remap, k) for k, v in node.items()}
    if isinstance(out.get("content"), str):
        remap.content(out)
    if out.get("encoding") == "base64" and isinstance(out.get("data"), str):
        remap.encoded(out)
    remap.status(out)
    return out


def _redigest(node: Any, remap: Remap) -> Any:
    """Phase 2: every digest of a rewritten file, and the byte count beside it, follows the new content."""
    if isinstance(node, list):
        return [_redigest(item, remap) for item in node]
    if isinstance(node, str):
        return remap.digests.get(node, node)
    if not isinstance(node, dict):
        return node
    sizes = {remap.sizes[v] for v in node.values() if isinstance(v, str) and v in remap.sizes}
    out = {}
    for k, v in node.items():
        size = next((new for old, new in sizes if v == old), None) if isinstance(v, int) and "bytes" in k else None
        out[k] = size if size is not None else _redigest(v, remap)
    return out


def sanitize_text_file(path: Path, remap: Remap) -> bool:
    """Carry the digest remap into a test module that pins evidence digests and sizes."""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    for index, line in enumerate(lines):
        for old, new in remap.digests.items():
            if old in line:
                lines[index] = line = line.replace(old, new)
                before, after = remap.sizes[old]
                for near in range(max(0, index - 3), min(len(lines), index + 4)):
                    lines[near] = re.sub(rf"(bytes\"?\s*[:=]\s*){before}\b", rf"\g<1>{after}", lines[near])
    clean = "\n".join(lines)
    if clean == text:
        return False
    path.write_text(clean, encoding="utf-8")
    return True


def _serialize(document: Any, raw: str) -> str:
    indent = 1 if raw.startswith('{\n "') else 2
    return json.dumps(document, indent=indent, ensure_ascii=raw.isascii()) + "\n"


def sanitize_paths(fixtures: list[Path], modules: list[Path]) -> list[Path]:
    """Sanitize every fixture, then carry the digest remap through all fixtures and test modules.

    A fixture whose own file digest is pinned by another fixture (a shard descriptor) changes that
    digest too, so the remap is re-applied until no file changes any more.
    """
    remap = Remap()
    raws = {path: path.read_text(encoding="utf-8") for path in fixtures}
    documents = {path: _rewrite(json.loads(raw), remap) for path, raw in raws.items()}
    texts = dict(raws)
    while True:
        known = len(remap.digests)
        for path, raw in raws.items():
            documents[path] = _redigest(documents[path], remap)
            text = _serialize(documents[path], raw) if documents[path] != json.loads(raw) else raw
            texts[path] = text
            old, new = raw.encode("utf-8"), text.encode("utf-8")
            remap.record(hashlib.sha256(old).hexdigest(), hashlib.sha256(new).hexdigest(), (len(old), len(new)))
        if len(remap.digests) == known:
            break
    changed = []
    for path, raw in raws.items():
        if texts[path] != raw:
            path.write_text(texts[path], encoding="utf-8")
            changed.append(path)
    changed += [path for path in modules if sanitize_text_file(path, remap)]
    return changed


def main(argv: list[str]) -> int:
    paths = [Path(arg) for arg in argv]
    fixtures = [path for path in paths if path.suffix == ".json"]
    modules = [path for path in paths if path.suffix == ".py"]
    for path in sanitize_paths(fixtures, modules):
        print(f"sanitized {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
