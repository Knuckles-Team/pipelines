"""The fleet clone-scanner contract: thresholds, formats and exclusions.

One reviewed contract for every repository, so a consumer cannot narrow what
the clone gates see. Exclusions cover only machine-produced or deliberately
repeated trees (build output, vendored code, lockfiles, fixtures, samples).
"""

from __future__ import annotations

from pathlib import PurePosixPath

from pipelines_hooks.core.paths import glob_match, normalise_path

DUPEHOUND_THRESHOLD = 0.85
DUPEHOUND_MIN_TOKENS = 40
JSCPD_MIN_TOKENS = 50
JSCPD_MIN_LINES = 5
JSCPD_MODE = "mild"

JSCPD_FORMATS = tuple(
    "asciidoc astro bash bicep c c-header cpp cpp-header css csharp csv cypher dhall "
    "docker graphql go hcl ini java javascript json json5 jsx less makefile markdown "
    "markup mermaid nginx protobuf promql properties pug php python ruby rust sass "
    "scss sql svelte stylus swift toml turtle text txt tsx typescript vue yaml".split()
)
#: Formats jscpd v5 parses but has no default extension mapping for.
JSCPD_FORMAT_EXTENSIONS = (
    ("asciidoc", ("adoc", "asciidoc")),
    ("cypher", ("cypher",)),
    ("dhall", ("dhall",)),
    ("graphql", ("gql",)),
    ("mermaid", ("mermaid", "mmd")),
    ("nginx", ("conf", "nginx")),
    ("promql", ("promql",)),
)
JSCPD_FORMAT_NAMES = (("docker", ("Containerfile", "Dockerfile")), ("makefile", ("GNUmakefile", "Makefile")))
JSCPD_EXTENSIONS = frozenset(
    ".adoc .asciidoc .astro .bash .bicep .c .c++ .cc .cjs .cpp .cs .cts .cxx .css .csv "
    ".cypher .conf .dhall .gql .graphql .go .h .h++ .hh .hpp .hxx .hcl .htm .html .ini "
    ".java .js .json .json5 .jsx .less .md .markdown .mkd .mmd .mermaid .mjs .mts .nginx "
    ".php .proto .promql .properties .pug .py .pyi .rb .rs .sass .scss .sh .sql .svelte "
    ".styl .swift .tf .toml .ttl .ts .tsx .txt .vue .xml .yaml .yml".split()
)
EXCLUSIONS = tuple(
    """**/.git/** **/.venv/** **/.venv-base/** **/venv/** **/node_modules/** **/.cache/**
    **/target/** **/target-isolated/** **/build/** **/build-artifacts/** **/dist/**
    **/dist-primary/** **/dist-reproduction/** **/__pycache__/** **/.mypy_cache/**
    **/.pytest_cache/** **/.pytest_tmp/** **/.ruff_cache/** **/.hypothesis/** **/.tox/**
    **/.eggs/** **/coverage/** **/htmlcov/** **/site-packages/** **/*.egg-info/**
    **/vendor/** **/third_party/** **/fixtures/** **/fixture/** **/samples/** **/sample/**
    **/examples/** **/docs/examples/** **/docs/samples/** **/__snapshots__/** **/*.snap
    **/__generated__/** **/generated/** **/codegen/** **/openapi_client/**
    **/graphql_client/** **/*.generated.* **/*.map **/*.min.css **/*.min.js **/*.lock
    **/Cargo.lock **/package-lock.json **/pnpm-lock.yaml **/yarn.lock **/poetry.lock
    site/**""".split()
)


def is_excluded(path: str) -> bool:
    """Whether a repository-relative path belongs to an excluded tree."""
    value = normalise_path(path)
    return any(glob_match(value, pattern) for pattern in EXCLUSIONS)


def is_jscpd_path(path: str) -> bool:
    """Whether a path is in the reviewed jscpd format universe."""
    candidate = PurePosixPath(normalise_path(path))
    if is_excluded(candidate.as_posix()):
        return False
    names = {name for _, names in JSCPD_FORMAT_NAMES for name in names}
    return candidate.name in names or candidate.suffix.lower() in JSCPD_EXTENSIONS


def format_exts_arg() -> str:
    return ";".join(f"{name}:{','.join(values)}" for name, values in JSCPD_FORMAT_EXTENSIONS)


def format_names_arg() -> str:
    return ";".join(f"{name}:{','.join(values)}" for name, values in JSCPD_FORMAT_NAMES)
