"""sdk-conformance: a connector uses the SDK capability instead of its own copy.

The connector SDK centralizes the capabilities a connector needs. Its index is
the SDK spec ``SDK-CENTRALIZED-CAPABILITIES``; each row says that connectors use
one SDK capability and ship no copy. This gate flags the copies that a static
scan can see. Every finding cites the row it breaks:

* ``R001`` governed HTTP client and retry: a direct ``requests`` import, a
  hand-built ``httpx`` client or call, or an own retry loop;
* ``R008`` TLS profiles: TLS verification turned off, the insecure-request
  warning silenced, or a hand-built SSL context;
* ``R009`` credential and secret-reference resolution: hand-parsed ``env://``
  or ``openbao://`` references;
* ``R016`` GraphQL: an own client built on the GraphQL protocol library's
  ``Client`` or transports;
* ``R040`` optional dependencies come from SDK extras: a direct requirement on
  a package that an SDK extra carries.

The scan covers non-test Python and ``pyproject.toml``. It applies to a
repository that depends on ``agent-connector-sdk``; the SDK itself is exempt.
A hit is evidence for review. A miss is not proof of conformance.

The direct ``gql``/``graphql-core`` declaration belongs to ``connector-graphql``
(PIPE-GATES-R012), and this gate does not repeat it.

Findings warn by default, so the fleet migrates repository by repository;
``--strict`` makes them failures. A repository turns strict on in its own
pre-commit configuration once it is migrated.
"""

from __future__ import annotations

import argparse
import re
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

SDK = "agent-connector-sdk"
ROW = "SDK-CENTRALIZED-CAPABILITIES-"
_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    ".pipeline-theme",
    "tests",
    "test",
    "scripts",
    "examples",
    "docs",
}
_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?")

# The packages each SDK extra carries, by normalized name. The table mirrors
# ``[project.optional-dependencies]`` of agent-connector-sdk at its latest
# release. Update it in the same change that adds an SDK extra.
SDK_EXTRAS: dict[str, str] = {
    "rdflib": "integrity",
    "fastmcp": "mcp",
    "mcp": "mcp",
    "fasta2a": "a2a",
    "starlette": "a2a",
    "feedparser": "feeds",
    "pyarrow": "dataprep",
    "psycopg": "db",
    "pymysql": "db",
    "pymongo": "db",
    "oracledb": "db",
    "pyodbc": "mssql",
    "pandas": "market",
    "yfinance": "market",
    "websockets": "stream",
}
# Owned by connector-graphql (PIPE-GATES-R012).
_NOT_HERE = frozenset({"gql", "graphql-core"})


@dataclass(frozen=True)
class Rule:
    row: str
    pattern: re.Pattern[str]
    message: str


RULES: tuple[Rule, ...] = (
    Rule(
        "R001",
        re.compile(r"^\s*(?:import\s+requests\b|from\s+requests(?:\.\w+)*\s+import\b)"),
        "imports requests directly; use agent_connector_sdk.http.create_http_client",
    ),
    Rule(
        "R001",
        re.compile(
            r"\bhttpx\.(?:Client|AsyncClient)\s*\(|\bhttpx\.(?:get|post|put|patch|delete|head|options|request|stream)\s*\("
        ),
        "builds an httpx client or calls httpx directly; use agent_connector_sdk.http.create_http_client",
    ),
    Rule(
        "R001",
        re.compile(
            r"\bfor\s+(?:_?attempt|_?retry|_?retries|_?tries|_?try)\w*\s+in\s+range\s*\("
            r"|\bdef\s+_?validate_max_retries\b"
            r"|[\"']Retry-After[\"']\s*\](?!\s*=[^=])|\.get\(\s*[\"']Retry-After[\"']"
            r"|^\s*(?:import\s+(?:tenacity|backoff)\b|from\s+(?:tenacity|backoff)\b)"
            r"|\bfrom\s+urllib3\.util(?:\.retry)?\s+import\s+.*\bRetry\b"
        ),
        "own retry or backoff loop; use agent_connector_sdk.http.RetryPolicy",
    ),
    Rule(
        "R008",
        re.compile(r"\bverify\s*=\s*False\b|\bcheck_hostname\s*=\s*False\b|\bCERT_NONE\b"),
        "turns TLS verification off; use agent_connector_sdk.tls.resolve_tls_profile",
    ),
    Rule(
        "R008",
        re.compile(r"\bdisable_warnings\s*\(|\bInsecureRequestWarning\b"),
        "silences the insecure-request warning; use agent_connector_sdk.tls.resolve_tls_profile",
    ),
    Rule(
        "R008",
        re.compile(r"\bssl\.(?:create_default_context|SSLContext|_create_unverified_context)\s*\("),
        "builds its own SSL context; use agent_connector_sdk.tls.resolve_tls_profile",
    ),
    Rule(
        "R009",
        re.compile(
            r"\b(?:startswith|removeprefix|partition|split|match|fullmatch)\s*\(\s*\(?\s*r?[\"'](?:env|openbao)://"
            r"|=\s*r?[\"'](?:env|openbao)://[\"']"
            r"|re\.compile\s*\(\s*r?[\"'][^\"']*(?:env|openbao)://"
        ),
        "parses an env:// or openbao:// reference itself; use agent_connector_sdk.credentials",
    ),
    Rule(
        "R016",
        re.compile(r"^\s*(?:from\s+gql\.transport(?:\.\w+)*\s+import\b|from\s+gql\s+import\s+.*\bClient\b)"),
        "builds its own GraphQL client; use agent_connector_sdk.transports.graphql",
    ),
)


@dataclass(frozen=True)
class Finding:
    row: str
    location: str
    message: str

    def render(self) -> str:
        return f"{ROW}{self.row}: {self.location}: {self.message}"


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse(requirement: str) -> tuple[str, frozenset[str]]:
    match = _REQUIREMENT.match(requirement)
    if not match:
        return "", frozenset()
    extras = frozenset(_normalize(extra.strip()) for extra in (match.group(2) or "").split(",") if extra.strip())
    return _normalize(match.group(1)), extras


def _python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).parts
        if _SKIP_DIRS.intersection(relative[:-1]) or relative[-1].startswith("test_") or relative[-1] == "conftest.py":
            continue
        yield path


def _project(root: Path) -> dict | None:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        return tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
    except tomllib.TOMLDecodeError:
        return None


def applies(project: dict) -> bool:
    """A repository that depends on the SDK, other than the SDK itself."""
    if _normalize(str(project.get("name", ""))) == SDK:
        return False
    sections = [project.get("dependencies", []), *project.get("optional-dependencies", {}).values()]
    return any(_parse(str(item))[0] == SDK for items in sections for item in items)


def source_findings(root: Path) -> list[Finding]:
    found: list[Finding] = []
    for path in _python_files(root):
        relative = path.relative_to(root)
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            for rule in RULES:
                if rule.pattern.search(line):
                    found.append(Finding(rule.row, f"{relative}:{number}", rule.message))
    return found


def dependency_findings(project: dict, extras: dict[str, str]) -> list[Finding]:
    """One finding per package that a section declares and an SDK extra carries."""
    sections = {"dependencies": project.get("dependencies", [])}
    sections.update(
        {f"optional-dependencies.{key}": value for key, value in project.get("optional-dependencies", {}).items()}
    )
    declared: dict[str, tuple[str, list[str]]] = {}
    for section, items in sections.items():
        for item in items:
            name, _ = _parse(str(item))
            if name in extras and name not in _NOT_HERE:
                declared.setdefault(name, (str(item), []))[1].append(section)
    return [
        Finding(
            "R040",
            "pyproject.toml " + ", ".join(f"[project.{section}]" for section in where),
            f"declares {item!r} directly; depend on {SDK}[{extras[name]}]",
        )
        for name, (item, where) in declared.items()
    ]


def findings(root: Path, extras: dict[str, str] | None = None) -> list[Finding]:
    """Every conformance finding for the repository at ``root``."""
    project = _project(root)
    if project is None or not applies(project):
        return []
    return source_findings(root) + dependency_findings(project, SDK_EXTRAS if extras is None else extras)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sdk-conformance", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--strict", action="store_true", help="fail instead of warn")
    arguments = parser.parse_args(argv)
    problems = findings(arguments.root)
    level = "FAIL" if arguments.strict else "WARN"
    for problem in problems:
        print(f"sdk-conformance: {level}: {problem.render()}")
    if problems:
        print(f"sdk-conformance: {len(problems)} finding(s)")
    return 1 if problems and arguments.strict else 0
