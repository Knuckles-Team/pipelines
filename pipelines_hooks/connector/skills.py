"""connector-standard member: the packaged skills pass the universal-skills gates.

Atomicity (atomic skills, dual-mode workflows), cross-agent frontmatter portability and cross-platform path portability,
run over the connector's package ``skills`` directory (the first directory named ``skills`` within two levels). The gate
logic is the universal-skills checks, ported under ``skill_checks``; a connector adds no hook and no wrapper script.
A connector without skills passes. ``[tool.pipelines.skills] path_exclude`` lists directories (relative to the root) the path check
leaves out (generated reference content whose upstream names are long).
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

from pipelines_hooks.connector import project
from pipelines_hooks.connector.skill_checks import atomicity, frontmatter, paths

MAX_PATH, MAX_NAME = 200, 100


def skills_dir(root: Path) -> Path | None:
    """The first directory named ``skills`` at depth one or two under ``root``, as the shell hook found it."""
    for depth in (1, 2):
        found = sorted(p for p in root.glob("/".join(["*"] * depth)) if p.is_dir() and p.name == "skills")
        if found:
            return found[0]
    return None


def _table(root: Path) -> dict[str, object]:
    return dict(project.load(root).get("tool", {}).get("pipelines", {}).get("skills", {}))


def _quiet(call: object, *args: object) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = call(*args)  # type: ignore[operator]
    return int(code), out.getvalue()


def main(argv: list[str]) -> int:
    root = Path.cwd()
    skills = skills_dir(root)
    if skills is None:
        print("connector-skills: OK: no skills directory")
        return 0
    exclude = [str(x).strip("/") for x in _table(root).get("path_exclude", [])]  # type: ignore[attr-defined]
    excluded = [arg for e in exclude for arg in ("--exclude", e)]
    checks = (
        ("atomicity", atomicity.main, ["--root", str(skills)]),
        ("frontmatter-portability", frontmatter.main, [str(skills), "--max-violations", "0"]),
        (
            "path-portability",
            paths.main,
            [str(root), "--max-path", str(MAX_PATH), "--max-name", str(MAX_NAME), "--max-violations", "0", *excluded],
        ),
    )
    failed: list[str] = []
    for name, run, args in checks:
        code, text = _quiet(run, args)
        if code:
            failed.append(name)
            print(f"connector-skills: {name} FAILED\n{text.rstrip()}")
    if failed:
        print(f"connector-skills: FAILED checks: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("connector-skills: OK: atomicity, frontmatter portability and path portability hold")
    return 0
