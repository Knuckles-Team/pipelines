"""stack-profile: resolve a repository's stack profiles, hooks and workflows.

``reference/stack-profiles.yml`` is the one table (PIPE-GATES-R022). This
command detects the profiles a repository matches (marker files, dependency
names, build backend, entry-point groups), composes them (``base`` always,
then ``requires``) and prints the union as JSON:

- ``profiles`` and the ``evidence`` that selected each one;
- ``hooks`` by stage (``pre-commit``, ``pre-push``, ``ci-gates``) and the
  repository each id comes from;
- ``workflows`` (reusable workflow, event, inputs), the ``caller`` file and
  the pre-commit ``config`` paths;
- ``change_scope``: the change-scope classes the profiles touch.

``--profile NAME`` (repeatable) adds profiles for a project that has no files
yet. ``--check`` compares the repository's pre-commit configs and workflow
callers with the resolved set: it lists ``missing``, ``misplaced`` (wrong
stage) and ``extra`` hooks and ``missing_workflows``, and exits 1 when a
required hook or workflow is missing or misplaced. Extra hooks are reported,
never fatal. ``--emit pre-commit|ci-gates`` prints the config file a scaffold
writes instead of JSON. An unreadable table or config is :class:`CannotRun`.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from pipelines_hooks.core.errors import CannotRun

STAGES = ("pre-commit", "pre-push", "ci-gates")
_SKIP_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "target", "dist", "build", ".tox", "site"})
_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?")


def _default_table() -> Path:
    try:
        packaged = resources.files("pipelines_hooks.stack_reference").joinpath("stack-profiles.yml")
        if packaged.is_file():
            return Path(str(packaged))
    except ModuleNotFoundError:
        pass
    return Path(__file__).resolve().parents[2] / "reference" / "stack-profiles.yml"


def load_table(path: Path | None = None) -> dict[str, Any]:
    """The parsed profile table; ``CannotRun`` when it is missing or malformed."""
    table_path = path or _default_table()
    try:
        table = yaml.safe_load(table_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CannotRun(f"cannot read the stack profile table {table_path}: {exc}") from exc
    if not isinstance(table, dict) or not isinstance(table.get("profiles"), dict):
        raise CannotRun(f"{table_path} has no profiles mapping")
    return table


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement(spec: str) -> tuple[str, set[str]]:
    match = _NAME.match(spec)
    if not match:
        return "", set()
    extras = {_normalize(e) for e in (match.group(2) or "[]")[1:-1].split(",") if e.strip()}
    return _normalize(match.group(1)), extras


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"{path} is not valid TOML: {exc}") from exc


class Facts:
    """What detection reads from one repository root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.files = self._files(root)
        pyproject = _read_toml(root / "pyproject.toml")
        project = pyproject.get("project", {}) or {}
        self.project_name = _normalize(str(project.get("name", "")))
        self.build_backend = str((pyproject.get("build-system", {}) or {}).get("build-backend", ""))
        self.tool_tables = {f"tool.{name}" for name in (pyproject.get("tool", {}) or {})}
        self.entry_point_groups = set((project.get("entry-points", {}) or {}).keys())
        specs = list(project.get("dependencies", []) or [])
        for group in (project.get("optional-dependencies", {}) or {}).values():
            specs.extend(group or [])
        self.python_deps: dict[str, set[str]] = {}
        for spec in specs:
            name, extras = _requirement(str(spec))
            if name:
                self.python_deps.setdefault(name, set()).update(extras)
        self.cargo_deps: set[str] = set()
        for cargo in (p for p in self.files if p.rsplit("/", 1)[-1] == "Cargo.toml"):
            document = _read_toml(root / cargo)
            for table in ("dependencies", "dev-dependencies", "build-dependencies"):
                self.cargo_deps.update(_normalize(k) for k in (document.get(table, {}) or {}))
            workspace = document.get("workspace", {}) or {}
            self.cargo_deps.update(_normalize(k) for k in (workspace.get("dependencies", {}) or {}))
        self.npm_deps: set[str] = set()
        for package in (p for p in self.files if p.rsplit("/", 1)[-1] == "package.json"):
            try:
                document = json.loads((root / package).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CannotRun(f"{package} is not valid JSON: {exc}") from exc
            for table in ("dependencies", "devDependencies", "peerDependencies"):
                self.npm_deps.update((document.get(table, {}) or {}).keys())

    @staticmethod
    def _files(root: Path) -> list[str]:
        found: list[str] = []
        if not root.is_dir():
            return found
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            if any(part in _SKIP_DIRS for part in relative.parts[:-1]) or not path.is_file():
                continue
            found.append(relative.as_posix())
        return sorted(found)

    def python_dep(self, wanted: str) -> bool:
        name, extras = _requirement(wanted)
        return name in self.python_deps and extras <= self.python_deps[name]


def _evidence(detect: dict[str, Any], facts: Facts) -> list[str]:
    reasons: list[str] = []
    if detect.get("always"):
        reasons.append("always")
    for pattern in detect.get("files_any", []) or []:
        if any(fnmatch.fnmatchcase(path, pattern) for path in facts.files):
            reasons.append(f"file {pattern}")
    reasons += [f"python dependency {d}" for d in detect.get("python_deps_any", []) or [] if facts.python_dep(d)]
    reasons += [f"crate {d}" for d in detect.get("cargo_deps_any", []) or [] if _normalize(d) in facts.cargo_deps]
    reasons += [f"npm package {d}" for d in detect.get("npm_deps_any", []) or [] if d in facts.npm_deps]
    reasons += [f"build backend {b}" for b in detect.get("build_backends_any", []) or [] if facts.build_backend == b]
    reasons += [f"pyproject {t}" for t in detect.get("pyproject_tables_any", []) or [] if t in facts.tool_tables]
    groups = detect.get("entry_point_groups_any", []) or []
    reasons += [f"entry points {g}" for g in groups if g in facts.entry_point_groups]
    return reasons


def detect(table: dict[str, Any], facts: Facts, forced: list[str]) -> dict[str, list[str]]:
    """Profile name -> evidence, in table order, closed over ``requires``."""
    profiles: dict[str, dict[str, Any]] = table["profiles"]
    unknown = [name for name in forced if name not in profiles]
    if unknown:
        raise CannotRun(f"unknown profile(s): {', '.join(unknown)}; known: {', '.join(profiles)}")
    selected: dict[str, list[str]] = {}
    for name, profile in profiles.items():
        excluded = facts.project_name in {_normalize(n) for n in profile.get("not_project_names", []) or []}
        reasons = [] if excluded else _evidence(profile.get("detect", {}) or {}, facts)
        if name in forced:
            reasons.append("requested")
        if reasons:
            selected[name] = reasons
    pending = list(selected)
    while pending:
        parent = pending.pop()
        for required in profiles[parent].get("requires", []) or []:
            if required not in selected:
                selected[required] = []
                pending.append(required)
            selected[required].append(f"required by {parent}")
    return {name: selected[name] for name in profiles if name in selected}


def _source(table: dict[str, Any], hook_id: str) -> dict[str, str]:
    for name, entry in (table.get("hook_repos", {}) or {}).items():
        if hook_id in (entry.get("ids", []) or []):
            return {"source": name, "repo": entry["repo"], "rev": str(entry.get("rev", ""))}
    pipelines = table["hook_repos"]["pipelines"]
    return {"source": "pipelines", "repo": pipelines["repo"], "rev": str(pipelines["rev"])}


def resolve(table: dict[str, Any], selected: dict[str, list[str]]) -> dict[str, Any]:
    """The union of the selected profiles' hooks, workflows, caller and scope."""
    profiles = table["profiles"]
    chosen = [profiles[name] for name in selected]
    caller = max((p["caller"] for p in chosen if p.get("caller")), key=lambda c: c.get("priority", 0))
    ci_stage = next((p["ci_gates_stage"] for p in chosen if p.get("ci_gates_stage")), "ci-gates")
    hooks: dict[str, list[str]] = {stage: [] for stage in STAGES}
    for profile in chosen:
        for stage in STAGES:
            for hook_id in profile.get(stage, []) or []:
                target = ci_stage if stage == "ci-gates" else stage
                if not any(hook_id in ids for ids in hooks.values()):
                    hooks[target].append(hook_id)
    wrapped = {w for p in chosen for w in p.get("wraps", []) or []}
    workflows: list[dict[str, Any]] = []
    for profile in chosen:
        for workflow in profile.get("workflows", []) or []:
            if workflow["name"] in wrapped:
                continue
            existing = next((w for w in workflows if w["name"] == workflow["name"]), None)
            if existing:
                existing.setdefault("inputs", {}).update(workflow.get("inputs", {}) or {})
            else:
                workflows.append({"inputs": {}, **workflow})
    scope: list[str] = []
    for profile in chosen:
        scope += [c for c in profile.get("change_scope", []) or [] if c not in scope]
    all_ids = [hook_id for ids in hooks.values() for hook_id in ids]
    return {
        "hooks": hooks,
        "hook_sources": {hook_id: _source(table, hook_id) for hook_id in all_ids},
        "workflows": workflows,
        "caller": caller,
        "change_scope": scope,
    }


def _config_hooks(path: Path) -> dict[str, str]:
    """Hook id -> stage of one pre-commit config (``pre-commit`` when unset)."""
    if not path.is_file():
        return {}
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise CannotRun(f"{path} is not valid YAML: {exc}") from exc
    default = (document.get("default_stages") or ["pre-commit"])[0]
    found: dict[str, str] = {}
    for repo in document.get("repos", []) or []:
        for hook in repo.get("hooks", []) or []:
            stages = hook.get("stages") or [default]
            found.setdefault(str(hook.get("id", "")), "pre-push" if "pre-push" in stages else str(stages[0]))
    return found


def check(root: Path, resolved: dict[str, Any]) -> dict[str, Any]:
    """Missing, misplaced and extra hooks and missing workflows of one repository."""
    caller = resolved["caller"]
    config = root / caller["config"]
    if not config.is_file() and (root / ".pre-commit-config.yaml").is_file():
        config = root / ".pre-commit-config.yaml"
    local = _config_hooks(config)
    ci_path = root / caller["ci_config"]
    ci_hooks = {} if ci_path == config else _config_hooks(ci_path)
    missing: list[dict[str, str]] = []
    misplaced: list[dict[str, str]] = []
    for stage in ("pre-commit", "pre-push"):
        for hook_id in resolved["hooks"][stage]:
            if hook_id not in local:
                missing.append({"id": hook_id, "stage": stage})
            elif local[hook_id] != stage:
                misplaced.append({"id": hook_id, "stage": local[hook_id], "expected": stage})
    suggested_ci = [h for h in resolved["hooks"]["ci-gates"] if h not in ci_hooks and h not in local]
    known = {hook_id for ids in resolved["hooks"].values() for hook_id in ids}
    extra = [{"id": h, "stage": s} for h, s in local.items() if h and h not in known]
    workflow_text = ""
    workflow_dir = root / ".github" / "workflows"
    if workflow_dir.is_dir():
        workflow_text = "\n".join(p.read_text(encoding="utf-8") for p in sorted(workflow_dir.glob("*.y*ml")))
    missing_workflows = [w["name"] for w in resolved["workflows"] if f"/workflows/{w['name']}@" not in workflow_text]
    if not (root / caller["path"]).is_file():
        missing_workflows.insert(0, caller["path"])
    return {
        "config": config.relative_to(root).as_posix() if config.is_file() else caller["config"],
        "missing": missing,
        "misplaced": misplaced,
        "extra": extra,
        "missing_ci_gates": suggested_ci,
        "missing_workflows": missing_workflows,
        "ok": not (missing or misplaced or missing_workflows),
    }


def emit(table: dict[str, Any], resolved: dict[str, Any], which: str) -> str:
    """The pre-commit format config a scaffold writes for ``pre-commit`` or ``ci-gates``."""
    stages = ("pre-commit", "pre-push") if which == "pre-commit" else ("ci-gates",)
    args = table.get("hook_args", {}) or {}
    repos: dict[str, dict[str, Any]] = {}
    for stage in stages:
        for hook_id in resolved["hooks"][stage]:
            source = resolved["hook_sources"][hook_id]
            entry = repos.setdefault(source["repo"], {"repo": source["repo"], "hooks": []})
            if source["rev"]:
                entry["rev"] = source["rev"]
            hook: dict[str, Any] = {"id": hook_id, **(args.get(hook_id, {}) or {})}
            if source["source"] == "local":
                hook.update({"name": hook_id, "entry": f"TODO {hook_id} command", "language": "system"})
                hook["pass_filenames"] = False
            if stage == "pre-push":
                hook["stages"] = ["pre-push"]
            entry["hooks"].append(hook)
    header = {"default_stages": ["pre-commit"]}
    if which == "pre-commit":
        header = {"default_install_hook_types": ["pre-commit", "pre-push"], **header}
    ordered = [{"repo": r["repo"], **({"rev": r["rev"]} if "rev" in r else {}), "hooks": r["hooks"]} for r in repos.values()]
    banner = "# Generated by `pipelines-hook stack-profile --emit` from reference/stack-profiles.yml.\n"
    return banner + yaml.safe_dump({**header, "repos": ordered}, sort_keys=False)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="stack-profile", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--profile", action="append", default=[], help="add a profile (new project)")
    parser.add_argument("--table", type=Path, default=None, help="profile table (default: the packaged one)")
    parser.add_argument("--check", action="store_true", help="fail when a required hook or workflow is absent")
    parser.add_argument("--emit", choices=("pre-commit", "ci-gates"), default=None)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    table = load_table(args.table)
    root = args.root.resolve()
    selected = detect(table, Facts(root), args.profile)
    resolved = resolve(table, selected)
    if args.emit:
        sys.stdout.write(emit(table, resolved, args.emit))
        return 0
    report: dict[str, Any] = {"root": root.name, "profiles": list(selected), "evidence": selected, **resolved}
    if args.check:
        report["check"] = check(root, resolved)
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 1 if args.check and not report["check"]["ok"] else 0
