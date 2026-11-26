"""Observed-outcome proof for ``test-quality``: a test must notice a wrong outcome.

A TOML contract binds each collected test in a declared scope to the outcomes it must
verify (``return-value``, ``error-state``, ``side-effect``), each with the designated
assertion line and a bounded counterexample (one source replacement).  The runner works
on a disposable copy: the baseline must pass, and each counterexample must make the test
fail *at the designated assertion*.  A test that still passes, or has no applicable
outcome, is ``outcome-not-observed``.  A counterexample that fails elsewhere (import,
setup, an unrelated assertion), a skipped or uncollected test, an unsupported assertion
adapter or a timeout is ``CannotRun``.  A proof covers only the declared observables.
"""

from __future__ import annotations

import ast
import hashlib
import re
import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env

KINDS = ("return-value", "error-state", "side-effect")
_COPY_IGNORE = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "node_modules")


@dataclass(frozen=True)
class OutcomeContract:
    test: str
    subject: str
    outcomes: tuple[dict[str, object], ...]
    not_applicable: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class OutcomeProof:
    test: str
    kind: str
    baseline: str
    counterexample: str
    assertion: str
    status: str  # pass | fail | unchecked


@dataclass
class OutcomeResult:
    findings: list[tuple[str, int, str]] = field(default_factory=list)
    proofs: list[OutcomeProof] = field(default_factory=list)
    evidence: dict[str, object] = field(default_factory=dict)


def load_contracts(path: Path) -> tuple[list[str], list[str], int, list[OutcomeContract], str]:
    try:
        raw = path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"{path.name}: outcome contract is unreadable: {exc}") from exc
    try:
        runner = [str(a) for a in data["runner"]]
        scope = [str(s) for s in data["scope"]]
        contracts = [
            OutcomeContract(c["test"], c["subject"], tuple(c.get("outcomes", [])), tuple(c.get("not_applicable", [])))
            for c in data["contracts"]
        ]
        timeout = int(data.get("timeout", 120))
    except (KeyError, TypeError, ValueError) as exc:
        raise CannotRun(f"{path.name}: malformed outcome contract: {exc!r}") from exc
    if not runner or not scope:
        raise CannotRun(f"{path.name}: runner and scope must be non-empty")
    return runner, scope, timeout, contracts, hashlib.sha256(raw).hexdigest()


def _run(tree: Path, argv: list[str], timeout: int) -> str:
    try:
        proc = subprocess.run(  # noqa: S603 -- argument array from the declared policy
            argv, cwd=tree, env=sanitized_env(), capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise CannotRun(f"outcome run exceeded {timeout}s: {' '.join(argv)}") from exc
    except OSError as exc:
        raise CannotRun(f"outcome runner is unavailable: {exc}") from exc
    return proc.stdout + proc.stderr


def _statuses(output: str) -> dict[str, str]:
    return {
        m["id"]: m["state"]
        for m in re.finditer(r"^(?P<state>PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS) (?P<id>\S+)", output, re.M)
    }


def _collected(output: str) -> set[str]:
    return {line.split(" ")[0] for line in output.splitlines() if "::" in line and not line.startswith(("=", " "))}


def _assertion_kind(tree: ast.AST, line: int) -> str | None:
    """``assert`` for a real assert or ``pytest.raises``; ``None`` for a constant assert; else unsupported."""
    for node in ast.walk(tree):
        if getattr(node, "lineno", None) != line:
            continue
        if isinstance(node, ast.Assert):
            return None if isinstance(node.test, ast.Constant) else "assert"
        if isinstance(node, ast.With) and any(
            isinstance(i.context_expr, ast.Call) and getattr(i.context_expr.func, "attr", "") == "raises"
            for i in node.items
        ):
            return "assert"
    raise CannotRun(f"line {line} is not a supported assertion (assert or pytest.raises); add an adapter")


def _apply(tree: Path, change: dict[str, str], where: str) -> None:
    target = tree / change["file"]
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, KeyError) as exc:
        raise CannotRun(f"{where}: counterexample file is unreadable: {exc!r}") from exc
    if text.count(change["old"]) != 1:
        raise CannotRun(f"{where}: counterexample must match exactly once in {change['file']}")
    target.write_text(text.replace(change["old"], change["new"]), encoding="utf-8")


def check(root: Path, contract_path: Path) -> OutcomeResult:
    runner, scope, timeout, contracts, digest = load_contracts(contract_path)
    result = OutcomeResult()
    with tempfile.TemporaryDirectory(prefix="outcomes-") as tmp:
        base = Path(tmp) / "baseline"
        shutil.copytree(root, base, ignore=_COPY_IGNORE)
        collected = _collected(_run(base, [*runner, "--collect-only", "-q", *scope], timeout))
        by_test = {c.test: c for c in contracts}
        missing = sorted(set(by_test) - collected)
        if missing:
            raise CannotRun(f"contract tests not collected in scope: {missing}")
        states = _statuses(_run(base, [*runner, "-rA", "--tb=line", "-q", *scope], timeout))
        for test in sorted(collected):
            if states.get(test) == "SKIPPED":
                raise CannotRun(f"{test} was skipped; a skipped case proves nothing")
            if states.get(test) != "PASSED":
                raise CannotRun(f"baseline for {test} is {states.get(test, 'not run')}; the baseline must pass")
        for test in sorted(collected):
            file, _, name = test.partition("::")
            contract = by_test.get(test)
            applicable = [o for o in (contract.outcomes if contract else ()) if o.get("kind") in KINDS]
            if not applicable:
                line = next(
                    (
                        n.lineno
                        for n in ast.walk(ast.parse((root / file).read_text(encoding="utf-8")))
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name.split("[")[0]
                    ),
                    1,
                )
                result.findings.append((file, line, "outcome-not-observed"))
                continue
            module = ast.parse((root / file).read_text(encoding="utf-8"))
            for outcome in applicable:
                line = int(outcome["assertion_line"])  # type: ignore[call-overload]
                if _assertion_kind(module, line) is None:
                    result.findings.append((file, line, "outcome-not-observed"))
                    result.proofs.append(
                        OutcomeProof(test, str(outcome["kind"]), "pass", "not-run", f"{file}:{line}", "fail")
                    )
                    continue
                trial = Path(tmp) / f"trial{len(result.proofs)}"
                shutil.copytree(root, trial, ignore=_COPY_IGNORE)
                _apply(trial, dict(outcome["counterexample"]), test)  # type: ignore[call-overload]
                output = _run(trial, [*runner, "-rA", "--tb=line", "-q", test], timeout)
                state = _statuses(output).get(test)
                if state == "PASSED":
                    result.findings.append((file, line, "outcome-not-observed"))
                    status = "fail"
                elif state == "FAILED" and re.search(rf"{re.escape(file)}:{line}:", output):
                    status = "pass"
                else:
                    raise CannotRun(
                        f"{test}: counterexample failed outside the designated assertion {file}:{line} (unchecked)"
                    )
                result.proofs.append(
                    OutcomeProof(test, str(outcome["kind"]), "pass", state or "n/a", f"{file}:{line}", status)
                )
    result.findings.sort()
    result.evidence = {
        "policy_digest": digest,
        "source_digest": hashlib.sha256(
            b"".join((root / t.partition("::")[0]).read_bytes() for t in sorted({c.test for c in contracts}))
        ).hexdigest(),
        "proofs": [p.__dict__ for p in result.proofs],
        "not_applicable": [{"test": c.test, **n} for c in contracts for n in c.not_applicable],
        "scope": scope,
        "measured": "declared observables and counterexamples only; not all semantics",
    }
    return result
