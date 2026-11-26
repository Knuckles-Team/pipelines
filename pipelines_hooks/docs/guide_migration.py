"""guide-migration: a large guide is split into declared pages with every block accounted for.

Declared in ``.config/guide-migration.json``: the old guide snapshot, the canonical (concise,
linking) guide, a size limit and one record per source block.  Blocks are the old guide's
paragraphs, headings, tables and fenced code or diagram blocks, identified ``b001`` upward with
a digest.  Each block is ``retained`` (byte-identical in the new guide), ``moved`` (byte-identical
under a destination heading anchor) or ``retired`` (an explicit, reviewed retirement with a
reason).  Moved claims are verified through the documentation claim resolvers; an unknown
factual assertion stays ``unverified`` and blocks a complete-verification receipt (exit 2).
Byte preservation, editorial review and measured verification are separate evidence kinds.
``--render DEST`` writes the reviewable split into a new scratch directory; checking never
rewrites a file.
"""

from __future__ import annotations

import argparse
import os
import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.docs.claims import CLAIM_KINDS, RESOLVERS
from pipelines_hooks.docs.gate_io import Result, finish, load_json, read, require, safe_path, sha, strict_keys
from pipelines_hooks.hygiene.mermaid_rules import validate_block

GATE = "guide-migration"
DECLARATION = ".config/guide-migration.json"
DISPOSITIONS = ("retained", "moved", "retired")
_LINK = re.compile(r"\[[^\]]*\]\((?P<target>[^)#\s]+)(?:#[^)]*)?\)")


@dataclass(frozen=True)
class Claim:
    id: str
    kind: str
    text: str


@dataclass(frozen=True)
class BlockRecord:
    id: str
    digest: str
    disposition: str
    dest: str | None
    anchor: str | None
    review: str | None
    claims: tuple[Claim, ...]


@dataclass(frozen=True)
class GuideMigrationManifest:
    """Old/new snapshots, the canonical guide, the size limit and one record per source block."""

    old: str
    guide: str
    size_limit: int
    records: tuple[BlockRecord, ...]


@dataclass(frozen=True)
class SourceBlock:
    id: str
    kind: str
    text: str
    first: int
    last: int

    @property
    def digest(self) -> str:
        return sha(self.text)


def split_blocks(text: str) -> list[SourceBlock]:
    """Paragraph-level blocks; a fenced block is one block of kind ``code`` or ``diagram``."""
    blocks: list[SourceBlock] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        start = i
        fence = lines[i].startswith("```")
        i += 1
        if fence:
            while i < len(lines) and not lines[i].startswith("```"):
                i += 1
            i += 1
        else:
            while i < len(lines) and lines[i].strip() and not lines[i].startswith("```"):
                i += 1
        kind = "prose"
        if fence:
            kind = "diagram" if lines[start].strip() == "```mermaid" else "code"
        blocks.append(SourceBlock(f"b{len(blocks) + 1:03d}", kind, "\n".join(lines[start:i]), start + 1, i))
    return blocks


def load_manifest(root: Path) -> GuideMigrationManifest:
    data, _ = load_json(GATE, root, DECLARATION)
    data = strict_keys(
        GATE,
        DECLARATION,
        data,
        {"schema", "old", "guide", "size_limit", "blocks"},
        {"schema", "old", "guide", "size_limit", "blocks"},
    )
    if data["schema"] != 1 or not isinstance(data["size_limit"], int) or data["size_limit"] < 1:
        raise CannotRun(f"{GATE}: unsupported schema or size limit")
    records = []
    for raw in data["blocks"]:
        b = strict_keys(
            GATE,
            "block",
            raw,
            {"id", "digest", "disposition", "dest", "anchor", "review", "claims"},
            {"id", "digest", "disposition"},
        )
        if b["disposition"] not in DISPOSITIONS:
            raise CannotRun(f"{GATE}: block {b['id']} has unknown disposition {b['disposition']!r}")
        claims = []
        for c in b.get("claims", []):
            c = strict_keys(GATE, f"{b['id']} claim", c, {"id", "kind", "text"}, {"id", "kind", "text"})
            if c["kind"] not in CLAIM_KINDS | {"unverified"}:
                raise CannotRun(f"{GATE}: claim {c['id']} has unsupported kind {c['kind']!r}")
            claims.append(Claim(c["id"], c["kind"], c["text"]))
        for key in ("dest",):
            if b.get(key):
                safe_path(GATE, b[key])
        records.append(
            BlockRecord(
                b["id"], b["digest"], b["disposition"], b.get("dest"), b.get("anchor"), b.get("review"), tuple(claims)
            )
        )
    ids = [r.id for r in records]
    if len(ids) != len(set(ids)):
        raise CannotRun(f"{GATE}: duplicate block identity in the manifest")
    return GuideMigrationManifest(
        safe_path(GATE, data["old"]), safe_path(GATE, data["guide"]), data["size_limit"], tuple(records)
    )


def _section(page: str, anchor: str) -> str | None:
    m = re.search(rf"^## {re.escape(anchor)}\s*$", page, re.M)
    if m is None:
        return None
    nxt = re.search(r"^## ", page[m.end() :], re.M)
    return page[m.end() : m.end() + nxt.start() if nxt else len(page)]


def check(root: Path) -> tuple[Result, list[str]]:
    manifest = load_manifest(root)
    old = require(GATE, root, manifest.old).decode("utf-8", errors="replace")
    guide_raw = read(root, manifest.guide)
    if guide_raw is None:
        raise CannotRun(f"{GATE}: the new guide {manifest.guide} is not in the snapshot")
    guide = guide_raw.decode("utf-8", errors="replace")
    result, unverified = Result(), []
    source = split_blocks(old)
    by_id = {r.id: r for r in manifest.records}
    for block in source:
        if block.id not in by_id:
            result.findings.append(
                f"{manifest.old}:{block.first}: source block {block.id} is omitted from the manifest"
            )
    for record in manifest.records:
        if record.id not in {b.id for b in source}:
            result.findings.append(f"{DECLARATION}: record {record.id} names no source block")
    counts = {d: 0 for d in DISPOSITIONS}
    pages: dict[str, str] = {}
    for block in source:
        rec = by_id.get(block.id)
        if rec is None:
            continue
        counts[rec.disposition] += 1
        where = f"{manifest.old}:{block.first}-{block.last}"
        if rec.digest != block.digest:
            result.findings.append(
                f"{where}: block {block.id} digest {block.digest} differs from the manifest {rec.digest}"
            )
        after, after_where = "n/a", "n/a"
        if rec.disposition == "retained":
            if block.text not in guide:
                result.findings.append(f"{manifest.guide}: retained block {block.id} is not preserved")
            else:
                after, after_where = block.digest, manifest.guide
        elif rec.disposition == "moved":
            if not rec.dest or not rec.anchor:
                result.findings.append(f"{DECLARATION}: moved block {block.id} needs a destination path and anchor")
            else:
                if rec.dest not in pages:
                    page = read(root, rec.dest)
                    pages[rec.dest] = page.decode("utf-8", errors="replace") if page is not None else ""
                section = _section(pages[rec.dest], rec.anchor)
                if section is None or block.text not in section:
                    result.findings.append(f"{rec.dest}: moved block {block.id} is absent under ## {rec.anchor}")
                else:
                    after, after_where = block.digest, f"{rec.dest}#{rec.anchor}"
        elif not (rec.review or "").strip():
            result.findings.append(f"{DECLARATION}: retired block {block.id} carries no recorded review")
        if block.kind == "diagram":
            lines = [(block.first + n + 1, t) for n, t in enumerate(block.text.splitlines()[1:-1])]
            for f in validate_block(block.first, lines):
                result.findings.append(f"{where}: diagram {block.id} fails the renderer: {f['message']}")
        result.lines.append(
            f"block id={block.id} kind={block.kind} lines={block.first}-{block.last} digest={block.digest} disposition={rec.disposition} to={after_where} after={after}"
        )
        for claim in rec.claims:
            resolved = None if claim.kind == "unverified" else RESOLVERS[claim.kind](root, claim.text)
            if resolved is True:
                evidence = "measured"
            elif resolved is False:
                evidence = "changed"
                result.findings.append(f"{where}: claim {claim.id} ({claim.kind}) {claim.text!r} no longer holds")
            else:
                evidence = "unresolved"
                unverified.append(f"claim {claim.id} of block {block.id} ({claim.kind}) cannot be verified")
            result.lines.append(f"claim id={claim.id} block={block.id} kind={claim.kind} evidence={evidence}")
    size = len(guide_raw)
    result.lines.append(
        f"counts blocks={len(source)} retained={counts['retained']} moved={counts['moved']} retired={counts['retired']}"
    )
    result.lines.append(f"size guide={manifest.guide} bytes={size} limit={manifest.size_limit}")
    if size > manifest.size_limit:
        result.findings.append(f"{manifest.guide}: guide is {size} bytes, over the limit {manifest.size_limit}")
    base = PurePosixPath(manifest.guide).parent
    linked = set()
    for m in _LINK.finditer(guide):
        if "://" in m["target"]:
            continue
        target = posixpath.normpath((base / m["target"]).as_posix())
        linked.add(target)
        if read(root, target) is None:
            result.findings.append(
                f"{manifest.guide}:{guide[: m.start()].count(chr(10)) + 1}: link {m['target']} is broken"
            )
    for dest in sorted({r.dest for r in manifest.records if r.disposition == "moved" and r.dest}):
        if dest not in linked:
            result.findings.append(f"{manifest.guide}: the guide does not link to destination {dest}")
    result.lines.append(f"navigation links={sorted(linked)}")
    complete = not unverified
    result.lines.append(
        f"verification complete={'yes' if complete else 'no'} unverified={len(unverified)} "
        "evidence-kinds=byte-preserved,editorial-review,measured"
    )
    return result, unverified


def render(root: Path, dest: Path) -> list[Path]:
    """Write the reviewable split: destination pages with moved blocks, and the concise linking guide."""
    manifest = load_manifest(root)
    if dest.exists():
        raise CannotRun(f"{GATE}: refusing to overwrite existing destination {dest}")
    if ".git" in dest.parts or ".." in dest.parts:
        raise CannotRun(f"{GATE}: unsafe destination {dest}")
    old = require(GATE, root, manifest.old).decode("utf-8", errors="replace")
    source = {b.id: b for b in split_blocks(old)}
    pages: dict[str, dict[str, list[str]]] = {}
    retained: list[str] = []
    for record in manifest.records:
        block = source.get(record.id)
        if block is None:
            raise CannotRun(f"{GATE}: record {record.id} names no source block")
        if record.disposition == "retained":
            retained.append(block.text)
        elif record.disposition == "moved":
            if not record.dest or not record.anchor:
                raise CannotRun(f"{GATE}: moved block {record.id} needs a destination path and anchor")
            pages.setdefault(record.dest, {}).setdefault(record.anchor, []).append(block.text)
    base = PurePosixPath(manifest.guide).parent
    guide = ["\n\n".join(retained), "## Pages", *(f"- [{d}]({os.path.relpath(d, base)})" for d in sorted(pages))]
    written = []
    files = {manifest.guide: "\n\n".join(p for p in guide[:2] if p) + "\n\n" + "\n".join(guide[2:]) + "\n"}
    for page, sections in pages.items():
        files[page] = "\n\n".join(f"## {a}\n\n" + "\n\n".join(texts) for a, texts in sections.items()) + "\n"
    for rel, text in files.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(target)
    return written


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=GATE, description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate the staged snapshot (default)")
    mode.add_argument("--render", type=Path, metavar="DEST", help="render the split into a new directory")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    if args.render is not None:
        for path in render(root, args.render):
            print(f"rendered {path}")
        return 0
    result, unverified = check(root)
    code = finish(GATE, "guide migration", result)
    if code == 0 and unverified:
        raise CannotRun(f"{GATE}: {len(unverified)} unverified claim(s): " + "; ".join(unverified))
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
