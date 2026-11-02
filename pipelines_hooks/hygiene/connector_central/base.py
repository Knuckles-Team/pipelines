"""Shared context and registry for the central connector migration (PIPE-GATES-R016.50 and following).

A rule is a function ``rule(ctx) -> None`` registered with ``@rule(id)``. It either rewrites files exactly or records a
review item and leaves the files alone; it never guesses. Rules are idempotent: every match requires the pre-migration
shape. ``RULE_ROWS`` maps each rule id to its PIPE-GATES-R016.x spec row (the single source for the spec table).
"""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipelines_hooks.core.distributions import SDK, distribution_for, is_distribution, project_distribution

SDK_FLOOR = "0.5.4"
SDK_PIN = "agent-connector-sdk[mcp]>=0.5.4,<0.6.0"

# (rule id, source document, one-line summary). The row number is R016.<50 + index>.
RULE_TABLE: tuple[tuple[str, str, str], ...] = (
    ("w1.g1", "wave1", "entry point value names `<pkg>:connector`"),
    ("w1.g2", "wave1", "console script becomes `scion_sdk.cli:serve`"),
    ("w1.g3", "wave1", "`mcp_server.py` bootstrap is deleted and its values extracted"),
    ("w1.g4", "wave1", "package `__init__.py` declares `connector = Connector(...)`"),
    ("w1.g5", "wave1", "`__main__.py` calls `run()`"),
    ("w1.g6", "wave1", "the repo's own `/health` route is deleted"),
    ("w1.g7", "wave1", "tests importing deleted bootstrap functions are deleted or reviewed"),
    ("w1.h", "wave1", "scaffold tests and conftest env lines are deleted by fingerprint"),
    ("w1.k1", "wave1", "`__version__` assignments are deleted"),
    ("w1.k2", "wave1", "`.bumpversion.cfg` reduced (then deleted by n)"),
    ("w1.k3", "wave1", "README package-version lines are deleted"),
    ("w1.k4", "wave1", "`__version__` assertions in tests are deleted"),
    ("w1.i1", "wave1", "`connector_sources.declaration()` is deleted and call sites use `load_declaration`"),
    ("w1.i2", "wave1", "identical schema-mapping field dicts become `FIELD_SETS`"),
    ("w1.l1", "wave1", "conventional provider entry-point tables are deleted"),
    ("w1.l2", "wave1", "empty content `__init__.py` markers are deleted"),
    ("w1.l3", "wave1", "the lazy-import scaffold is deleted from `__init__.py`"),
    ("w1.l4", "wave1", "SDK floor, merged extras and dropped one-element extras"),
    ("auth.r1", "auth", "static bearer token declaration"),
    ("auth.r2", "auth", "API key in a fixed header declaration"),
    ("auth.r3", "auth", "API key in a query parameter declaration"),
    ("auth.r4", "auth", "basic user and password declaration"),
    ("auth.r5", "auth", "client credentials declaration"),
    ("auth.r6", "auth", "refresh token declaration"),
    ("auth.r7", "auth", "per-thread delegation holder is deleted"),
    ("auth.r8", "auth", "delegation wrappers are deleted for `delegation=True`"),
    ("auth.r9", "auth", 'resolved TLS profile becomes `tls="<name>"`'),
    ("auth.r10", "auth", "hand-configured requests session is deleted"),
    ("auth.r11", "auth", "cookie login becomes `SessionLogin`"),
    ("auth.r12", "auth", "global client singleton becomes `client_factory`"),
    ("auth.r13", "auth", "local-only tool becomes `NoAuth()`"),
    ("auth.r14", "auth", "plaintext setting becomes `allow_plaintext_env`"),
    ("ingest.i1", "ingest", "duplicated ingest plumbing is deleted"),
    ("ingest.i2", "ingest", "`STREAM = SourceStream...` replaces `_BINDING`"),
    ("ingest.i3", "ingest", "ingest call sites use `STREAM.entities` and `STREAM.documents`"),
    ("ingest.i4", "ingest", "exact dispatch tables become stream mappers"),
    ("ingest.i5", "ingest", "exact mapper bodies become `RecordMap`"),
    ("ingest.i6", "ingest", "local helpers equal to SDK helpers are replaced"),
    ("ingest.i7", "ingest", "checkpointed paging goes to review"),
    ("ingest.i8", "ingest", "best-effort wrapper and split document stream options"),
    ("ingest.i9", "ingest", "media and mixed change sets use `STREAM.media` and `STREAM.batch`"),
    ("pl.n", "pipelines", "version lives in `pyproject.toml` only"),
    ("pl.o", "pipelines", "container files are rendered, not committed"),
    ("pl.p", "pipelines", "ontology artifacts are generated, not committed"),
    ("pl.q", "pipelines", "`.pre-commit-config.yaml` is the shared reference"),
    ("pl.r", "pipelines", "`security_sanitizer.py` and `.codespellignore` are provided"),
    ("pl.s", "pipelines", "workflow flags: skip-hooks, bump2version, render and rebuild callers"),
    ("pl.t", "pipelines", "`.security/*` is provided"),
    ("pl.u", "pipelines", "`scripts/bootstrap.sh` is deleted"),
    ("pl.v", "pipelines", "`verify_api_integration.py` becomes `connector-api-parity`"),
    (
        "id.name",
        "identity",
        "hard-coded connector names in `kg_*.py` and `mappings/*.yaml` derive from or match the SDK identity",
    ),
    ("pl.w", "pipelines", "own pipelines workflow refs are `@main`"),
    ("pl.x", "pipelines", "unreferenced non-scaffold root files are deleted"),
    (
        "pl.y",
        "pipelines",
        "`.github/workflows/org-site.yml` notifies the org site (only when pipelines main provides it)",
    ),
    ("pl.z", "pipelines", "every local spec is indexed in `specs/README.md`"),
    ("pl.aa", "pipelines", "the shared MkDocs theme files match the canonical copy"),
    ("pl.ab", "pipelines", "the `[[project.authors]]` block is the neutral organisation author"),
    ("pl.ac", "pipelines", "example credential URIs in docs code are the placeholder form the privacy gate accepts"),
    ("pl.ad", "pipelines", "the fleet's SHA-pinned `actions/checkout` and `actions/setup-python` replace mutable tags"),
    (
        "pl.ae",
        "pipelines",
        "the publication-workflow test expects the shared hook revision `main`, not the old SHA pin",
    ),
    ("pl.af", "pipelines", "codespell findings are fixed or classified"),
)
FIRST_ROW = 50
RULE_ROWS: dict[str, str] = {rid: f"PIPE-GATES-R016.{FIRST_ROW + i}" for i, (rid, _s, _t) in enumerate(RULE_TABLE)}


class Review:
    """Review items; a ``blocking`` item stops the repo in the batch driver."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, step: str, detail: str, path: str = "", blocking: bool = True) -> None:
        self.items.append({"step": step, "path": path, "detail": detail, "blocking": blocking})


@dataclass
class Ctx:
    """One repo under migration. All paths in ``changed``/``deleted`` are repo-relative posix strings."""

    root: Path
    pkg: Path
    fleet: str  # entry-point name, e.g. "plane-mcp"
    dist: str  # [project].name
    review: Review = field(default_factory=Review)
    changed: set[str] = field(default_factory=set)
    deleted: set[str] = field(default_factory=set)
    options: dict[str, Any] = field(default_factory=dict)  # sdk_path, pipelines_root, offline, ...
    applied: list[str] = field(default_factory=list)  # rule ids that changed something

    @property
    def pkg_name(self) -> str:
        return self.pkg.name

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")

    def exists(self, rel: str) -> bool:
        return (self.root / rel).exists()

    def write(self, rel: str, text: str, rule_id: str = "") -> bool:
        """Write ``text``; returns True when the content changed."""
        path = self.root / rel
        old = path.read_text(encoding="utf-8") if path.is_file() else None
        if old == text:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.changed.add(rel)
        self.deleted.discard(rel)
        if rule_id and rule_id not in self.applied:
            self.applied.append(rule_id)
        return True

    def delete(self, rel: str, rule_id: str = "") -> bool:
        path = self.root / rel
        if not (path.is_file() or path.is_symlink()):
            return False
        path.unlink()
        self.deleted.add(rel)
        self.changed.discard(rel)
        if rule_id and rule_id not in self.applied:
            self.applied.append(rule_id)
        return True

    def pyproject(self) -> dict[str, Any]:
        return tomllib.loads(self.read("pyproject.toml"))

    @property
    def sdk_distribution(self) -> str:
        """The SDK spelling this migration should retain or explicitly emit.

        A migration may set ``options["sdk_distribution"]`` to the new name
        after that distribution is published.  Until then, an existing
        project keeps the spelling already present in its requirements.
        """
        requested = self.options.get("sdk_distribution")
        project = self.pyproject().get("project", {})
        if requested:
            if not is_distribution(str(requested), SDK):
                raise ValueError(f"unsupported SDK distribution: {requested}")
            return distribution_for([str(requested)], SDK)
        return project_distribution(project, SDK)

    def note(self, rule_id: str, detail: str, path: str = "", blocking: bool = False) -> None:
        self.review.add(rule_id, detail, path, blocking)

    def git_tracked(self, pattern: str) -> list[str]:
        base = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        r = subprocess.run(
            ["git", "ls-files", "-z", "--", pattern], cwd=self.root, capture_output=True, text=True, env=base
        )
        return [p for p in r.stdout.split("\0") if p]


RuleFn = Callable[[Ctx], None]
RULES: dict[str, RuleFn] = {}


def rule(rule_id: str) -> Callable[[RuleFn], RuleFn]:
    """Register ``fn`` under ``rule_id`` (must be in ``RULE_TABLE``)."""
    if rule_id not in RULE_ROWS:
        raise KeyError(rule_id)

    def deco(fn: RuleFn) -> RuleFn:
        RULES[rule_id] = fn
        return fn

    return deco


def spec_row(rule_id: str) -> str:
    return RULE_ROWS[rule_id]


def make_ctx(root: Path, options: dict[str, Any] | None = None) -> Ctx | None:
    """Resolve fleet name, package dir and distribution from ``pyproject.toml``; None when no connector entry point."""
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    eps = data.get("project", {}).get("entry-points", {}).get("scion_sdk.connector", {})
    if len(eps) != 1:
        return None
    ((fleet, value),) = eps.items()
    pkg = root / re.split(r"[:.]", str(value))[0]
    if not pkg.is_dir():
        return None
    return Ctx(root=root, pkg=pkg, fleet=fleet, dist=data["project"]["name"], options=dict(options or {}))
