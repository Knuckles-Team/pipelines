"""Spelling findings are fixed or classified (``pl.af``): safe typo fixes in prose and comments, identifiers to ignore_words.

The central codespell scan blocks a migrated connector on typos it already had. This rule runs the same scan
(``pipelines_hooks.connector.codespell.findings``, same config) and sorts every hit by where it sits:

* documentation (``.md``/``.rst``/``.txt``, outside code fences and code spans) and comments/docstrings of ``.py`` files,
  with exactly one suggestion: the word is replaced at its exact position, nothing else in the file moves;
* a code identifier of a ``.py`` file (variable, argument, attribute, function, class, keyword argument, import name,
  confirmed by the AST): the lower-case word joins the repo's own ``[tool.pipelines.codespell] ignore_words``;
* everything else (string literals, several suggestions, other file types, generated or unreadable files) is left alone
  and stays a blocking item of the final scan, which names the file, the line, the word and the class.

Code is never rewritten: a ``.py`` edit is only made inside a comment or docstring token, and is undone when the
file would no longer parse.
"""

from __future__ import annotations

import ast
import io
import keyword
import re
import tokenize
import tomllib
from dataclasses import dataclass
from typing import Any

from pipelines_hooks.hygiene.connector_central.base import Ctx, rule

ORDER: tuple[str, ...] = ("pl.af",)
REASONS_KEY = "spelling_reasons"
DOC_SUFFIXES = (".md", ".rst", ".txt")
_FINDING = re.compile(r"^(?P<path>.+?):(?P<line>\d+): (?P<word>\S+) ==> (?P<fix>.*)$")
_GENERATED = re.compile(r"(?i)(auto-?generated|generated (by|from|file)|do not (edit|modify)|@generated)")
_TABLE = ("tool", "pipelines", "codespell")
#: Tracked tool working directories whose generated reports are not connector prose.
GENERATED_DIRS = (".specify/",)
_HEADER = "[tool.pipelines.codespell]"


@dataclass(frozen=True)
class Hit:
    """One codespell finding: file, 1-based line, the flagged word and its suggestions."""

    path: str
    line: int
    word: str
    fixes: tuple[str, ...]

    @property
    def single(self) -> str | None:
        """The one suggestion, or None when codespell offers several (or an empty one)."""
        return self.fixes[0] if len(self.fixes) == 1 and self.fixes[0] else None


def parse_findings(lines: list[str]) -> list[Hit]:
    """``path:line: word ==> a, b`` lines as hits; tool-error lines are skipped."""
    hits: list[Hit] = []
    for raw in lines:
        m = _FINDING.match(raw)
        if m is None:
            continue
        fix = m["fix"].split(" | ", 1)[0]
        hits.append(Hit(m["path"], int(m["line"]), m["word"], tuple(f.strip() for f in fix.split(","))))
    return hits


def occurrences(line: str, word: str) -> list[int]:
    """Start columns of ``word`` as a whole word of ``line`` (letters/digits do not touch it; ``_`` and ``-`` may)."""
    return [m.start() for m in re.finditer(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", line)]


# --- classification: documentation ---------------------------------------------------------------------------------
def _doc_prose_columns(lines: list[str]) -> list[list[tuple[int, int]]]:
    """Per line, the column ranges that are prose: outside fenced code, inline code spans and URLs."""
    out: list[list[tuple[int, int]]] = []
    fence = ""
    for raw in lines:
        stripped = raw.lstrip()
        marker = stripped[:3] if stripped.startswith(("```", "~~~")) else ""
        if marker and (not fence or marker == fence):
            fence = "" if fence else marker
            out.append([])
            continue
        if fence:
            out.append([])
            continue
        spans: list[tuple[int, int]] = []
        pos = 0
        for m in re.finditer(r"`[^`\n]*`|\S*://\S*", raw):
            spans.append((pos, m.start()))
            pos = m.end()
        spans.append((pos, len(raw)))
        # an odd number of backticks leaves an unclosed span: treat the rest of that line as code
        out.append(spans if raw.count("`") % 2 == 0 else [])
    return out


# --- classification: python ----------------------------------------------------------------------------------------
def _identifiers(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.update(p for p in (node.name.split(".") + (node.asname or "").split(".")) if p)
        elif isinstance(node, ast.Global | ast.Nonlocal):
            names.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


class PyMap:
    """Token and AST facts of one ``.py`` file, enough to say what a (line, column) position is."""

    def __init__(self, text: str) -> None:
        tree = ast.parse(text)
        self.idents = _identifiers(tree)
        self.docstrings: set[tuple[int, int]] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) and node.body:
                first = node.body[0]
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    self.docstrings.add((first.value.lineno, first.value.col_offset))
        self.tokens = [
            t
            for t in tokenize.generate_tokens(io.StringIO(text).readline)
            if t.type in (tokenize.COMMENT, tokenize.STRING, tokenize.NAME)
            or tokenize.tok_name[t.type] == "FSTRING_MIDDLE"
        ]

    def kind(self, line: int, col: int) -> str:
        """``comment``, ``docstring``, ``identifier``, ``string`` or ``other`` for the token holding the position."""
        pos = (line, col)
        for tok in self.tokens:
            if tok.start <= pos < tok.end:
                if tok.type == tokenize.COMMENT:
                    return "comment"
                if tok.type == tokenize.STRING:
                    return "docstring" if tok.start in self.docstrings and not _is_bytes(tok.string) else "string"
                if tok.type == tokenize.NAME:
                    ok = tok.string in self.idents and not keyword.iskeyword(tok.string)
                    return "identifier" if ok else "other"
                return "string"
        return "other"


def _is_bytes(token: str) -> bool:
    return re.match(r"(?i)^[a-z]*b[a-z]*['\"]", token) is not None


def _generated(text: str) -> bool:
    return any(_GENERATED.search(ln) for ln in text.split("\n", 8)[:8])


# --- pyproject ignore_words ----------------------------------------------------------------------------------------
def merge_ignore_words(text: str, words: set[str]) -> str | None:
    """``pyproject.toml`` text whose ``[tool.pipelines.codespell] ignore_words`` is sorted and holds ``words`` too.

    Returns None when the table cannot be edited exactly (the caller then leaves the hits as review items).
    """
    data = tomllib.loads(text)
    table: Any = data
    for key in _TABLE:
        table = table.get(key, {}) if isinstance(table, dict) else {}
    have = table.get("ignore_words", []) if isinstance(table, dict) else []
    merged = sorted({str(w).lower() for w in have} | {w.lower() for w in words})
    if merged == list(have) and "ignore_words" in table:
        return text
    array = "ignore_words = [" + ", ".join(f'"{w}"' for w in merged) + "]"
    header = re.search(rf"(?m)^{re.escape(_HEADER)}[ \t]*$", text)
    if header is None:
        new = text.rstrip("\n") + f"\n\n{_HEADER}\n{array}\n"
    else:
        end = re.search(r"(?m)^\[", text[header.end() :])
        section_end = header.end() + end.start() if end else len(text)
        section = text[header.end() : section_end]
        existing = re.search(r"(?ms)^ignore_words[ \t]*=[ \t]*\[.*?\]", section)
        if existing:
            section = section[: existing.start()] + array + section[existing.end() :]
        else:
            section = "\n" + array + section
        new = text[: header.end()] + section + text[section_end:]
    try:
        check: Any = tomllib.loads(new)
        for key in _TABLE:
            check = check[key]
        if check["ignore_words"] != merged:
            return None
    except (tomllib.TOMLDecodeError, KeyError, TypeError):
        return None
    return new


def merge_exclude(text: str, paths: set[str]) -> str | None:
    """``pyproject.toml`` text whose ``[tool.pipelines.codespell] exclude`` holds ``paths`` too (None: not editable exactly)."""
    data = tomllib.loads(text)
    table: Any = data
    for key in _TABLE:
        table = table.get(key, {}) if isinstance(table, dict) else {}
    have = list(table.get("exclude", [])) if isinstance(table, dict) else []
    merged = sorted({str(p) for p in have} | paths)
    if merged == have:
        return text
    array = "exclude = [" + ", ".join(f'"{p}"' for p in merged) + "]"
    header = re.search(rf"(?m)^{re.escape(_HEADER)}[ \t]*$", text)
    if header is None:
        new = text.rstrip("\n") + f"\n\n{_HEADER}\n{array}\n"
    else:
        end = re.search(r"(?m)^\[", text[header.end() :])
        section_end = header.end() + end.start() if end else len(text)
        section = text[header.end() : section_end]
        existing = re.search(r"(?ms)^exclude[ \t]*=[ \t]*\[.*?\]", section)
        if existing:
            section = section[: existing.start()] + array + section[existing.end() :]
        else:
            section = "\n" + array + section
        new = text[: header.end()] + section + text[section_end:]
    try:
        check: Any = tomllib.loads(new)
        for key in _TABLE:
            check = check[key]
        if check["exclude"] != merged:
            return None
    except (tomllib.TOMLDecodeError, KeyError, TypeError):
        return None
    return new


# --- the rule ------------------------------------------------------------------------------------------------------
def _remember(ctx: Ctx, hit: Hit, reason: str) -> None:
    ctx.options.setdefault(REASONS_KEY, {})[f"{hit.path}:{hit.line}:{hit.word}"] = reason


def classify_file(ctx: Ctx, rel: str, hits: list[Hit]) -> tuple[list[tuple[int, int, int, str]], set[str]]:
    """``(edits, ignore_words)`` for one file; every hit not covered gets its reason remembered for the final scan.

    An edit is ``(line, col, length, replacement)`` with a 1-based line.
    """
    try:
        text = ctx.read(rel)
    except (OSError, UnicodeDecodeError):
        for h in hits:
            _remember(ctx, h, "binary or unreadable file")
        return [], set()
    if _generated(text):
        for h in hits:
            _remember(ctx, h, "generated file")
        return [], set()
    lines = text.split("\n")
    edits: list[tuple[int, int, int, str]] = []
    words: set[str] = set()
    is_py = rel.endswith(".py")
    is_doc = rel.endswith(DOC_SUFFIXES)
    pymap: PyMap | None = None
    if is_py:
        try:
            pymap = PyMap(text)
        except (SyntaxError, tokenize.TokenError, ValueError):
            for h in hits:
                _remember(ctx, h, "python file that cannot be parsed")
            return [], set()
    prose = _doc_prose_columns(lines) if is_doc else []
    for h in dict.fromkeys(hits):
        if not 1 <= h.line <= len(lines):
            _remember(ctx, h, "position outside the file")
            continue
        cols = occurrences(lines[h.line - 1], h.word)
        if not cols:
            _remember(ctx, h, "word position not found on the line")
            continue
        found: list[tuple[str, int]] = []
        for col in cols:
            if is_doc:
                inside = any(a <= col and col + len(h.word) <= b for a, b in prose[h.line - 1])
                found.append(("prose" if inside else "code", col))
            elif pymap is not None:
                found.append((pymap.kind(h.line, col), col))
            else:
                found.append(("other file type", col))
        fixable = [c for k, c in found if k in ("prose", "comment", "docstring") and h.single]
        idents = [c for k, c in found if k == "identifier"]
        unresolved = [
            k
            for k, _c in found
            if k not in ("prose", "comment", "docstring", "identifier")
            or (k in ("prose", "comment", "docstring") and not h.single)
        ]
        for col in fixable:
            edits.append((h.line, col, len(h.word), h.single or ""))
        if idents and not unresolved:
            words.add(h.word.lower())
        elif unresolved:
            kind = unresolved[0]
            if kind in ("prose", "comment", "docstring"):
                kind = f"{kind} with several suggestions"
            elif kind == "string":
                kind = "string literal"
            _remember(ctx, h, kind)
    return edits, words


def apply_edits(text: str, edits: list[tuple[int, int, int, str]]) -> str:
    """Replace each ``(line, col, length, new)`` right to left so earlier columns stay valid."""
    lines = text.split("\n")
    for line, col, length, new in sorted(set(edits), reverse=True):
        row = lines[line - 1]
        lines[line - 1] = row[:col] + new + row[col + length :]
    return "\n".join(lines)


@rule("pl.af")
def rule_af(ctx: Ctx) -> None:
    from pipelines_hooks.connector import codespell

    if not ctx.applied:
        return
    try:
        found = codespell.findings(ctx.root, extra=sorted(ctx.changed - ctx.deleted))
    except Exception:  # noqa: BLE001 - the final scan reports an unavailable codespell
        return
    by_file: dict[str, list[Hit]] = {}
    for hit in parse_findings(found):
        by_file.setdefault(hit.path, []).append(hit)
    ignore: set[str] = set()
    skip_dirs: set[str] = set()
    for rel, hits in sorted(by_file.items()):
        if rel.startswith(GENERATED_DIRS):  # tool working directories (code-enhancer reports): excluded, not edited
            skip_dirs.add(rel.split("/", 1)[0])
            continue
        edits, words = classify_file(ctx, rel, hits)
        if edits:
            text = ctx.read(rel)
            new = apply_edits(text, edits)
            if rel.endswith(".py"):
                try:
                    PyMap(new)
                except (SyntaxError, tokenize.TokenError, ValueError):
                    for h in hits:
                        _remember(ctx, h, "fix would leave the file unparseable")
                    new = text
            ctx.write(rel, new, "pl.af")
        ignore |= words
    if skip_dirs and ctx.exists("pyproject.toml"):
        merged_ex = merge_exclude(ctx.read("pyproject.toml"), skip_dirs)
        if merged_ex is None:
            ctx.note("pl.af", "cannot edit [tool.pipelines.codespell] exclude exactly", "pyproject.toml", True)
        else:
            ctx.write("pyproject.toml", merged_ex, "pl.af")
    if ignore and ctx.exists("pyproject.toml"):
        text = ctx.read("pyproject.toml")
        merged = merge_ignore_words(text, ignore)
        if merged is None:
            ctx.note("pl.af", "cannot edit [tool.pipelines.codespell] ignore_words exactly", "pyproject.toml", True)
        else:
            ctx.write("pyproject.toml", merged, "pl.af")
