"""Find external build binaries a ``.cargo/config.toml`` hard-depends on.

A replica that compares commands cannot catch "the build needs a binary the CI
runner lacks": the developer host has it, so the command succeeds there. cargo
hard-errors on a missing rustc-wrapper, linker or runner, so each one must be
mentioned somewhere in every workflow that runs cargo. An absent config is not
a finding.
"""

from __future__ import annotations

import re
from pathlib import Path

_SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_KEY_VALUE_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.'\"-]+)\s*=\s*(?P<value>.+?)\s*$")
_FUSE_LD_RE = re.compile(r"-fuse-ld=([A-Za-z0-9_.+-]+)")
_C_LINKER_RE = re.compile(r"-C\s*linker=([^\s\"']+)")


def parse_sections(text: str) -> list[tuple[str, str, str]]:
    """``(section, key, value)`` for every key; multi-line arrays are joined into one value."""
    section, results, pending, depth = "", [], None, 0
    for raw in text.splitlines():
        stripped = raw.split("#", 1)[0].strip()
        if depth:
            pending = (pending[0], pending[1] + " " + stripped)
            depth += stripped.count("[") - stripped.count("]")
        elif (header := _SECTION_RE.match(stripped)) is not None:
            section = header.group("name").strip("'\" ")
        elif (pair := _KEY_VALUE_RE.match(stripped)) is not None:
            pending = (pair.group("key").strip("'\""), pair.group("value"))
            depth = pair.group("value").count("[") - pair.group("value").count("]")
        if pending is not None and depth <= 0:
            results.append((section, *pending))
            pending, depth = None, 0
    return results


def _wrapper(section: str, key: str, value: str) -> list[tuple[str, str]]:
    unquoted = value.strip().strip("'\"")
    if key == "rustc-wrapper" and section in ("build", "") and unquoted:
        return [(unquoted, f"[{section or 'build'}] rustc-wrapper")]
    quoted = re.search(r"[\"']([^\"']+)[\"']", value) if key.upper() == "RUSTC_WRAPPER" and section == "env" else None
    return [(quoted.group(1), "[env] RUSTC_WRAPPER")] if quoted else []


def _target_tools(section: str, key: str, value: str) -> list[tuple[str, str]]:
    unquoted = value.strip().strip("'\"")
    if key in ("linker", "runner") and unquoted:
        return [(Path(unquoted.split()[0]).name, f"[{section}] {key}")]
    if key != "rustflags":
        return []
    fuse = [(m.group(1), f"[{section}] rustflags -fuse-ld") for m in _FUSE_LD_RE.finditer(value)]
    return fuse + [(Path(m.group(1)).name, f"[{section}] rustflags -C linker") for m in _C_LINKER_RE.finditer(value)]


def _binaries_for(section: str, key: str, value: str) -> list[tuple[str, str]]:
    if section.startswith("target."):
        return _target_tools(section, key, value)
    return _wrapper(section, key, value)


def required_build_binaries(config: Path) -> list[tuple[str, str]]:
    if not config.is_file():
        return []
    return [b for section, key, value in parse_sections(config.read_text(encoding="utf-8")) for b in _binaries_for(section, key, value)]


def build_tool_problems(config: Path, workflow_texts: dict[str, str]) -> list[str]:
    """One problem per required binary that a cargo-running workflow never mentions."""
    problems = []
    for binary, origin in required_build_binaries(config):
        missing = sorted(
            name for name, text in workflow_texts.items() if re.search(r"\bcargo\b", text) and not re.search(rf"\b{re.escape(binary)}\b", text)
        )
        if missing:
            problems.append(f"'{binary}' (required by {origin}) is never installed or referenced in: {', '.join(missing)}")
    return problems
