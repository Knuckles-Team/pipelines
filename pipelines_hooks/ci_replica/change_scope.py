"""change-scope: classify a pull request's diff once, so CI runs only the gates it touches.

Every changed path (added, modified, renamed or deleted) falls in exactly one
class, first match wins:

- ``spec``: ``specs/**`` and ``.specify/**`` (every spec-kit artifact).
- ``ci``: ``.github/**``, ``.config/pre-commit*``, ``.pre-commit-config.yaml``.
- ``deps``: lockfiles, ``pyproject.toml``, ``Cargo.toml``/``Cargo.lock``, ``package.json``.
- ``docs``: ``docs/**``, ``plans/**``, ``**/*.md``, ``LICENSE``, ``mkdocs.yml``.
- ``python``: ``*.py``/``*.pyi``; ``rust``: ``*.rs``; ``frontend``: web sources.
- ``other``: anything else; it counts as code.

The scope is ``spec`` when only spec and docs paths changed, ``full`` when a
``ci`` or ``deps`` path changed (or ``--force-full``, or an empty diff), else
``code``. For ``spec`` it also emits ``skip-hooks``: every hook id of the given
pre-commit configs that is not a spec or text gate (:data:`SPEC_GATES`).

Output: ``key=value`` lines on stdout, appended to ``$GITHUB_OUTPUT`` when set.
An unreadable diff or config is :class:`CannotRun` (exit 2).
"""

from __future__ import annotations

import argparse
import fnmatch
from pathlib import Path

import yaml

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, nul_split, repo_root
from pipelines_hooks.core.settings import setting

CLASSES = ("spec", "docs", "python", "rust", "frontend", "ci", "deps", "other")
CODE_CLASSES = frozenset({"python", "rust", "frontend", "ci", "deps", "other"})
FULL_CLASSES = frozenset({"ci", "deps"})

_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("spec", ("specs/*", ".specify/*")),
    ("ci", (".github/*", ".config/pre-commit*", ".pre-commit-config.yaml", ".pre-commit-hooks.yaml")),
    (
        "deps",
        (
            "uv.lock", "*/uv.lock", "pyproject.toml", "*/pyproject.toml", "Cargo.toml", "*/Cargo.toml",
            "Cargo.lock", "*/Cargo.lock", "package.json", "*/package.json", "package-lock.json",
            "*/package-lock.json", "pnpm-lock.yaml", "*/pnpm-lock.yaml", "yarn.lock", "*/yarn.lock",
            "requirements*.txt", "*/requirements*.txt", "rust-toolchain*",
        ),
    ),
    ("docs", ("docs/*", "plans/*", "*.md", "LICENSE", "LICENSE.*", "mkdocs.yml")),
    ("python", ("*.py", "*.pyi")),
    ("rust", ("*.rs",)),
    ("frontend", ("*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.cjs", "*.css", "*.scss", "*.vue", "*.svelte", "*.html")),
)  # fmt: skip

#: The gates a spec or docs only change runs (reference/ci-standard.md, gate-to-class table).
SPEC_GATES = frozenset(
    {
        "spec", "spec-standard", "spec-decomposition", "spec-status", "spec-trailers", "spec-analyze",
        "spec-checklists", "spec-contracts", "constitution", "ste-staged", "ste-staleness-staged",
        "public-surface", "tracked-privacy", "no-legacy-concepts", "mermaid", "trailing-whitespace",
        "end-of-file-fixer", "mixed-line-ending", "check-merge-conflict", "check-added-large-files",
        "check-yaml", "check-json", "markdownlint", "link-check", "lychee",
    }
)  # fmt: skip


def classify(path: str) -> str:
    """The one class of a repository-relative path; ``other`` when no rule matches."""
    for name, patterns in _RULES:
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns):
            return name
    return "other"


def hook_ids(configs: list[Path]) -> list[str]:
    """Every hook id of the existing pre-commit configs, in file order, deduplicated."""
    ids: list[str] = []
    for config in configs:
        if not config.is_file():
            continue
        try:
            document = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise CannotRun(f"{config} is not valid YAML: {exc}") from exc
        for repo in document.get("repos", []) or []:
            for hook in repo.get("hooks", []) or []:
                hook_id = str(hook.get("id", ""))
                if hook_id and hook_id not in ids:
                    ids.append(hook_id)
    return ids


def scope_for(paths: list[str], *, force_full: bool = False) -> dict[str, str]:
    """The step outputs for one diff (without ``skip-hooks``)."""
    present = {classify(path) for path in paths}
    outputs = {name: str(name in present).lower() for name in CLASSES}
    outputs["code"] = str(bool(present & CODE_CLASSES)).lower()
    if force_full or not paths or present & FULL_CLASSES:
        outputs["scope"] = "full"
    elif present & CODE_CLASSES:
        outputs["scope"] = "code"
    else:
        outputs["scope"] = "spec"
    return outputs


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="change-scope", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref", "--diff", dest="base_ref", default="")
    parser.add_argument("--config", action="append", default=[], help="pre-commit config whose hooks may be skipped")
    parser.add_argument("--spec-hooks", default="", help="extra comma-separated hook ids that count as spec gates")
    parser.add_argument("--force-full", action="store_true", help="main push, nightly or all-files run")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    root = repo_root(args.root)
    paths: list[str] = []
    if not args.force_full:
        base_ref = args.base_ref
        if not base_ref:
            raise CannotRun("change-scope needs --base-ref for a pull request diff")
        paths = sorted(set(nul_split(git_text(root, ("diff", "--name-only", "-z", f"{base_ref}...HEAD")))))
    outputs = scope_for(paths, force_full=args.force_full)
    allowed = SPEC_GATES | {item.strip() for item in args.spec_hooks.split(",") if item.strip()}
    skip: list[str] = []
    if outputs["scope"] == "spec":
        skip = [hook for hook in hook_ids([root / config for config in args.config]) if hook not in allowed]
    outputs["skip-hooks"] = ",".join(skip)
    counts = {name: sum(1 for path in paths if classify(path) == name) for name in CLASSES}
    print(f"change-scope: {len(paths)} paths " + " ".join(f"{k}={v}" for k, v in counts.items() if v))
    if outputs["scope"] == "spec":
        print("change-scope: spec/docs-only change; build, tests, scanners and journeys are not applicable")
    lines = [f"{key}={value}" for key, value in outputs.items()]
    print("\n".join(lines))
    target = setting("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return 0
