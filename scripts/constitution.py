"""Render the generated sections of the organization constitution from real configs.

The constitution holds two kinds of generated region. Each region sits between
``<!-- generated:begin constitution KIND[: ARGS] -->`` and ``<!-- generated:end -->``.

* ``thresholds`` renders the limits table from the gate configuration files and
  the gate source constants, so a number is never typed by hand.
* ``hooks: id, id`` renders one line per gate hook from ``.pre-commit-hooks.yaml``.
  A hook id that the catalogue does not publish is an error.

``--check`` exits 1 when the file differs from the rendered text and writes nothing.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines_hooks.ci_replica.fast_tests import DEFAULT_TIMEOUT_SECONDS
from pipelines_hooks.clones import contract
from pipelines_hooks.complexity import MAX_COGNITIVE, MAX_CYCLOMATIC
from pipelines_hooks.ste import scan

DEFAULT_FILE = Path(".specify/memory/constitution.md")
REGION = re.compile(
    r"(?P<begin><!-- generated:begin constitution (?P<kind>\w+)(?:: (?P<args>[^>]*?))? -->\n)"
    r"(?P<body>.*?)(?P<end><!-- generated:end -->)",
    re.DOTALL,
)
KISS_LIMITS = (
    ("statements_per_function", "Statements per function"),
    ("local_variables", "Local variables per function"),
    ("calls_per_function", "Calls per function"),
    ("positional_args", "Positional arguments"),
    ("max_indentation", "Indentation depth"),
    ("nested_function_depth", "Nested function depth"),
    ("returns_per_function", "Returns per function"),
    ("boolean_parameters", "Boolean parameters"),
    ("statements_per_try_block", "Statements per try block"),
    ("methods_per_class", "Methods per class"),
    ("imported_names_per_file", "Imported names per file"),
    ("statements_per_file", "Statements per file"),
    ("lines_per_file", "Lines per file"),
    ("functions_per_file", "Functions per file"),
    ("interface_types_per_file", "Interface types per file"),
)


def _toml(root: Path, rel: str) -> dict:
    return tomllib.loads((root / rel).read_text(encoding="utf-8"))


def _catalogue(root: Path) -> dict[str, dict]:
    hooks = yaml.safe_load((root / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    return {hook["id"]: hook for hook in hooks}


def _job_minutes(root: Path, rel: str, job: str, key: str | None = None) -> int:
    """A job's ``timeout-minutes``, or the same key under its ``with:`` inputs."""
    spec = yaml.safe_load((root / rel).read_text(encoding="utf-8"))["jobs"][job]
    value = spec["with"].get("timeout-minutes") if key else spec.get("timeout-minutes")
    if value is None:
        raise SystemExit(f"constitution: no timeout-minutes for job {job} in {rel}")
    return int(value)


def _requires_python(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    return _toml_value(text, "requires-python")


def _toml_value(text: str, key: str) -> str:
    match = re.search(rf'^{re.escape(key)}\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match is None:
        raise SystemExit(f"constitution: no {key} in pyproject.toml")
    return match.group(1)


def threshold_rows(root: Path) -> list[tuple[str, str, str]]:
    """Rows of ``(limit, value, source)`` read from the real configuration."""
    gates = _toml(root, "pipelines_hooks/gate_sets.toml")
    kiss = _toml(root, ".config/kiss.toml")["python"]
    rows = [
        ("Blocking checks per repository", str(len(gates["blocking"])), "`pipelines_hooks/gate_sets.toml`"),
        ("Pre-land fast set", ", ".join(f"`{g}`" for g in gates["fast"]), "`pipelines_hooks/gate_sets.toml`"),
        ("Post-land full set", ", ".join(f"`{g}`" for g in gates["full"]), "`pipelines_hooks/gate_sets.toml`"),
        ("Affected-tests cap at push", f"{DEFAULT_TIMEOUT_SECONDS} s", "`pipelines_hooks/ci_replica/fast_tests.py`"),
        (
            "Repository validation budget",
            f"{_toml(root, '.config/validation.toml')['budget_seconds']} s",
            "`.config/validation.toml`",
        ),
        (
            "Pull request gate job",
            f"{_job_minutes(root, '.github/workflows/connector_pr_pipeline.yml', 'gates', 'with')} min",
            "`.github/workflows/connector_pr_pipeline.yml`",
        ),
        (
            "Required-check aggregate job",
            f"{_job_minutes(root, 'templates/workflows/ci.yml', 'ci-required')} min",
            "`templates/workflows/ci.yml`",
        ),
        ("Python requirement", f"`{_requires_python(root)}`", "`pyproject.toml`"),
        (
            "Python environment",
            f"`{(root / '.python-version').read_text(encoding='utf-8').strip()}`",
            "`.python-version`",
        ),
        ("Cyclomatic complexity per function", f"{MAX_CYCLOMATIC}", "`pipelines_hooks/complexity/__init__.py`"),
        ("Cognitive complexity per function", f"{MAX_COGNITIVE}", "`pipelines_hooks/complexity/__init__.py`"),
        ("Words per sentence", f"{scan._SENTENCE_CAP}", "`pipelines_hooks/ste/scan.py`"),
        (
            "Clone similarity (dupehound, blocking)",
            f"{contract.DUPEHOUND_THRESHOLD}",
            "`pipelines_hooks/clones/contract.py`",
        ),
        (
            "Clone similarity (dupehound, diagnostic)",
            f"{contract.DUPEHOUND_DIAGNOSTIC_THRESHOLD}",
            "`pipelines_hooks/clones/contract.py`",
        ),
        (
            "Clone minimum size (dupehound)",
            f"{contract.DUPEHOUND_MIN_TOKENS} tokens",
            "`pipelines_hooks/clones/contract.py`",
        ),
        (
            "Clone minimum size (jscpd)",
            f"{contract.JSCPD_MIN_TOKENS} tokens, {contract.JSCPD_MIN_LINES} lines",
            "`pipelines_hooks/clones/contract.py`",
        ),
        (
            "Clone similarity (KISS)",
            f"{_toml(root, '.config/kiss.toml')['global']['min_similarity']}",
            "`.config/kiss.toml`",
        ),
    ]
    rows += [(label, str(kiss[key]), "`.config/kiss.toml`") for key, label in KISS_LIMITS]
    return rows


def render_thresholds(root: Path) -> str:
    lines = ["| Limit | Value | Source |", "|---|---|---|"]
    lines += [f"| {limit} | {value} | {source} |" for limit, value, source in threshold_rows(root)]
    return "\n".join(lines) + "\n"


def _description(hook: dict) -> str:
    name = hook["name"]
    return re.sub(r"^DEPRECATED \([^)]*\):\s*", "", name)


def render_hooks(root: Path, ids: list[str]) -> str:
    catalogue = _catalogue(root)
    missing = [i for i in ids if i not in catalogue]
    if missing:
        raise SystemExit(f"constitution: hook id not in .pre-commit-hooks.yaml: {', '.join(missing)}")
    return "".join(f"- `{i}`: {_description(catalogue[i])}\n" for i in ids)


def render_region(root: Path, kind: str, args: str | None) -> str:
    if kind == "thresholds":
        return render_thresholds(root)
    if kind == "hooks":
        return render_hooks(root, [part.strip() for part in (args or "").split(",") if part.strip()])
    raise SystemExit(f"constitution: unknown generated region kind {kind!r}")


def render(root: Path, text: str) -> str:
    """The file text with every generated region rewritten from the configs."""

    def replace(match: re.Match[str]) -> str:
        body = render_region(root, match["kind"], match["args"])
        return match["begin"] + body + match["end"]

    return REGION.sub(replace, text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when the file is out of date")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE, help="constitution path under the root")
    args = parser.parse_args(argv)
    path = args.root / args.file
    current = path.read_text(encoding="utf-8")
    rendered = render(args.root, current)
    if rendered == current:
        return 0
    if args.check:
        print(f"constitution: {args.file} is out of date; run python scripts/constitution.py", file=sys.stderr)
        return 1
    path.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
