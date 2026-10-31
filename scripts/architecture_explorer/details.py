"""Spec details for the architecture explorer: light descriptions and one lazy-loaded JSON file per family.

The page carries only a short plain-text description per row. The full requirement, acceptance text,
delivery evidence, matching test-spec lines and the family design documents are rendered here, at build
time, from a safe markdown subset (headings, paragraphs, lists, code, tables, links) and written to
``spec-details/<repo>/<family>.json`` next to the page, which fetches a family on its first expand.
All source text is HTML-escaped; only http(s) links and links relative to the family directory survive.
"""

from __future__ import annotations

import html
import json
import posixpath
import re
import shutil
from pathlib import Path

from .sdd import slug as anchor_slug

OWNER = "Knuckles-Team"
DESC_MAX = 160
DOC_MAX = 200_000
TEST_LINES_MAX = 12
MAX_DEPTH = 8
DOC_LABELS = {
    "spec.md": "Spec",
    "plan.md": "Plan",
    "tasks.md": "Tasks",
    "test-spec.md": "Test spec",
    "research.md": "Research",
    "data-model.md": "Data model",
    "quickstart.md": "Quickstart",
}
NESTED_LABELS = {"checklists": "Checklist", "contracts": "Contract"}
TEXT_SUFFIXES = (".md", ".yml", ".yaml", ".json", ".txt", ".toml", ".graphql", ".proto")
HEADING_RE = re.compile(r"<h([3-6])>(.*?)</h\1>", re.S)
TAG_RE = re.compile(r"<[^>]+>")
DESIGN_RE = re.compile(r"(^|[-_.])(design|architecture)([-_.]|$)", re.I)
ESC = html.escape


def safe_name(part: str) -> str:
    """Return one path component for a repository or family name (the page applies the same rule)."""
    out = re.sub(r"[^A-Za-z0-9._-]", "_", part)
    return "_" if out in ("", ".", "..") else out


def detail_path(repo: str, family: str) -> str:
    """Return the published path of one family's detail file, relative to the page."""
    return f"spec-details/{safe_name(repo)}/{safe_name(family)}.json"


def split_cells(line: str) -> list[str]:
    """Split a markdown table line into cells, ignoring pipes inside code spans and escaped pipes."""
    cells, cur, code = [], [], False
    chars = line.strip()
    i = 0
    while i < len(chars):
        ch = chars[i]
        if ch == "\\" and i + 1 < len(chars) and chars[i + 1] == "|":
            cur.append("|")
            i += 2
            continue
        if ch == "`":
            code = not code
        if ch == "|" and not code:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    cells.append("".join(cur).strip())
    if chars.startswith("|"):
        cells = cells[1:]
    if chars.endswith("|") and cells:
        cells = cells[:-1]
    return cells


def row_parts(body: str) -> tuple[str, str]:
    """Return the requirement text and the verification text of one requirements.md row (after the ID cell)."""
    cells = split_cells("|" + body)
    return (cells[0] if cells else ""), (cells[1] if len(cells) > 1 else "")


# ---------------------------------------------------------------- description

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_LEAD = re.compile(r"^\s*\*\*(.+?)\*\*\s*")


def plain(text: str) -> str:
    """Strip markdown emphasis, code ticks and link targets to plain text with single spaces."""
    text = _LINK.sub(r"\1", text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"[*`]|(?<!\w)_|_(?!\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", " ", plain(text)).strip().casefold()


def describe(requirement: str, title: str = "") -> str:
    """Return the first sentence of a requirement, plain text, at most DESC_MAX characters.

    A bold lead that only repeats the row title is skipped, so the description adds to the title.
    """
    text = requirement.strip()
    lead = _LEAD.match(text)
    if lead and title and _norm(lead.group(1)) == _norm(title) and text[lead.end() :].strip():
        text = text[lead.end() :]
    text = plain(text)
    match = re.match(r"(.+?[.!?])(?=\s+[A-Z\"'(\[]|\s*$)", text)
    sentence = match.group(1) if match else text
    if len(sentence) > DESC_MAX:
        cut = sentence[: DESC_MAX - 1]
        sentence = cut[: cut.rfind(" ")] if " " in cut[40:] else cut
        sentence = sentence.rstrip(" ,;:.") + "…"
    return sentence


# ------------------------------------------------------------------- markdown


class Ctx:
    """Where relative links resolve: ``specs/<family>/`` of one repository on its default branch."""

    def __init__(self, slug: str, family: str, base: str = "") -> None:
        self.slug = slug
        self.base = base or f"specs/{family}"


def safe_url(url: str, ctx: Ctx) -> str | None:
    """Return an http(s) URL, a relative link resolved to GitHub, or None when the link is not allowed."""
    url = url.strip()
    if not url or re.search(r"[\s\x00-\x1f\\<>\"]", url):
        return None
    if re.match(r"^https?://[^/\s]", url, re.I):
        return url
    if url.startswith(("#", "//")) or re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:", url):
        return None
    path, _, frag = url.partition("#")
    path = path.partition("?")[0]
    resolved = posixpath.normpath(posixpath.join(ctx.base, path))
    if not path or resolved.startswith(("..", "/")):
        return None
    kind = "tree" if path.endswith("/") else "blob"
    return f"https://github.com/{OWNER}/{ctx.slug}/{kind}/HEAD/{resolved}" + (f"#{frag}" if frag else "")


_CODE = re.compile(r"(`+)(.+?)(?<!`)\1(?!`)", re.S)
_LINKTOK = re.compile(r"\[([^\]]+)\]\(([^)\s]*)(?:\s+\"[^\"]*\")?\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_EM_STAR = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")
_EM_UNDER = re.compile(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)")
_BR = re.compile(r"<br\s*/?>", re.I)


def _emphasis(text: str) -> str:
    out = ESC(text)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _EM_STAR.sub(r"<em>\1</em>", out)
    return _EM_UNDER.sub(r"<em>\1</em>", out)


def _text_links(text: str, ctx: Ctx) -> str:
    out, pos = [], 0
    for m in _LINKTOK.finditer(text):
        out.append(_br(text[pos : m.start()]))
        url = safe_url(m.group(2), ctx)
        label = _emphasis(m.group(1))
        out.append(f'<a href="{ESC(url)}" rel="noopener noreferrer" target="_blank">{label}</a>' if url else label)
        pos = m.end()
    out.append(_br(text[pos:]))
    return "".join(out)


def _br(text: str) -> str:
    return "<br>".join(_emphasis(part) for part in _BR.split(text))


def inline(text: str, ctx: Ctx) -> str:
    """Render one run of inline markdown; every character of the source is escaped."""
    out, pos = [], 0
    for m in _CODE.finditer(text):
        out.append(_text_links(text[pos : m.start()], ctx))
        out.append(f"<code>{ESC(m.group(2).strip())}</code>")
        pos = m.end()
    out.append(_text_links(text[pos:], ctx))
    return "".join(out)


_FENCE = re.compile(r"^\s*(```+|~~~+)")
_HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_HR = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_QUOTE = re.compile(r"^\s*>")


def _starts_block(lines: list[str], i: int) -> bool:
    line = lines[i]
    return bool(
        _FENCE.match(line)
        or _HEAD.match(line)
        or _HR.match(line)
        or _QUOTE.match(line)
        or _ITEM.match(line)
        or (i + 1 < len(lines) and "|" in line and _SEP.match(lines[i + 1]) and "-" in lines[i + 1])
    )


def _table(lines: list[str], i: int, ctx: Ctx) -> tuple[str, int]:
    head = split_cells(lines[i])
    j = i + 2
    body = []
    while j < len(lines) and lines[j].strip() and "|" in lines[j]:
        body.append(split_cells(lines[j]))
        j += 1
    ths = "".join(f"<th>{inline(c, ctx)}</th>" for c in head)
    trs = "".join(
        "<tr>" + "".join(f"<td>{inline(c, ctx)}</td>" for c in (row + [""] * len(head))[: max(len(head), 1)]) + "</tr>"
        for row in body
    )
    return f'<div class="tbl"><table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>', j


def _list(lines: list[str], i: int, ctx: Ctx, depth: int) -> tuple[str, int]:
    first = _ITEM.match(lines[i])
    base = len(first.group(1).expandtabs(4))
    ordered = first.group(2)[0].isdigit()
    items = []
    while i < len(lines):
        m = _ITEM.match(lines[i])
        if not m or len(m.group(1).expandtabs(4)) != base or m.group(2)[0].isdigit() != ordered:
            break
        chunk = [m.group(3)]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip():
                peek = next((k for k in range(i + 1, len(lines)) if lines[k].strip()), None)
                if peek is None or len(lines[peek]) - len(lines[peek].lstrip()) <= base:
                    break
                chunk.append("")
                i += 1
                continue
            indent = len(nxt.expandtabs(4)) - len(nxt.expandtabs(4).lstrip())
            if indent <= base and (_ITEM.match(nxt) or _starts_block(lines, i) or indent == 0):
                break
            chunk.append(nxt.expandtabs(4)[min(indent, base + 2) :] if indent > base else nxt.strip())
            i += 1
        inner = _blocks(chunk, ctx, depth + 1)
        if inner.startswith("<p>") and inner.count("<p>") == 1:
            inner = inner.replace("<p>", "", 1).replace("</p>", "", 1)
        items.append(f"<li>{inner}</li>")
    tag = "ol" if ordered else "ul"
    return f"<{tag}>{''.join(items)}</{tag}>", i


def _blocks(lines: list[str], ctx: Ctx, depth: int = 0) -> str:
    if depth > MAX_DEPTH:
        return f"<p>{ESC(' '.join(s.strip() for s in lines))}</p>"
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        fence = _FENCE.match(line)
        if fence:
            mark, code = fence.group(1), []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(mark[:3]):
                code.append(lines[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{ESC(chr(10).join(code))}</code></pre>")
            continue
        head = _HEAD.match(line)
        if head:
            level = min(6, len(head.group(1)) + 2)
            out.append(f"<h{level}>{inline(head.group(2), ctx)}</h{level}>")
            i += 1
            continue
        if _HR.match(line) and not _ITEM.match(line):
            out.append("<hr>")
            i += 1
            continue
        if "|" in line and i + 1 < len(lines) and _SEP.match(lines[i + 1]) and "-" in lines[i + 1]:
            html_, i = _table(lines, i, ctx)
            out.append(html_)
            continue
        if _QUOTE.match(line):
            quote = []
            while i < len(lines) and _QUOTE.match(lines[i]):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote>{_blocks(quote, ctx, depth + 1)}</blockquote>")
            continue
        if _ITEM.match(line):
            html_, i = _list(lines, i, ctx, depth)
            out.append(html_)
            continue
        para = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not _starts_block(lines, i):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(para), ctx)}</p>")
    return "".join(out)


def render_markdown(markdown: str, ctx: Ctx) -> str:
    """Render markdown to safe HTML; raw HTML in the source is escaped, never passed through."""
    return _blocks(markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"), ctx)


# --------------------------------------------------------------- family files


def _gh(slug: str, kind: str, path: str) -> str:
    return f"https://github.com/{OWNER}/{slug}/{kind}/HEAD/{path}"


def matching_test_lines(test_spec: str, row_id: str) -> list[str]:
    """Return the test-spec lines that name a row ID (not a longer ID such as ``ID.1``)."""
    pattern = re.compile(r"(?<![\w.\-])" + re.escape(row_id) + r"(?![\w\-]|\.\d)")
    found = [ln.strip() for ln in test_spec.splitlines() if ln.strip() and pattern.search(ln)]
    return found[:TEST_LINES_MAX]


def evidence(slug: str, row: dict) -> dict:
    """Return a row's delivery evidence with each commit and test line linked on the default branch."""
    commits = [
        {"label": c[:12], "url": f"https://github.com/{OWNER}/{slug}/commit/{c}"}
        for c in row.get("landed_in") or []
        if isinstance(c, str) and re.fullmatch(r"[0-9a-f]{7,40}", c)
    ]
    tests = []
    for t in row.get("verified_by") or []:
        if not isinstance(t, str):
            continue
        path, _, line = t.partition(":")
        ok = path and not path.startswith(("/", "..")) and ".." not in path.split("/") and " " not in path
        url = _gh(slug, "blob", path) + (f"#L{line}" if line.isdigit() else "") if ok else ""
        tests.append({"label": t, "url": url})
    return {
        "landed_in": commits,
        "verified_by": tests,
        "rollup_of": [r for r in row.get("rollup_of") or [] if isinstance(r, str)],
    }


def _clip(markdown: str) -> str:
    return (
        markdown
        if len(markdown) <= DOC_MAX
        else markdown[:DOC_MAX] + "\n\n(Truncated here. Open the file on GitHub for the rest.)\n"
    )


CONSTITUTION_FILE = "constitution.md"
EXTRA_FILE = "search-extra.json"


def doc_label(name: str) -> str:
    head, _, rest = name.partition("/")
    if rest:
        return f"{NESTED_LABELS.get(head, head)}: {rest.rsplit('.', 1)[0]}"
    return DOC_LABELS.get(name) or "Design: " + name.removesuffix(".md")


def doc_names(files: set[str], family: str) -> list[str]:
    """Return the family documents to read: spec-kit files, checklists, contracts, design and architecture notes."""
    prefix = f"specs/{family}/"
    rel = sorted(f[len(prefix) :] for f in files if f.startswith(prefix))
    top = [n for n in rel if "/" not in n and n.endswith(".md") and (n in DOC_LABELS or DESIGN_RE.search(n[:-3]))]
    nested = [
        n for n in rel if n.partition("/")[0] in NESTED_LABELS and n.count("/") == 1 and n.endswith(TEXT_SUFFIXES)
    ]
    return top + nested


def family_docs(reader, files: set[str], family: str) -> dict[str, str]:
    """Read a family's documents (only those that exist)."""
    out = {}
    for name in doc_names(files, family):
        text = reader.read(f"specs/{family}/{name}")
        if text:
            out[name] = text
    return out


def outline(markup: str) -> list[list]:
    """Return ``[level, text, slug]`` for each heading of rendered HTML; a repeated slug gets ``-2``, ``-3``."""
    seen: dict[str, int] = {}
    out = []
    for level, inner in HEADING_RE.findall(markup):
        text = html.unescape(TAG_RE.sub("", inner)).strip()
        base = anchor_slug(text)
        seen[base] = seen.get(base, 0) + 1
        out.append([int(level), text, base if seen[base] == 1 else f"{base}-{seen[base]}"])
    return out


def doc_entry(repo_slug: str, base: str, name: str, text: str, ctx: Ctx) -> dict:
    """Return one document of a family file: label, GitHub link, safe HTML and its heading outline."""
    if not name.endswith(".md"):  # a contract file is shown as code
        text = f"```\n{text}\n```"
    markup = render_markdown(_clip(text), ctx)
    return {
        "name": name,
        "label": doc_label(name),
        "url": _gh(repo_slug, "blob", base + name),
        "html": markup,
        "outline": outline(markup),
    }


def constitution_detail(repo: str, slug: str, text: str) -> dict:
    """Return the detail file of a repository's constitution, shaped like a family file with one document."""
    ctx = Ctx(slug, "", base=".specify/memory")
    name = CONSTITUTION_FILE
    entry = doc_entry(slug, ".specify/memory/", name, text, ctx)
    entry["label"] = "Constitution"
    return {"v": 1, "repo": repo, "family": "_constitution", "files": [], "rows": {}, "docs": [entry]}


def family_detail(repo: str, slug: str, family: str, rows: list[dict], docs: dict[str, str], files: set[str]) -> dict:
    """Return the JSON document of one family: per-row full text and evidence plus the design documents."""
    ctx = Ctx(slug, family)
    test_spec = docs.get("test-spec.md", "")
    out_rows = {}
    for row in rows:
        req, acc = row_parts(row.get("text", ""))
        entry = {"status": row.get("status", ""), "req": render_markdown(req, ctx), **evidence(slug, row)}
        if acc.strip():
            entry["acc"] = render_markdown(acc, ctx)
        tests = matching_test_lines(test_spec, row["id"])
        if tests:
            entry["tests"] = [
                inline(" — ".join(c for c in split_cells(t) if c) if t.startswith("|") else t, ctx) for t in tests
            ]
        out_rows[row["id"]] = entry
    base = f"specs/{family}/"
    names = [
        n
        for n in ("requirements.md", "spec.md", "plan.md", "design.md", "test-spec.md", "tasks.md")
        if base + n in files
    ]
    names += [n for n in docs if n not in names]
    return {
        "v": 1,
        "repo": repo,
        "family": family,
        "files": [{"name": n, "url": _gh(slug, "blob", base + n)} for n in (names or ["requirements.md"])],
        "rows": out_rows,
        "docs": [
            doc_entry(slug, base, n, t, ctx)
            for n, t in sorted(docs.items(), key=lambda kv: (kv[0] != "plan.md", kv[0] == "test-spec.md", kv[0]))
        ],
    }


def write_json(path: Path, doc: dict) -> Path:
    """Write one detail file as compact JSON, creating its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    return path


def write_details(page_dir: Path, snaps: list, extra: dict | None = None) -> list[Path]:
    """Write one JSON file per repository family and constitution under ``<page_dir>/spec-details``.

    An earlier build's files are replaced. ``extra`` (the lazy search extras) is written to ``search-extra.json``.
    """
    root = page_dir / "spec-details"
    if root.exists():
        shutil.rmtree(root)
    written = []
    for snap in snaps:
        by_family: dict[str, list[dict]] = {}
        for row in snap.rows:
            by_family.setdefault(row["family"], []).append(row)
        for family, rows in by_family.items():
            doc = family_detail(snap.repo, snap.slug, family, rows, snap.docs.get(family, {}), snap.files)
            written.append(write_json(page_dir / detail_path(snap.repo, family), doc))
        if snap.constitution:
            doc = constitution_detail(snap.repo, snap.slug, snap.constitution)
            written.append(write_json(page_dir / detail_path(snap.repo, "_constitution"), doc))
    if extra is not None:
        write_json(page_dir / EXTRA_FILE, extra)
    return written
