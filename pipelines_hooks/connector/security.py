"""connector-security: the shared security checks and contract every connector used to copy into ``.security/``.

Three files were copied into about 69 repositories: ``repository_fuzz.py``, ``authenticated_negative.py`` and
``security-contract.json``. They are provided here instead:

* ``pipelines-connector security fuzz OUT`` mutates the repository's top-level JSON/TOML files and writes the evidence;
* ``pipelines-connector security authenticated-negative OUT`` checks the workflow control plane (privileged
  triggers, broad permissions, secrets in shell, mutable action references) and writes the evidence;
* ``pipelines-connector security contract [--out PATH]`` prints the effective contract: the shared default hooks and
  license policy plus ``[tool.pipelines.security] license_allowed / license_denied``;
* with no subcommand (the ``connector-standard`` member) it runs both checks and the contract validation.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pipelines_hooks.connector import project
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root

DEFAULT_CONTRACT = Path(__file__).resolve().parent / "defaults" / "security-contract.json"
SECURITY_KEYS = frozenset({"license_allowed", "license_denied"})
MAX_FILES = 16
MAX_SOURCE_BYTES = 1024 * 1024
MAX_CASES = 64

#: Workflow documents the negative check must reject; accepting one is an unauthorized acceptance.
NEGATIVE_CASES = (
    "on:\n  pull_request_target:\npermissions: {}\n",
    "on: push\npermissions: write-all\n",
    "on: push\npermissions: {}\njobs:\n  x:\n    steps:\n      - uses: owner/action@main\n",
    "on: push\npermissions: {}\njobs:\n  x:\n    uses: Knuckles-Team/pipelines-evil/.github/workflows/x.yml@main\n",
    "on: push\npermissions: {}\njobs:\n  x:\n    steps:\n      - run: echo '${{ secrets.RUNTIME_TOKEN }}'\n",
)
ACTION_REF = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
PINNED_ACTION = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?@[0-9a-f]{40}")
#: The organization's own shared workflow repository: the only place a ``@main`` reference is allowed (org plus repo,
#: exact). Every repository references these workflows at ``main`` and never pins them; third-party actions stay
#: pinned to a commit SHA.
OWN_WORKFLOW_REF = re.compile(r"Knuckles-Team/pipelines/\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml@main")
PINNED_IMAGE = re.compile(r"docker://[^\s]+@sha256:[0-9a-f]{64}")


# --- fuzz -----------------------------------------------------------------------------------------------------
def _corpus(root: Path) -> list[tuple[str, bytes]]:
    values: list[tuple[str, bytes]] = []
    try:
        candidates = sorted(p for p in root.iterdir() if p.suffix.casefold() in {".json", ".toml"})[:MAX_FILES]
    except OSError:
        candidates = []
    for path in candidates:
        try:
            if path.is_symlink() or not 0 < path.stat().st_size <= MAX_SOURCE_BYTES:
                continue
            values.append((path.suffix.casefold(), path.read_bytes()))
        except OSError:
            continue
    return values


def _mutations(payload: bytes) -> tuple[bytes, ...]:
    midpoint = max(1, len(payload) // 2)
    return (
        payload[:midpoint],
        payload + b"\x00",
        b"{" * 128 + payload[:64],
        b"[" * 128 + payload[:64],
        payload[:32] + b"\xff\xfe" + payload[32:64],
        b"null trailing",
        b"key = [1, 2,",
        b"\n" * 4096 + payload[:128],
    )


def _case_stream(corpus: list[tuple[str, bytes]]) -> Iterator[tuple[str, bytes]]:
    while True:
        for suffix, payload in corpus:
            for mutation in _mutations(payload):
                yield suffix, mutation


def _is_crash(suffix: str, mutation: bytes) -> bool:
    """True if parsing raised anything but the parsers' own errors."""
    try:
        text = mutation.decode("utf-8")
        json.loads(text) if suffix == ".json" else tomllib.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError):
        return False
    except Exception:  # noqa: BLE001 - any other exception is the finding
        return True
    return False


def fuzz_report(root: Path) -> dict[str, Any]:
    corpus = _corpus(root) or [(".json", b'{"seed": true}')]
    cases = crashes = 0
    for suffix, mutation in _case_stream(corpus):
        if cases >= MAX_CASES:
            break
        crashes += _is_crash(suffix, mutation)
        cases += 1
    return {"version": 1, "kind": "fuzz", "passed": crashes == 0, "cases": cases, "failures": 0, "crashes": crashes}


# --- authenticated negative -----------------------------------------------------------------------------------
def _run_uses_secret(text: str) -> bool:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)(?:-\s*)?run:\s*(.*)$", line)
        if match is None:
            continue
        indent = len(match.group(1))
        body = [match.group(2)]
        for following in lines[index + 1 :]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following)
        if "${{ secrets." in "\n".join(body):
            return True
    return False


def violations(text: str) -> list[str]:
    """The control-plane findings in one workflow document."""
    found: list[str] = []
    if re.search(r"^\s*pull_request_target\s*:", text, re.MULTILINE):
        found.append("privileged pull-request trigger")
    if re.search(r"^permissions:\s*(?:write-all|read-all)\s*$", text, re.MULTILINE):
        found.append("broad token permissions")
    if _run_uses_secret(text):
        found.append("secret expression in shell")
    for reference in ACTION_REF.findall(text):
        if reference.startswith("./"):
            continue
        if reference.startswith("docker://"):
            if PINNED_IMAGE.fullmatch(reference) is None:
                found.append("mutable container action")
        elif OWN_WORKFLOW_REF.fullmatch(reference) is None and PINNED_ACTION.fullmatch(reference) is None:
            found.append("mutable action")
    return found


def negative_report(root: Path) -> dict[str, Any]:
    unauthorized = sum(not violations(case) for case in NEGATIVE_CASES)
    failures = 0
    workflows = root / ".github" / "workflows"
    paths = sorted((*workflows.glob("*.yml"), *workflows.glob("*.yaml"))) if workflows.is_dir() else []
    for path in paths:
        try:
            failures += len(violations(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError):
            failures += 1
    return {
        "version": 1,
        "kind": "authenticated_negative",
        "passed": failures == 0 and unauthorized == 0,
        "cases": len(NEGATIVE_CASES),
        "failures": failures,
        "unauthorized_acceptances": unauthorized,
    }


# --- contract -------------------------------------------------------------------------------------------------
def security_table(pyproject: dict[str, Any]) -> dict[str, Any]:
    """The ``[tool.pipelines.security]`` table; an unknown key is refused, never ignored."""
    table = pyproject.get("tool", {}).get("pipelines", {}).get("security", {})
    unknown = sorted(set(table) - SECURITY_KEYS)
    if unknown:
        raise CannotRun(f"[tool.pipelines.security] has unknown keys: {', '.join(unknown)}")
    return dict(table)


def contract(root: Path) -> dict[str, Any]:
    """The shared default contract with the connector's license additions applied; allow and deny never overlap."""
    result = json.loads(DEFAULT_CONTRACT.read_text(encoding="utf-8"))
    table = security_table(project.load(root))
    policy = result["license_policy"]
    policy["allowed"] = sorted(set(policy["allowed"]) | {str(v) for v in table.get("license_allowed", [])})
    policy["denied"] = sorted(set(policy["denied"]) | {str(v) for v in table.get("license_denied", [])})
    overlap = sorted(set(policy["allowed"]) & set(policy["denied"]))
    if overlap:
        raise CannotRun(f"license policy allows and denies the same identifiers: {', '.join(overlap)}")
    return result


def _write(path: Path, payload: dict[str, Any], *, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=indent) + ("\n" if indent else ""), encoding="utf-8")


def check(root: Path) -> list[str]:
    """Run both checks into a scratch directory and compare each result with the contract's own thresholds."""
    hooks = contract(root)["hooks"]
    reports = {"fuzz": fuzz_report(root), "authenticated_negative": negative_report(root)}
    out: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        for name, report in reports.items():
            _write(Path(scratch) / f"{name}.json", report)
            if not report["passed"]:
                out.append(f"{name} failed: {json.dumps(report, sort_keys=True)}")
            elif report["cases"] < hooks[name]["min_cases"]:
                out.append(f"{name} ran {report['cases']} cases, below the contract minimum {hooks[name]['min_cases']}")
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-security", description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command")
    for name in ("fuzz", "authenticated-negative"):
        sub.add_parser(name).add_argument("out", type=Path)
    sub.add_parser("contract").add_argument("--out", type=Path)
    args, _ = parser.parse_known_args(argv)
    root = repo_root(args.root)
    if args.command in ("fuzz", "authenticated-negative"):
        report = fuzz_report(root) if args.command == "fuzz" else negative_report(root)
        _write(args.out, report)
        return 0 if report["passed"] else 1
    if args.command == "contract":
        text = json.dumps(contract(root), indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0
    found = check(root)
    for line in found:
        print(f"connector-security: {line}")
    if not found:
        print("connector-security: OK: fuzz, authenticated-negative and the license policy hold")
    return 1 if found else 0
