"""Parsing the requirement rows of a ``specs/<id>/requirements.md`` table."""

from __future__ import annotations

import re
from typing import NamedTuple

from pipelines_hooks.specs.ids import ID, ROW_RE

_TITLE_RE = re.compile(r"\*\*(.+?)\*\*")
_RETIRED_RE = re.compile(r"RETIRED:?\s*(.*)")
_RELATIVE = r"R\d{2,3}(?:\.\d+)*|\.\d+(?:\.\d+)*"
#: "Depends:" takes backticked or bare full IDs. "Requires" and "After" take backticked IDs only.
_DEPENDS_RE = re.compile(r"\b(?:Depends:)\s*(?P<run>[^|]*?)(?:\.(?=\s|\||$)|\||$)")
_NEEDS_RE = re.compile(r"\b(?:Requires|After)\s+(?P<run>`[^|]*?)(?:\.(?=\s|\||$)|\||$)")
_TICKED_RE = re.compile(r"`([^`]+)`")


class Row(NamedTuple):
    """One requirement row: its ID, title, and retirement reason if retired."""

    id: str
    title: str
    retired_reason: str | None
    depends_on: tuple[str, ...] = ()


def _row_title(body: str) -> str:
    match = _TITLE_RE.search(body)
    raw = match.group(1) if match else body.split("|")[0]
    return raw.strip().rstrip(".")


def _retired_reason(title: str) -> str | None:
    match = _RETIRED_RE.match(title)
    if not match:
        return None
    return match.group(1).strip() or "retired"


def _resolve(token: str, row_id: str) -> str | None:
    """A full ID stays; ``R001.1`` takes the row's spec prefix; ``.1`` is a child of the row's parent."""
    token = token.strip()
    if re.fullmatch(ID, token):
        return token
    if re.fullmatch(_RELATIVE, token):
        if token.startswith("."):
            base = row_id.rsplit(".", 1)[0] if re.search(r"R\d{2,3}\.\d+(?:\.\d+)*$", row_id) else row_id
            return base + token
        return row_id.rsplit("-R", 1)[0] + "-" + token
    return None


def _declared_ids(body: str, row_id: str) -> tuple[str, ...]:
    """Prerequisite IDs named by ``Depends:``, ``Requires`` or ``After`` in one row."""
    found: list[str] = []
    for pattern, bare in ((_DEPENDS_RE, True), (_NEEDS_RE, False)):
        for match in pattern.finditer(body):
            run = match.group("run")
            tokens = _TICKED_RE.findall(run)
            if bare:
                tokens += re.findall(rf"(?<![`\w-])({ID})(?![\w`])", _TICKED_RE.sub(" ", run))
            found += [t for t in (_resolve(t, row_id) for t in tokens) if t]
    return tuple(dict.fromkeys(i for i in found if i != row_id))


class DependencyGap(ValueError):
    """A ``Depends:``/``Requires``/``After`` clause whose prerequisites cannot be read without guessing."""


def dependency_evidence(body: str, row_id: str) -> tuple[list[str], list[dict], list[str]]:
    """Follow the shared grammar; retain package/prose/self/repeated context.

    Canonical prerequisite lists are conjunctive. Alternative requirement meaning
    and malformed requirement-like tokens need review, not invented AND edges, so
    both raise :class:`DependencyGap`. The spec-standard gate and the architecture
    explorer read rows through this one function.
    """
    effective: list[str] = []
    contexts: list[dict] = []
    occurrences: list[str] = []
    for pattern, bare in ((_DEPENDS_RE, True), (_NEEDS_RE, False)):
        for match in pattern.finditer(body):
            run = match.group("run")
            tokens = _TICKED_RE.findall(run)
            residue = _TICKED_RE.sub(" ", run)
            if bare:
                tokens += re.findall(rf"(?<![`\w-])({ID})(?![\w`])", residue)
            resolved = []
            for token in tokens:
                target = _resolve(token, row_id)
                if target is None and "-R" in token.upper():
                    raise DependencyGap(f"{row_id}: malformed requirement-like dependency token {token!r}")
                if target is not None:
                    resolved.append(target)
            if bare and re.search(r"[A-Za-z0-9-]+-R[A-Za-z0-9.]+", residue):
                for token in re.findall(r"[A-Za-z0-9-]+-R[A-Za-z0-9.]+", residue):
                    if _resolve(token, row_id) is None:
                        raise DependencyGap(f"{row_id}: malformed requirement-like dependency token {token!r}")
            if bool(set(resolved) - {row_id}) and re.search(r"\bor\b", residue, re.I):
                raise DependencyGap(f"{row_id}: ambiguous alternative requirement prerequisites")
            kind = "requirement_prerequisites" if resolved else "non_requirement_context"
            contexts.append({"kind": kind, "text": match.group(0), "tokens": list(tokens)})
            for target in resolved:
                occurrences.append(target)
                if target == row_id:
                    contexts.append({"kind": "ignored_self_reference", "text": match.group(0), "tokens": [target]})
                elif target in effective:
                    contexts.append({"kind": "repeated_reference", "text": match.group(0), "tokens": [target]})
                else:
                    effective.append(target)
    return effective, contexts, occurrences


def dependency_gaps(text: str) -> list[str]:
    """One message per requirement row of ``text`` whose dependency clause :func:`dependency_evidence` refuses."""
    out: list[str] = []
    for line in text.splitlines():
        match = ROW_RE.match(line)
        if not match:
            continue
        try:
            dependency_evidence(match.group(2), match.group(1))
        except DependencyGap as exc:
            out.append(str(exc))
    return out


def parse_rows(text: str) -> list[Row]:
    """Every distinct requirement row, in document order (first occurrence wins)."""
    seen: set[str] = set()
    rows: list[Row] = []
    for line in text.splitlines():
        match = ROW_RE.match(line)
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        title = _row_title(match.group(2))
        body = match.group(2)
        rows.append(
            Row(
                match.group(1),
                title,
                _retired_reason(title),
                _declared_ids(body, match.group(1)),
            )
        )
    return rows
