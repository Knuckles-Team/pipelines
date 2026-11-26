"""lint-type: lint, import-order and type diagnostics with zero exceptions.

Every tracked first-party Python file of the staged snapshot is materialized in a
disposable directory and checked by three required phases: Ruff lint, Ruff
import-order and mypy.  No baseline, per-file ignore, inline ``noqa`` or
``type: ignore`` comment, disabled rule or ``ignore_errors`` override may hide a
finding, and the gate never installs a tool, autofixes or reaches the network.
A finding or suppression is exit 1.  A missing tool, a version mismatch, an
unsupported language, an incomplete scope, a timeout or malformed output is
``CannotRun`` (exit 2), locally and in CI; findings of the phases that did
complete are still printed.

Policy lives in ``[tool.pipelines_hooks.lint_type]``:
``language``, ``source_roots``, ``test_roots``, ``timeout_seconds``,
``line_length`` and ``tools`` (exact pinned versions of ``ruff`` and ``mypy``).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tokenize
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_bytes, repo_root
from pipelines_hooks.core.tracked import tracked_paths
from pipelines_hooks.core.validation_report import CheckRecord, Evidence, RuleRecord, ValidationReport

PHASES = ("lint", "import-order", "type")
TOOL_OF = {"lint": "ruff", "import-order": "ruff", "type": "mypy"}
DEFAULT_TOOLS = {"ruff": "0.15.22", "mypy": "2.4.0"}
SUPPORTED_LANGUAGE = "python"
_FOREIGN_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb", ".php", ".c", ".cc", ".cpp", ".cs"}
_SUPPRESSION_RE = re.compile(r"#\s*(?:noqa\b|type:\s*ignore\b|ruff:\s*noqa\b|mypy:\s*ignore-errors\b|pyright:)", re.I)
_CONFIG_SUPPRESSION_KEYS = {
    "ruff": ("ignore", "extend-ignore", "per-file-ignores", "extend-per-file-ignores", "exclude", "extend-exclude"),
    "mypy": ("ignore_errors", "disable_error_code", "exclude", "follow_imports", "ignore_missing_imports"),
}


@dataclass(frozen=True)
class AnalyzerInvocation:
    """One pinned analyzer phase: the exact argument array and its budget."""

    phase: str
    tool: str
    version: str
    argv: tuple[str, ...]
    timeout_seconds: int


@dataclass(frozen=True)
class CodeQualityPolicy:
    """Language profile, complete first-party roots, pinned tools and budgets."""

    language: str
    source_roots: tuple[str, ...]
    test_roots: tuple[str, ...]
    tools: dict[str, str]
    timeout_seconds: int = 300
    line_length: int = 120

    def __post_init__(self) -> None:
        if self.language != SUPPORTED_LANGUAGE:
            raise CannotRun(f"lint-type: unsupported language profile {self.language!r}")
        if not self.source_roots:
            raise CannotRun("lint-type: no first-party source roots are declared")
        missing = sorted(set(TOOL_OF.values()) - set(self.tools))
        if missing:
            raise CannotRun(f"lint-type: unpinned tools: {', '.join(missing)}")
        for name, version in self.tools.items():
            if not re.fullmatch(r"\d+(\.\d+){1,3}", str(version)):
                raise CannotRun(f"lint-type: tool {name} is not pinned to an exact version: {version!r}")
        if self.timeout_seconds < 1 or self.line_length < 1:
            raise CannotRun("lint-type: invocation budgets must be positive")

    @property
    def roots(self) -> tuple[str, ...]:
        return self.source_roots + self.test_roots

    def invocation(self, phase: str) -> AnalyzerInvocation:
        tool = TOOL_OF[phase]
        if phase == "type":
            argv: tuple[str, ...] = (tool, "--output", "json", "--no-incremental", "--cache-dir=/dev/null", *self.roots)
        else:
            select = "I" if phase == "import-order" else "E,F,W"
            argv = (
                tool, "check", "--isolated", "--no-cache", f"--line-length={self.line_length}",
                f"--select={select}", "--output-format", "json", *self.roots,
            )  # fmt: skip
        return AnalyzerInvocation(phase, tool, self.tools[tool], argv, self.timeout_seconds)

    def digest(self) -> str:
        blob = json.dumps(
            [self.language, self.source_roots, self.test_roots, sorted(self.tools.items()), self.line_length],
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()


def _pyproject(root: Path) -> dict[str, object]:
    raw = blob_bytes(root, ":pyproject.toml")
    if raw is None:
        raise CannotRun("lint-type: pyproject.toml is not in the snapshot")
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"lint-type: pyproject.toml is unreadable: {exc}") from exc


def load_policy(root: Path, files: list[str]) -> tuple[CodeQualityPolicy, dict[str, object]]:
    data = _pyproject(root)
    tool = data.get("tool", {})
    section = tool.get("pipelines_hooks", {}) if isinstance(tool, dict) else {}
    declared = section.get("lint_type", {}) if isinstance(section, dict) else {}
    if not isinstance(declared, dict):
        raise CannotRun("lint-type: [tool.pipelines_hooks.lint_type] must be a table")
    packages = section.get("packages", []) if isinstance(section, dict) else []
    top = sorted({f.split("/")[0] for f in files if f.endswith(".py") and "/" in f})
    tests = [name for name in ("tests",) if name in top]
    source = tuple(declared.get("source_roots", [p for p in packages if p in top]))
    policy = CodeQualityPolicy(
        language=str(declared.get("language", SUPPORTED_LANGUAGE)),
        source_roots=source,
        test_roots=tuple(declared.get("test_roots", tests)),
        tools={**DEFAULT_TOOLS, **dict(declared.get("tools", {}))},
        timeout_seconds=int(declared.get("timeout_seconds", 300)),
        line_length=int(declared.get("line_length", 120)),
    )
    return policy, data


def _in_scope(path: str, policy: CodeQualityPolicy) -> bool:
    return any(path == r or path.startswith(r.rstrip("/") + "/") for r in policy.roots)


def scope_findings(files: list[str], policy: CodeQualityPolicy) -> list[str]:
    """Refuse a policy whose roots omit tracked Python or contain unsupported languages."""
    problems = [f"{f} is outside the declared roots" for f in files if f.endswith(".py") and not _in_scope(f, policy)]
    problems += [
        f"{f} uses an unsupported language"
        for f in files
        if _in_scope(f, policy) and Path(f).suffix in _FOREIGN_SUFFIXES
    ]
    return problems


def suppression_findings(root: Path, files: list[str], pyproject: dict[str, object]) -> list[Evidence]:
    """Inline comments and effective configuration that would hide a finding."""
    found: list[Evidence] = []
    for rel in files:
        raw = blob_bytes(root, f":{rel}") or b""
        try:
            for token in tokenize.generate_tokens(io.StringIO(raw.decode("utf-8")).readline):
                if token.type == tokenize.COMMENT and _SUPPRESSION_RE.search(token.string):
                    found.append(Evidence(path=rel, line=token.start[0], observed=token.string.strip()[:80]))
        except (tokenize.TokenError, IndentationError, UnicodeError) as exc:
            raise CannotRun(f"lint-type: {rel} cannot be tokenized: {exc}") from exc
    tool = pyproject.get("tool", {})
    tool = tool if isinstance(tool, dict) else {}
    ruff = tool.get("ruff", {}) if isinstance(tool.get("ruff"), dict) else {}
    lint = ruff.get("lint", {}) if isinstance(ruff.get("lint"), dict) else {}
    for table in (ruff, lint):
        for key in _CONFIG_SUPPRESSION_KEYS["ruff"]:
            if table.get(key):
                found.append(
                    Evidence(path="pyproject.toml", observed=f"tool.ruff {key}", detail="configuration suppression")
                )
    mypy_tables = [tool.get("mypy", {})] + [
        o for o in (tool.get("mypy", {}) or {}).get("overrides", []) if isinstance(o, dict)
    ]
    for table in mypy_tables:
        if isinstance(table, dict):
            for key in ("ignore_errors", "disable_error_code", "exclude"):
                if table.get(key):
                    found.append(
                        Evidence(path="pyproject.toml", observed=f"tool.mypy {key}", detail="configuration suppression")
                    )
    return found


def materialize(root: Path, files: list[str], pyproject: bytes, dest: Path) -> str:
    """Write the staged blobs of ``files`` into ``dest`` and return their joint digest."""
    digest = hashlib.sha256()
    for rel in sorted(files):
        raw = blob_bytes(root, f":{rel}")
        if raw is None:
            raise CannotRun(f"lint-type: {rel} vanished from the snapshot")
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        digest.update(rel.encode() + b"\0" + hashlib.sha256(raw).digest())
    (dest / "pyproject.toml").write_bytes(pyproject)
    return digest.hexdigest()


def _tool_path(name: str) -> str | None:
    beside = Path(sys.executable).parent / name
    return str(beside) if beside.is_file() else shutil.which(name)


def _tool_version(path: str) -> str:
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30, check=False).stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CannotRun(f"cannot query tool version: {exc}") from exc
    match = re.search(r"\d+(?:\.\d+)+", out)
    return match.group(0) if match else ""


def _ruff_diagnostics(stdout: str, dest: Path) -> list[Evidence]:
    items = json.loads(stdout or "[]")
    return [
        Evidence(
            path=Path(i["filename"]).resolve().relative_to(dest.resolve()).as_posix(),
            line=i["location"]["row"],
            observed=i["code"],
            expected="no diagnostic",
            detail=i["message"],
        )
        for i in items
    ]


def _mypy_diagnostics(stdout: str) -> list[Evidence]:
    found = []
    for raw in stdout.splitlines():
        if not raw.startswith("{"):
            continue
        i = json.loads(raw)
        if i.get("severity") == "error":
            found.append(
                Evidence(path=i["file"], line=max(int(i["line"]), 1), observed=i.get("code") or "error",
                         expected="no diagnostic", detail=i["message"])
            )  # fmt: skip
    return found


def run_phase(policy: CodeQualityPolicy, phase: str, dest: Path, source_digest: str) -> CheckRecord:
    """Run one phase; an unavailable or misbehaving tool is a ``cannot-run`` record, never a pass."""
    invocation = policy.invocation(phase)
    base: dict[str, Any] = {
        "category": phase,
        "identity": f"{invocation.tool}=={invocation.version}",
        "command": invocation.argv,
        "source_digest": source_digest,
        "policy_digest": policy.digest(),
        "scope": policy.roots,
    }
    path = _tool_path(invocation.tool)
    if path is None:
        return CheckRecord(**base, status="cannot-run", status_reason=f"{invocation.tool} is not installed")
    found = _tool_version(path)
    if found != invocation.version:
        reason = f"{invocation.tool} version {found or 'unknown'} does not match pinned {invocation.version}"
        return CheckRecord(**base, status="cannot-run", status_reason=reason)
    started = time.monotonic()
    try:
        result = subprocess.run(
            [path, *invocation.argv[1:]], cwd=dest, capture_output=True, text=True,
            timeout=invocation.timeout_seconds, check=False, env={"PATH": str(Path(path).parent), "HOME": str(dest)},
        )  # fmt: skip
        diagnostics = (
            _ruff_diagnostics(result.stdout, dest) if invocation.tool == "ruff" else _mypy_diagnostics(result.stdout)
        )
        if result.returncode not in (0, 1) or (result.returncode == 1 and not diagnostics):
            raise ValueError(f"exit {result.returncode}: {(result.stderr or result.stdout)[:200]}")
    except subprocess.TimeoutExpired:
        return CheckRecord(**base, status="cannot-run", status_reason=f"{invocation.tool} timed out")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return CheckRecord(**base, status="cannot-run", status_reason=f"{invocation.tool} output unusable: {exc}")
    elapsed = int((time.monotonic() - started) * 1000)
    by_rule: dict[str, list[Evidence]] = {}
    for item in diagnostics:
        by_rule.setdefault(item.observed or "unknown", []).append(item)
    rules = [RuleRecord(rule=code, outcome="fail", reason=f"{len(items)} diagnostic(s)", evidence=tuple(items))
             for code, items in by_rule.items()]  # fmt: skip
    if not rules:
        rules = [RuleRecord(rule=f"{phase}-clean", outcome="pass", reason="no diagnostics")]
    return CheckRecord(**base, status="complete", duration_ms=elapsed, rules=tuple(rules))


def analyze(root: Path) -> list[CheckRecord]:
    """Check the staged snapshot; one record per phase, suppression findings under ``lint``."""
    files = [f for f in tracked_paths(root, ("*.py",)) if not f.startswith(("/", "../"))]
    all_tracked = tracked_paths(root)
    policy, data = load_policy(root, files)
    problems = scope_findings(
        sorted(set(files) | {f for f in all_tracked if Path(f).suffix in _FOREIGN_SUFFIXES}), policy
    )
    if problems:
        raise CannotRun("lint-type: incomplete scope: " + "; ".join(problems[:5]))
    scoped = [f for f in files if _in_scope(f, policy)]
    suppressions = suppression_findings(root, scoped, data)
    records: list[CheckRecord] = []
    with tempfile.TemporaryDirectory(prefix="lint-type-") as tmp:
        dest = Path(tmp)
        digest = materialize(root, scoped, blob_bytes(root, ":pyproject.toml") or b"", dest)
        for phase in PHASES:
            record = run_phase(policy, phase, dest, digest)
            if phase == "lint" and suppressions:
                extra = RuleRecord(
                    rule="suppression", outcome="fail", reason="a finding may be hidden", evidence=tuple(suppressions)
                )
                record = record.model_copy(update={"rules": (*record.rules, extra)})
            records.append(record)
    return records


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="lint-type", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    records = analyze(root)
    report = ValidationReport.build(repository=root.name, snapshot="index", checks=records)
    for record in records:
        print(
            f"lint-type: {record.category} tool={record.identity} status={record.status} "
            f"source={record.source_digest[:12]} argv={' '.join(record.command)}"
        )
        if record.status_reason:
            print(f"  cannot run: {record.status_reason}")
        for rule in record.rules:
            for item in rule.evidence if rule.outcome == "fail" else ():
                print(f"  {item.path}:{item.line} {rule.rule} {item.detail}")
    if report.verdict == "cannot-run":
        raise CannotRun("lint-type: a required phase could not run")
    print("lint-type: clean" if report.verdict == "pass" else "FAIL: lint-type findings.")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
