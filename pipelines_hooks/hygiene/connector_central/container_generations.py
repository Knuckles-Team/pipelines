"""Recorded older generations of the connector container files (PIPE-GATES-R016.92).

Rule ``pl.o`` replaces committed ``docker/*`` files by the shared render. A committed file that differs from the render is
accepted only when the difference is a *recorded older generator form*, never for any other reason:

* ``dockerfile_forms``: whole-file fingerprints of the single-stage ``Dockerfile`` that the earlier MCP-only scaffold wrote
  (no ``runtime-base`` stage). The fingerprint is the SHA-256 of the file with comments and blank lines dropped and the
  connector's name, pinned version, entry point, base-image digest, host, port, uid and home placeholdered, so a hand
  edit changes the hash and the file keeps blocking.
* ``stubs``: whole-file fingerprints of stub ``debug.Dockerfile`` / ``*.compose.yml`` files of that scaffold.
* ``rewrites``: exact line blocks the earlier generator wrote where the render now writes a different block
  (``<DIST>``, ``<DISTVAR>``, ``<PORT>`` and ``<HOST>`` stand for the connector's own values). A rewrite
  turns the old block into the new block; the file is accepted only when, after every recorded rewrite, it equals the
  render byte for byte.

The data lives in ``container_generations.json`` and is built from the fleet by ``scripts/connector_central_generations.py``
(every entry occurs in several repositories, so only generator output survives, never a hand edit).
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

GENERATIONS_PATH = Path(__file__).with_name("container_generations.json")
_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}")


@cache
def load() -> dict[str, Any]:
    if not GENERATIONS_PATH.is_file():
        return {"dockerfile_forms": {}, "stubs": {}, "rewrites": []}
    return json.loads(GENERATIONS_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def loose_lines(text: str) -> list[str]:
    """The instruction lines: blank lines, full-line comments and the compose ``version:`` key are dropped."""
    return [
        ln
        for ln in text.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#") and not ln.startswith("version:")
    ]


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _first(pattern: str, text: str, default: str) -> str:
    match = re.search(pattern, text, re.M)
    return match.group(1) if match else default


def dockerfile_form(text: str, dist: str) -> str:
    """The placeholdered, comment-free text of a single-stage ``Dockerfile`` (input of its fingerprint)."""
    uid = _first(r"^USER\s+(\d+)", text, "") or _first(r"useradd[^\n]*--uid\s+(\d+)", text, "10001")
    home = _first(r"^\s*(?:ENV\s+)?HOME=(\S+?)\s*\\?$", text, "/tmp")
    out = "\n".join(loose_lines(text))
    out = out.replace(dist, "<DIST>").replace(dist.replace("-", "_"), "<PKG>")
    out = re.sub(r" --no-binary \S+", "", out)  # the sdist names go to the table (``sdist_deps``), not the fingerprint
    out = re.sub(r"==\d+\.\d+\.\d+", "==<SEMVER>", out)
    out = _DIGEST.sub("@sha256:<DIGEST>", out)
    out = re.sub(r'(?m)^CMD \["[^"]+"\]$', 'CMD ["<ENTRY>"]', out)
    out = re.sub(r"(?m)^ARG HOST=\S+$", "ARG HOST=<HOST>", out)
    out = re.sub(r"(?m)^ARG PORT=\S+$", "ARG PORT=<PORT>", out)
    out = re.sub(rf"\b{re.escape(uid)}\b", "<UID>", out)
    return out.replace(home, "<HOME>") + "\n"


def is_older_dockerfile(text: str, dist: str) -> bool:
    return digest(dockerfile_form(text, dist)) in load()["dockerfile_forms"]


def older_sdist_deps(text: str) -> list[str]:
    """``--no-binary`` names on the older generation's one ``pip install`` line."""
    out: list[str] = []
    for line in text.splitlines():
        if "pip install" in line:
            out += [n for n in re.findall(r"--no-binary (\S+)", line) if n not in out]
    return out


def is_stub(name: str, text: str) -> bool:
    return digest("\n".join(loose_lines(text)) + "\n") in load()["stubs"].get(name, {})


def placeholders(dist: str, port: str, host: str = "127.0.0.1") -> dict[str, str]:
    return {"<DIST>": dist, "<DISTVAR>": re.sub(r"[^A-Z0-9]", "_", dist.upper()), "<PORT>": port, "<HOST>": host}


def _expand(lines: list[str], values: dict[str, str]) -> list[str]:
    out = []
    for line in lines:
        for key, value in values.items():
            line = line.replace(key, value)
        out.append(line)
    return out


EXTRAS = "<EXTRAS>"
ANY = "<ANY>"
#: Capturing placeholders of a recorded block: the text they match in the old block is carried into the new block.
CAPTURES = {EXTRAS: r"(?:\[[A-Za-z0-9_,-]*\])?", ANY: r"[^\s]+", "<PKGS>": r"[^\\]*[^\s\\]"}


def _line_pattern(line: str) -> re.Pattern[str]:
    out = re.escape(line)
    for token, pattern in CAPTURES.items():
        out = out.replace(re.escape(token), f"(?P<{token.strip('<>')}>{pattern})")
    return re.compile(out)


def match_block(lines: list[str], start: int, old: list[str]) -> dict[str, str] | None:
    """The placeholder texts the ``old`` block carries at ``start``; None when it does not match there."""
    found: dict[str, str] = {}
    for offset, want in enumerate(old):
        match = _line_pattern(want).fullmatch(lines[start + offset])
        if match is None:
            return None
        found.update(match.groupdict())
    return {f"<{k}>": v for k, v in found.items()}


def _fill(block: list[str], found: dict[str, str]) -> list[str]:
    out = []
    for line in block:
        for token, value in found.items():
            line = line.replace(token, value)
        out.append(line)
    return out


def rewrite_entries(
    entries: list[dict[str, Any]],
    name: str,
    text: str,
    dist: str,
    port: str,
    counts: dict[int, int] | None = None,
    host: str = "127.0.0.1",
) -> str:
    """Apply ``entries`` (for file ``name``) to the normalised ``text``, in order.

    A line ending ``.<EXTRAS>`` installs the local wheel with whatever extras the old file named, which the new block
    keeps (the caller then drops the ones rule l4 removed from the wheel). An entry whose new block is its old block
    followed by more lines is an insertion and is skipped where those lines already follow, so a rewrite never applies
    twice. ``counts`` collects, per entry index, how often the entry changed the text.
    """
    values = placeholders(dist, port, host)
    lines = text.splitlines()
    for index, entry in enumerate(entries):
        if entry["file"] != name:
            continue
        old, new = _expand(entry["old"], values), _expand(entry["new"], values)
        new = [ln for ln in new if ln.strip()]  # a deleted block is recorded as an empty line
        i = 0
        while i + len(old) <= len(lines):
            found = match_block(lines, i, old)
            if found is None:
                i += 1
                continue
            block = _fill(new, found)
            head = _fill(old, found)
            if block[: len(head)] == head and len(block) > len(head):
                follow = lines[i + len(head) : i + len(head) + 1]
                if follow == block[len(head) : len(head) + 1]:
                    i += len(head)  # the inserted lines are already there (their values are the file's own)
                    continue
            if block and lines[i : i + len(block)] == block:
                i += len(block)
                continue
            lines[i : i + len(old)] = block
            if counts is not None:
                counts[index] = counts.get(index, 0) + 1
            i += len(block)
    return "\n".join(lines) + "\n"


def apply_rewrites(name: str, text: str, dist: str, port: str, host: str = "127.0.0.1") -> str:
    """Apply every recorded older-generation block rewrite for file ``name`` to the normalised ``text``.

    ``<HOST>`` in a recorded block is the host the connector's image binds (the table's ``host``, default 127.0.0.1).
    """
    return rewrite_entries(load()["rewrites"], name, text, dist, port, host=host)
