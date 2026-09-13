"""Syntax rules for one Mermaid block (flowcharts and sequence diagrams)."""

from __future__ import annotations

import re
from collections.abc import Sequence

Finding = dict[str, object]
BlockLine = tuple[int, str]

ILLEGAL_UNQUOTED_CHARS = ("(", ")", "[", "]", "{", "}", "<", ">", "&", ";", ",")
#: Longer shapes precede shorter ones; edge labels are masked first so an
#: asymmetric shape cannot start inside ``|label|`` and swallow the next node.
FLOW_SHAPE_PATTERN = re.compile(
    r"\b[a-zA-Z0-9_-]+\s*(?:"
    r'\(\[(".*?")\]\)|\[\[(".*?")\]\]|\[\((".*?")\)\]|\(\((".*?")\)\)|\{\{(".*?")\}\}|>\s*(".*?")\]|'
    r'\[(".*?")\]|\((".*?")\)|\{(".*?")\}|'
    r"\(\[(.*?)\]\)|\[\[(.*?)\]\]|\[\((.*?)\)\]|\(\((.*?)\)\)|\{\{(.*?)\}\}|>\s*(.*?)\]|"
    r"\[(.*?)\]|\((.*?)\)|\{(.*?)\})"
)
EDGE_LABEL_PATTERN = re.compile(r"\|[^|\n]*\|")
SEQUENCE_ARROW_PATTERN = re.compile(r"(-->>|->>|-->|->|--x|-x|--\)|-\))")
SEQUENCE_OPENERS = frozenset(("alt", "loop", "rect", "opt", "par", "critical", "break"))
SEQUENCE_DIRECTIVES = frozenset(
    "participant actor note autonumber activate deactivate alt else end loop rect opt par critical break".split()
)
SEQUENCE_ARROWS = frozenset(("->", "-->", "->>", "-->>", "-x", "--x", "-)", "--)"))


def _unquoted_label_message(match: tuple[str, ...]) -> str | None:
    label = next((item for item in match if item), "").strip()
    bad = [char for char in ILLEGAL_UNQUOTED_CHARS if char in label]
    if not label or not bad or (label.startswith('"') and label.endswith('"')):
        return None
    return f"Unquoted special character(s) {bad} in node label '{label}'. Quote the label."


def _flow_findings(line: int, clean: str) -> list[Finding]:
    messages = map(_unquoted_label_message, FLOW_SHAPE_PATTERN.findall(EDGE_LABEL_PATTERN.sub(" ", clean)))
    findings: list[Finding] = [{"line": line, "message": message} for message in messages if message]
    if "-- |" in clean or "--  |" in clean:
        findings.append({"line": line, "message": "Invalid arrow label syntax. Use '-->|label|' or '-- label -->'."})
    return findings


def _sequence_structure(line: int, word: str, stack: list[BlockLine]) -> list[Finding]:
    if word in SEQUENCE_OPENERS:
        stack.append((line, word))
        return []
    if word == "else" and (not stack or stack[-1][1] not in ("alt", "critical")):
        return [{"line": line, "message": "Found 'else' without a matching active 'alt' or 'critical' block."}]
    if word == "end" and not stack:
        return [{"line": line, "message": "Found 'end' without a matching opening block."}]
    if word == "end":
        stack.pop()
    return []


def _sequence_arrow(line: int, clean: str, word: str) -> list[Finding]:
    if word in SEQUENCE_DIRECTIVES or ":" not in clean:
        return []
    arrow = SEQUENCE_ARROW_PATTERN.search(clean.split(":", 1)[0].strip())
    if not arrow or arrow.group(1) in SEQUENCE_ARROWS:
        return []
    return [{"line": line, "message": f"Potential invalid arrow syntax '{arrow.group(1)}' in sequence diagram."}]


def _content_findings(diagram: str, line: int, clean: str, *, stack: list[BlockLine]) -> list[Finding]:
    findings: list[Finding] = []
    if clean.replace('\\"', "").count('"') % 2:
        findings.append({"line": line, "message": "Mismatched double quotes on line (odd number of quotes)."})
    if diagram in ("graph", "flowchart"):
        findings.extend(_flow_findings(line, clean))
    elif diagram == "sequencediagram":
        word = clean.split()[0].lower()
        findings.extend(_sequence_structure(line, word, stack))
        findings.extend(_sequence_arrow(line, clean, word))
    return findings


def validate_block(start_line: int, block: Sequence[BlockLine]) -> list[Finding]:
    """Line-numbered findings for one Mermaid block."""
    meaningful = [(line, text.strip()) for line, text in block if text.strip() and not text.strip().startswith("%%")]
    if not meaningful:
        return [{"line": start_line, "message": "Empty or undeclared Mermaid diagram block."}] if block else []
    diagram = meaningful[0][1].split()[0].lower()
    stack: list[BlockLine] = []
    findings = [f for line, clean in meaningful[1:] for f in _content_findings(diagram, line, clean, stack=stack)]
    findings.extend({"line": line, "message": f"Unclosed sequence diagram block: '{kind}' has no matching 'end'."} for line, kind in stack)
    return findings
