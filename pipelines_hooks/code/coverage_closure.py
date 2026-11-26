"""Coverage closure for ``test-quality --closure``: zero uncovered executable lines per project.

The 80 percent floor is an ordinary threshold and never satisfies closure.  Each declared
project runs its own runner argv in a disposable snapshot and must write a coverage.py JSON
report; every first-party source under the declared roots must appear in it with an empty
``missing_lines``.  A file with no executable statements is a visible zero-line file.  A
missing runner, report or declared file set, a failing runner or a timeout is ``CannotRun``;
the report is deleted before the run so a stale report can never be read.
"""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env

_IGNORE = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "node_modules")


@dataclass
class ClosureResult:
    findings: list[tuple[str, int, str]] = field(default_factory=list)
    projects: list[dict[str, object]] = field(default_factory=list)


def _executable(source: str) -> bool:
    body = ast.parse(source).body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return bool(body)


def check(root: Path, policy_path: Path) -> ClosureResult:
    try:
        raw = policy_path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
        projects = list(data["projects"])
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError) as exc:
        raise CannotRun(f"{policy_path.name}: coverage closure policy is unreadable: {exc!r}") from exc
    if not projects:
        raise CannotRun(f"{policy_path.name}: no projects declared")
    result = ClosureResult()
    policy_digest = hashlib.sha256(raw).hexdigest()
    for project in projects:
        name = str(project.get("name", ""))
        runner, sources = project.get("runner"), project.get("sources")
        if not name or not runner or not sources:
            raise CannotRun(
                f"{policy_path.name}: project {name or '?'} needs a runner and sources (skipped projects refuse)"
            )
        excluded = {e["path"] for e in project.get("generated_exclusions", []) if e.get("producer")}
        base = root / project.get("root", ".")
        report_rel = project.get("report", "coverage.json")
        timeout = int(project.get("timeout", 300))
        with tempfile.TemporaryDirectory(prefix="closure-") as tmp:
            tree = Path(tmp) / "snapshot"
            shutil.copytree(root, tree, ignore=_IGNORE)
            work = tree / base.relative_to(root)
            (work / report_rel).unlink(missing_ok=True)
            try:
                proc = subprocess.run(  # noqa: S603 -- declared argv
                    [str(a) for a in runner],
                    cwd=work,
                    env=sanitized_env(),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                raise CannotRun(f"project {name}: runner did not finish: {exc!r}") from exc
            if proc.returncode != 0:
                raise CannotRun(
                    f"project {name}: runner exited {proc.returncode}: {(proc.stdout + proc.stderr)[-300:]}"
                )
            try:
                files = json.loads((work / report_rel).read_text(encoding="utf-8"))["files"]
            except (OSError, ValueError, KeyError) as exc:
                raise CannotRun(f"project {name}: runner produced no coverage.py JSON report: {exc!r}") from exc
        reported = {Path(k).as_posix(): v for k, v in files.items()}
        entry: dict[str, object] = {"project": name, "policy_digest": policy_digest, "files": {}, "zero_line": []}
        digest = hashlib.sha256()
        for source in sorted(sources):
            for path in sorted((base / source).rglob("*.py")):
                rel_project = path.relative_to(base).as_posix()
                rel = path.relative_to(root).as_posix()
                if rel in excluded or rel_project in excluded:
                    continue
                text = path.read_text(encoding="utf-8")
                digest.update(text.encode())
                if not _executable(text):
                    entry["zero_line"].append(rel)  # type: ignore[union-attr]
                    continue
                record = reported.get(rel_project) or reported.get(rel)
                if record is None:
                    result.findings.append((rel, 1, "coverage-below-threshold"))
                    entry["files"][rel] = {"reported": False}  # type: ignore[index]
                    continue
                missing = sorted(record.get("missing_lines", []))
                entry["files"][rel] = {  # type: ignore[index]
                    "executed": len(record.get("executed_lines", [])),
                    "uncovered": missing,
                }
                result.findings.extend((rel, line, "coverage-below-threshold") for line in missing)
        entry["source_digest"] = digest.hexdigest()
        result.projects.append(entry)
    result.findings.sort()
    return result
