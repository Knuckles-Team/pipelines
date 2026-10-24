"""Pipelines-owned boilerplate rules n to v (PIPE-GATES-R016.91 and following).

Source: ``plans/connector-pipelines-central-codemod-rules-2026-10-23.md``. Each rule requires the full pre-migration
shape and otherwise records a review item and leaves every file alone. The in-process implementations in
``pipelines_hooks.connector`` are the single definition of what the central tooling renders, generates and checks.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
import re
import shutil
import tempfile
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

import pipelines_hooks
from pipelines_hooks.connector import api_parity, codespell, container, generate, project, security
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.hygiene.connector_central import container_generations as generations
from pipelines_hooks.hygiene.connector_central.base import Ctx, rule

ORDER: tuple[str, ...] = ("pl.n", "pl.o", "pl.p", "pl.q", "pl.r", "pl.t", "pl.u", "pl.v", "pl.s")

SDK_REBUILD_WORKFLOW = """name: Connector SDK rebuild

on:
  repository_dispatch:
    types: [sdk-release]
  schedule:
    - cron: '17 5 * * *'
  workflow_dispatch:

permissions:
  contents: read

jobs:
  rebuild:
    uses: Knuckles-Team/pipelines/.github/workflows/connector_sdk_rebuild_pipeline.yml@main
    secrets: inherit
"""
PYTHON_PIPELINE = "Knuckles-Team/pipelines/.github/workflows/python_pipeline.yml@main"
CONTAINER_PIPELINE = "Knuckles-Team/pipelines/.github/workflows/container_pipeline.yml@main"
SANITIZER_SHA = "804eb9c6d60c1b1e37a1"
CODESPELL_SHA = "5837bc657ab01809e047"
SEMVER = r"\d+\.\d+\.\d+"
STANDARD_COMPOSE_ENV = ("PYTHONUNBUFFERED=1", "HOST=0.0.0.0", "TRANSPORT=streamable-http")


def pipelines_root(ctx: Ctx) -> Path:
    """The pipelines checkout that owns the templates and defaults."""
    given = ctx.options.get("pipelines_root")
    return Path(given) if given else Path(pipelines_hooks.__file__).resolve().parent.parent


# --- shared text helpers ----------------------------------------------------------------------------------------
def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_scalar(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{json.dumps(str(k))} = {_toml_scalar(v)}" for k, v in value.items()) + "}"
    return json.dumps(str(value), ensure_ascii=False)


def _table_text(keys: tuple[str, ...], values: dict[str, Any]) -> str:
    """``[keys]`` with ``values``; the container ``config_mounts`` list is written as ``[[keys.config_mounts]]`` tables."""
    arrays = {k: v for k, v in values.items() if k == "config_mounts" and v}
    body = "".join(f"{k} = {_toml_scalar(v)}\n" for k, v in values.items() if k not in arrays)
    tables = "".join(
        f"\n[[{'.'.join(keys)}.{k}]]\n" + "".join(f"{kk} = {_toml_scalar(vv)}\n" for kk, vv in entry.items())
        for k, entries in arrays.items()
        for entry in entries
    )
    return f"[{'.'.join(keys)}]\n{body}{tables}"


def _lookup(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def _append_table(ctx: Ctx, rule_id: str, keys: tuple[str, ...], values: dict[str, Any]) -> bool | None:
    """Append ``[keys]`` with ``values`` to pyproject.toml. True: written or already identical; None: blocked."""
    text = ctx.read("pyproject.toml")
    current = _lookup(tomllib.loads(text), keys)
    if current is not None:
        if current == values:
            return True
        ctx.note(rule_id, f"[{'.'.join(keys)}] already exists with other values: {current!r}", "pyproject.toml", True)
        return None
    new = text.rstrip("\n") + "\n\n" + _table_text(keys, values)
    try:
        if _lookup(tomllib.loads(new), keys) != values:
            raise ValueError("table differs after write")
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        ctx.note(rule_id, f"cannot append [{'.'.join(keys)}] to pyproject.toml exactly: {exc}", "pyproject.toml", True)
        return None
    ctx.write("pyproject.toml", new, rule_id)
    return True


def _gitignore(ctx: Ctx, rule_id: str, lines: list[str]) -> None:
    old = ctx.read(".gitignore") if ctx.exists(".gitignore") else ""
    have = {ln.strip() for ln in old.splitlines()}
    missing = [ln for ln in lines if ln not in have]
    if not missing:
        return
    base = old if not old or old.endswith("\n") else old + "\n"
    ctx.write(".gitignore", base + "".join(f"{ln}\n" for ln in missing), rule_id)


def _remove_files(ctx: Ctx, rule_id: str, names: list[str]) -> None:
    for name in names:
        ctx.delete(name, rule_id)


@contextmanager
def _source_date_epoch(epoch: str) -> Iterator[None]:
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = epoch
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old


# --- pl.n: version lives in pyproject.toml only ---------------------------------------------------------------------
VERSION_FILES = ("__init__.py", "mcp_server.py", "agent_server.py", "api_client.py", "version.py", "_version.py")
VERSION_TESTS = ("tests/test_startup.py", "tests/test_init_dynamics.py")
_ASSIGN = re.compile(r"""^__version__\s*(?::\s*str\s*)?=\s*["'][^"']*["']\s*(?:#.*)?$""")


def _dynamic_version(ctx: Ctx, text: str) -> str | None:
    """Make a ``dynamic = ["version"]`` project static; returns the new pyproject text or None (reviewed)."""
    data = tomllib.loads(text)
    attr = _lookup(data, ("tool", "setuptools", "dynamic", "version", "attr"))
    version = ""
    if isinstance(attr, str) and "." in attr:
        module = ctx.root / (attr.rsplit(".", 1)[0].replace(".", "/") + ".py")
        match = re.search(
            r"""^__version__\s*=\s*["']([^"']+)["']""", module.read_text() if module.is_file() else "", re.M
        )
        version = match.group(1) if match else ""
    if not version and ctx.exists(".bumpversion.cfg"):
        match = re.search(r"^current_version\s*=\s*(" + SEMVER + r")\s*$", ctx.read(".bumpversion.cfg"), re.M)
        version = match.group(1) if match else ""
    if not version:
        ctx.note(
            "pl.n",
            "dynamic version cannot be resolved (no attr literal, no bumpversion current_version)",
            "pyproject.toml",
            True,
        )
        return None
    lines = text.splitlines(keepends=True)
    dyn = [i for i, ln in enumerate(lines) if re.match(r"""^dynamic\s*=\s*\[\s*["']version["']\s*,?\s*\]\s*$""", ln)]
    attr_line = [
        i
        for i, ln in enumerate(lines)
        if re.match(r"""^version\s*=\s*\{\s*attr\s*=\s*["'][^"']+["']\s*,?\s*\}\s*$""", ln)
    ]
    heads = [i for i, ln in enumerate(lines) if ln.strip() == "[project]"]
    if len(dyn) != 1 or len(attr_line) != 1 or len(heads) != 1:
        ctx.note(
            "pl.n",
            'dynamic version table has a shape other than dynamic=["version"] + {attr=...}',
            "pyproject.toml",
            True,
        )
        return None
    dyn_i, attr_i = dyn[0], attr_line[0]
    out = list(lines)
    out[dyn_i] = f'version = "{version}"\n'
    del out[attr_i]
    new = "".join(out)
    # drop the now-empty [tool.setuptools.dynamic] header
    new = re.sub(r"^\[tool\.setuptools\.dynamic\]\n(?=\n|\[|\Z)\n?", "", new, flags=re.M)
    try:
        check = tomllib.loads(new)
    except tomllib.TOMLDecodeError:
        ctx.note("pl.n", "rewritten pyproject.toml does not parse", "pyproject.toml", True)
        return None
    if check.get("project", {}).get("version") != version or "dynamic" in check.get("project", {}):
        ctx.note("pl.n", "dynamic version rewrite did not produce a static version", "pyproject.toml", True)
        return None
    return new


def _py_files(ctx: Ctx) -> list[Path]:
    skip = {".venv", "node_modules", "site-packages", ".git"}
    return [p for p in ctx.root.rglob("*.py") if not skip.intersection(p.relative_to(ctx.root).parts)]


def _insert_import(text: str, statement: str) -> str:
    if re.search(rf"^{re.escape(statement)}\s*$", text, re.M):
        return text
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    target = None
    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom) and not (
            isinstance(node, ast.ImportFrom) and node.module == "__future__"
        ):
            target = node.lineno - 1
            break
    if target is None:
        last = (
            tree.body[0].end_lineno
            if tree.body and isinstance(getattr(tree.body[0], "value", None), ast.Constant)
            else 0
        )
        target = last or 0
    lines.insert(target, statement + "\n")
    return "".join(lines)


@rule("pl.n")
def rule_n(ctx: Ctx) -> None:
    text = ctx.read("pyproject.toml")
    data = tomllib.loads(text)
    meta = data.get("project", {})
    if "version" not in meta:
        if "version" in meta.get("dynamic", []):
            new = _dynamic_version(ctx, text)
            if new is None:
                return
            ctx.write("pyproject.toml", new, "pl.n")
            meta = tomllib.loads(new)["project"]
        else:
            ctx.note("pl.n", "pyproject.toml has no static or dynamic [project] version", "pyproject.toml", True)
            return
    version = str(meta["version"])
    ctx.delete(".bumpversion.cfg", "pl.n")
    for name in ("README.md",):
        if ctx.exists(name):
            old = ctx.read(name)
            new = re.sub(rf"^[*_]?Version: {SEMVER}[*_]?[ \t]*\n(?:[ \t]*\n)?", "", old, flags=re.M)
            if new != old:
                ctx.write(name, new, "pl.n")
    # residual __version__ assignments in the listed files
    for path in _py_files(ctx):
        rel = ctx.rel(path)
        if rel.startswith("tests/") or not (path.parent == ctx.pkg or path.name in VERSION_FILES):
            continue
        if path.name not in VERSION_FILES:
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        lines = src.splitlines(keepends=True)
        hits = [i for i, ln in enumerate(lines) if _ASSIGN.match(ln.rstrip("\n"))]
        if not hits:
            continue
        readers = [i for i, ln in enumerate(lines) if "__version__" in ln and i not in hits]
        outside = [
            ctx.rel(p)
            for p in _py_files(ctx)
            if p != path
            and "__version__" in p.read_text(encoding="utf-8", errors="replace")
            and not ctx.rel(p).startswith("tests/")
        ]
        if readers or outside or path.name in ("version.py", "_version.py"):
            ctx.note(
                "pl.n",
                f"__version__ literal still read ({len(readers)} reader lines here, other files: {outside}); "
                f'replace readers by importlib.metadata.version("{ctx.dist}") by hand',
                rel,
                True,
            )
            continue
        ctx.write(rel, "".join(ln for i, ln in enumerate(lines) if i not in hits), "pl.n")
    # version-literal assertions in the two scaffold tests
    for rel in VERSION_TESTS:
        if not ctx.exists(rel):
            continue
        src = ctx.read(rel)
        pat = re.compile(
            rf"""^(\s*)assert\s+(?:[\w.]+\.__version__|importlib\.metadata\.version\([^)]*\))\s*==\s*["']{SEMVER}["']\s*$""",
            re.M,
        )
        if pat.search(src):
            new = pat.sub(lambda m: f'{m.group(1)}assert importlib.metadata.version("{ctx.dist}")', src)
            new = _insert_import(new, "import importlib.metadata")
            ctx.write(rel, new, "pl.n")
    # a version literal anywhere else
    literal = re.compile(r"""^\s*__version__\s*=\s*["']""" + re.escape(version) + r"""["']""", re.M)
    for path in _py_files(ctx):
        if literal.search(path.read_text(encoding="utf-8", errors="replace")):
            ctx.note("pl.n", "file spells the package version; read importlib.metadata.version", ctx.rel(path), False)


# --- pl.o: container files are rendered, not committed ----------------------------------------------------------------
_FROM = re.compile(r"^FROM\s+(\S+)(?:\s+AS\s+([A-Za-z0-9_.-]+))?\s*$", re.I)
_APT = re.compile(r"apt-get install -y --no-install-recommends ([^\\\n]+?)\s*\\")


class _Unmatched(Exception):
    """The committed container files have a shape the renderer cannot reproduce."""


def _stages(text: str) -> list[tuple[str | None, list[str]]]:
    stages: list[tuple[str | None, list[str]]] = []
    for line in text.splitlines():
        match = _FROM.match(line)
        if match:
            stages.append((match.group(2), [line]))
        elif stages:
            stages[-1][1].append(line)
    return stages


def _stage_text(lines: list[str]) -> str:
    out = list(lines)
    while out and (not out[-1].strip() or out[-1].lstrip().startswith("#")):
        out.pop()
    return "\n".join(out) + "\n"


def _first(pattern: str, text: str, default: str) -> str:
    match = re.search(pattern, text, re.M)
    return match.group(1) if match else default


def _default_entry(target: str, scripts: set[str], dist: str) -> str:
    name = next((s for s in sorted(scripts) if s.endswith(f"-{target}")), "")
    return dist if not name and target == "mcp" and dist in scripts else name


def committed_table(ctx: Ctx, pyproject: dict[str, Any]) -> dict[str, Any]:
    """The ``[tool.pipelines.container]`` values that make the renderer reproduce ``docker/Dockerfile``."""
    current = ctx.read("docker/Dockerfile")
    meta = pyproject["project"]
    scripts, dist = set(meta.get("scripts", {})), meta["name"]
    stages = _stages(current)
    by_name = {name: lines for name, lines in stages if name}
    names = [name for name, _ in stages]
    older = "runtime-base" not in names and generations.is_older_dockerfile(current, dist)
    table: dict[str, Any] = {}
    uid = _first(r"^USER\s+(\d+)", current, "") or _first(r"useradd[^\n]*--uid\s+(\d+)", current, "10001")
    home = _first(r"^\s*(?:ENV\s+)?HOME=(\S+?)\s*\\?$", current, "/tmp")
    host = _first(r"^ARG HOST=(\S+)", current, "127.0.0.1")
    port = _first(r"^ARG PORT=(\S+)", current, "8000")
    if host != "127.0.0.1":
        table["host"] = host
    if port != "8000":
        table["port"] = int(port) if port.isdigit() else port
    if uid != "10001":
        table["uid"] = int(uid) if uid.isdigit() else uid
    if home != "/tmp":
        table["home"] = home
    entries: dict[str, str] = {}
    copies: list[str] = []
    for target in container.RUNTIME_TARGETS:
        if target not in by_name:
            continue
        line = next((ln for ln in by_name[target] if re.match(r"^(CMD|ENTRYPOINT)\b", ln)), "")
        exe = re.search(r'\[\s*"([^"]+)"', line)
        if not exe or exe.group(1) not in scripts:
            raise _Unmatched(f"stage {target} has no CMD/ENTRYPOINT naming a [project.scripts] entry")
        entries[target] = exe.group(1)
        for ln in by_name[target]:
            if ln.startswith("COPY ") and ln != f"COPY --from=builder-{target} /usr/local /usr/local":
                if ln not in copies:
                    copies.append(ln)
    declared = {t: n for t, n in entries.items() if n != _default_entry(t, scripts, dist)}
    if declared:
        table["entrypoints"] = declared
    sdists: list[str] = generations.older_sdist_deps(current) if older else []
    for target in container.RUNTIME_TARGETS:
        for name in re.findall(r"--no-binary (\S+)", "\n".join(by_name.get(f"builder-{target}", []))):
            if name not in sdists:
                sdists.append(name)
    if sdists:
        table["sdist_deps"] = sdists
    base = "\n".join(by_name.get("builder-base", []))
    apt = _APT.findall(base)
    if apt:
        table["builder_apt"] = apt[0].split()
    rt = by_name.get("runtime-base", [])
    rt_apt = _APT.findall("\n".join(rt))
    if rt_apt:
        table["runtime_apt"] = rt_apt[0].split()
    rt_copies = [ln for ln in rt if ln.startswith("COPY ")]
    if rt_copies:
        table["runtime_copies"] = rt_copies
    if copies:
        table["stage_copies"] = copies
    known = {
        "builder-base",
        "runtime-base",
        *container.RUNTIME_TARGETS,
        *(f"builder-{t}" for t in container.RUNTIME_TARGETS),
    }
    if "runtime-base" not in names and not older:
        raise _Unmatched(
            "no runtime-base stage, and the single-stage Dockerfile is not one of the recorded older generator forms"
        )
    if any(n is None for n in names):
        raise _Unmatched("an unnamed stage")
    split = names.index("runtime-base") if "runtime-base" in names else len(names)
    extra = [_stage_text(by_name[n]).rstrip("\n") for n in names[:split] if n and n not in known and not older]
    extra_rt = [_stage_text(by_name[n]).rstrip("\n") for n in names[split:] if n and n not in known and not older]
    if extra:
        table["extra_stages"] = extra
    if extra_rt:
        table["extra_runtime_stages"] = extra_rt
    # debug image
    if ctx.exists("docker/debug.Dockerfile"):
        dbg = ctx.read("docker/debug.Dockerfile")
        pk = _APT.findall(dbg)
        if pk and pk[0].split() != container.DEFAULT_DEBUG_APT.split():
            table["debug_apt"] = pk[0].split()
        ext = re.search(r"uv pip install [^\n]*? \.(?:\[([^\]]*)\])?\s*$", dbg, re.M)
        got = [e for e in (ext.group(1) or "").split(",") if e] if ext else []
        got = [e for e in got if e in meta.get("optional-dependencies", {}) or e not in DROPPABLE_EXTRAS]
        want = sorted(set(meta.get("optional-dependencies", {})) & set(container.RUNTIME_TARGETS))
        if got != want:
            table["debug_extras"] = got
    # which extras of the wheel each image installs: only a deviation from the renderer's default is recorded
    have = set(meta.get("optional-dependencies", {}))
    installs: dict[str, list[str]] = {}
    for target in container.RUNTIME_TARGETS:
        pin = re.search(
            rf'"{re.escape(dist)}(?:\[([A-Za-z0-9_,-]+)\])?==', "\n".join(by_name.get(f"builder-{target}", []))
        )
        if pin is None:
            continue
        # an extra rule l4 removed from the wheel was only a hollow pin of the SDK; the image no longer names it
        got = [e for e in (pin.group(1) or "").split(",") if e and e in have]
        default = [target] if target in have else (["all"] if "all" in have else [])
        if got != default:
            installs[target] = got
    if installs:
        table["install_extras"] = installs
    limits = _committed_limits(ctx, set(by_name))
    if limits:
        table["limits"] = limits
    # compose extras
    env: list[str] = []
    for target in container.RUNTIME_TARGETS:
        name = f"docker/{target}.compose.yml"
        if ctx.exists(name) and target in by_name:
            block = re.search(r"^    environment:\n((?:      - .*\n)+)", _list_environment(ctx.read(name)), re.M)
            items = [ln[8:].rstrip() for ln in (block.group(1).splitlines() if block else [])]
            fixed = [*STANDARD_COMPOSE_ENV[:2], f"PORT={port}", STANDARD_COMPOSE_ENV[2]]
            if items[:4] == fixed:
                for item in items[4:]:
                    if item not in env:
                        env.append(item)
    if env:
        table["compose_env"] = env
    optional = [
        t
        for t in container.RUNTIME_TARGETS
        if t in by_name
        and ctx.exists(f"docker/{t}.compose.yml")
        and container.ENV_FILE_OPTIONAL in ctx.read(f"docker/{t}.compose.yml")
    ]
    if optional:
        table["env_file_optional"] = True
    mounts = _committed_config_mounts(ctx, set(by_name))
    if mounts:
        table["config_mounts"] = mounts
    return table


#: Extras rule l4 may have dropped from the wheel; a committed install line naming one is an expected difference.
_MOUNT_ENTRY = re.compile(
    r"      - type: bind\n        source: (?P<source>\S+)\n        target: (?P<target>\S+)\n        read_only: true\n"
)


def _service_volumes(text: str) -> str | None:
    """The raw ``volumes:`` block lines (after the key) of the one service of a compose file; None when it has none."""
    match = re.search(r"^    volumes:\n((?:      .*\n|\n)*)", text, re.M)
    return None if match is None else match.group(1)


def _committed_config_mounts(ctx: Ctx, targets: set[str]) -> list[dict[str, str]]:
    """The read-only bind ``volumes:`` of the committed compose files, as the SDK ``config_mounts`` entries.

    The render writes the same mounts into every compose file, so the committed files must agree. A volume that is not a
    read-only bind of the long form with exactly source and target, or whose target the SDK schema refuses, blocks with
    the precise reason.
    """
    found: dict[str, list[dict[str, str]]] = {}
    for target in container.RUNTIME_TARGETS:
        name = f"docker/{target}.compose.yml"
        if target not in targets or not ctx.exists(name):
            continue
        block = _service_volumes(ctx.read(name))
        mounts: list[dict[str, str]] = []
        rest = block or ""
        while rest:
            entry = _MOUNT_ENTRY.match(rest)
            if entry is None:
                first = rest.splitlines()[0] if rest.strip() else "<blank>"
                raise _Unmatched(
                    f"{name} volumes: `{first.strip()}` is not a read-only bind mount of exactly source and target"
                )
            mounts.append({"source": entry["source"], "target": entry["target"]})
            rest = rest[entry.end() :]
        if mounts:
            try:
                container.config_mounts_block(mounts)
            except CannotRun as exc:
                raise _Unmatched(f"{name} volumes cannot be a config mount: {exc}") from exc
        found[target] = mounts
    if len({json.dumps(m) for m in found.values()}) > 1:
        raise _Unmatched("the committed compose files mount different volumes; the render mounts the same in each")
    return next(iter(found.values()), [])


DROPPABLE_EXTRAS = frozenset({"mcp", "agent", "all"})
_LIMIT_LINES = (
    ("memory_limit", "mem_limit", "memory_limit_env"),
    ("cpu_limit", "cpus", "cpu_limit_env"),
)


def _committed_limits(ctx: Ctx, entries: set[str]) -> dict[str, dict[str, str]]:
    """Per image kind, the compose ``mem_limit``/``cpus`` ``${VAR:-default}`` settings that differ from the template."""
    out: dict[str, dict[str, str]] = {}
    for target in container.RUNTIME_TARGETS:
        name = f"docker/{target}.compose.yml"
        if not ctx.exists(name) or target not in entries:
            continue
        text = ctx.read(name)
        found: dict[str, str] = {}
        for value_key, yaml_key, env_key in _LIMIT_LINES:
            match = re.search(rf"^    {yaml_key}: \$\{{([A-Za-z0-9_]+):-([^}}\s]*)\}}[ \t]*$", text, re.M)
            if match is None:
                continue
            if match.group(1) != container.DEFAULT_LIMITS[env_key]:
                found[env_key] = match.group(1)
            if match.group(2) != container.DEFAULT_LIMITS[value_key]:
                found[value_key] = match.group(2)
        if found:
            out[target] = found
    return out


def _drop_dist_extras(committed: str, rendered: str, dist: str) -> str:
    """Accept ``"<dist>[mcp]==v"`` (committed) where the render has ``"<dist>==v"``: rule l4 dropped that extra.

    Only extras the render no longer requests on the dist's own install requirement are removed; nothing else is touched.
    """
    kept = set(re.findall(rf'"{re.escape(dist)}\[([A-Za-z0-9_,-]+)\]==', rendered))
    return re.sub(
        rf'"{re.escape(dist)}\[(mcp|agent|all)\]==',
        lambda m: m.group(0) if m.group(1) in kept else f'"{dist}==',
        committed,
    )


def _align_dist_version(committed: str, rendered: str, dist: str) -> str:
    """Accept a committed ``"<dist>==x.y.z"`` pin whose only difference from the render is the semver.

    The central pass bumps the wheel version in ``pyproject.toml``; the committed pin still names the old release.
    Only the dist's own install requirement (same name, same extras, same quoting) is aligned.
    """
    pin = re.compile(rf'("{re.escape(dist)}(?:\[[A-Za-z0-9_,-]+\])?==)(\d+\.\d+\.\d+)(")')
    versions = {m.group(2) for m in pin.finditer(rendered)}
    if len(versions) != 1:
        return committed
    (version,) = versions
    return pin.sub(lambda m: f"{m.group(1)}{version}{m.group(3)}", committed)


def _drop_debug_extras(committed: str, extras: set[str]) -> str:
    """Remove dropped ``mcp``/``agent``/``all`` extras from the debug image's ``uv pip install ... .[extras]`` line."""

    def fix(match: re.Match[str]) -> str:
        keep = [e for e in match.group(2).split(",") if e and (e in extras or e not in DROPPABLE_EXTRAS)]
        return f"{match.group(1)}[{','.join(keep)}]" if keep else match.group(1)

    return re.sub(r"(?m)^(.*uv pip install [^\n]*? \.)\[([^\]]*)\](\s*)$", lambda m: fix(m) + m.group(3), committed)


def _normalise_dockerfile(text: str, new: bool) -> str:
    lines = text.splitlines()
    while lines and (not lines[0].strip() or lines[0].startswith("#")):
        lines.pop(0)
    out = []
    for ln in lines:
        if new and ln == "ARG SDK_VERSION=":
            continue
        out.append(ln.replace(" --upgrade-package agent-connector-sdk", "") if new else ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip("\n") + "\n"


_ENV_MAP_LINE = re.compile(r"^      ([A-Za-z_][A-Za-z0-9_]*):(?: (.*))?$")


def _env_scalar(raw: str) -> str | None:
    """The string a compose ``environment:`` mapping value stands for; None when the quoting is not plain."""
    if raw[:1] == '"' and raw[-1:] == '"' and len(raw) >= 2:
        body = raw[1:-1]
        return None if re.search(r'["\\]', body) else body
    if raw[:1] == "'" and raw[-1:] == "'" and len(raw) >= 2:
        body = raw[1:-1]
        return None if "'" in body else body
    return raw if raw and not raw.startswith(("{", "[", "&", "*", "|", ">", "!", "#")) and " #" not in raw else None


def _list_environment(text: str) -> str:
    """Compose treats ``environment:`` as a mapping or as a list of ``KEY=value`` alike; write a mapping as the list.

    Only a block made wholly of ``KEY: value`` lines with plain scalars is rewritten (an empty value is the list entry
    ``KEY``, which compose reads from the host environment); anything else is returned unchanged, so it keeps blocking.
    """
    match = re.search(r"^    environment:\n((?:      .*\n)+)", text, re.M)
    if match is None:
        return text
    items: list[str] = []
    for line in match.group(1).splitlines():
        entry = _ENV_MAP_LINE.match(line)
        if entry is None:
            return text
        raw = (entry.group(2) or "").strip()
        value = _env_scalar(raw) if raw else ""
        if value is None:
            return text
        items.append(f"      - {entry.group(1)}={value}" if raw else f"      - {entry.group(1)}")
    return text[: match.start(1)] + "\n".join(items) + "\n" + text[match.end(1) :]


def _normalise_loose(text: str) -> str:
    return "\n".join(generations.loose_lines(text)) + "\n"


def _compose_old_to_new(ctx: Ctx, name: str, text: str, dist: str) -> str:
    target = name.split(".")[0].split("/")[-1]
    services = re.findall(r"^  ([A-Za-z0-9_.-]+):\s*$", text.split("services:", 1)[-1], re.M)
    if len(services) != 1:
        raise _Unmatched(f"docker/{name.split('/')[-1]} declares services {services}, not exactly one")
    old = services[0]
    new = f"{dist}-{target}"
    old_var = re.sub(r"[^A-Z0-9]", "_", old.upper()) + "_IMAGE"
    new_var = re.sub(r"[^A-Z0-9]", "_", new.upper()) + "_IMAGE"
    return text.replace(old_var, new_var).replace(old, new)


def container_pair(
    ctx: Ctx, name: str, new: str, dist: str, port: str, rewrite: bool = True, host: str = "127.0.0.1"
) -> tuple[str, str] | None:
    """``(committed, rendered)`` normalised for comparison; None when the committed file is a recorded older form.

    ``rewrite=False`` leaves the recorded block rewrites out (the script that records them needs the raw difference).
    """
    rel = f"docker/{name}"
    old = ctx.read(rel)
    if name == "Dockerfile" and generations.is_older_dockerfile(old, dist):
        return None  # a recorded single-stage older generator form; the render is its modern equivalent
    if name != "Dockerfile" and generations.is_stub(name, old):
        return None  # a recorded stub of the earlier scaffold; the render is the complete file
    if name.endswith("compose.yml"):
        old = _compose_old_to_new(ctx, rel, _list_environment(old), dist)
    if name in ("Dockerfile", "debug.Dockerfile"):
        old = _align_dist_version(old, new, dist)
    if name == "Dockerfile":
        old = _drop_dist_extras(old, new, dist)
        return _normalise_dockerfile(old, False), _normalise_dockerfile(new, True)
    a, b = _normalise_loose(old), _normalise_loose(new)
    if rewrite:
        # Recorded rewrites name the install line as the older generator wrote it (``.[mcp]``), so they run before rule l4's
        # dropped extras are removed from it; running them after would never match once l4 had changed ``pyproject.toml``.
        a = generations.apply_rewrites(name, a, dist, port, host)
    if name == "debug.Dockerfile":
        a = _drop_debug_extras(a, set(ctx.pyproject()["project"].get("optional-dependencies", {})))
    return a, b


def _container_diff(
    ctx: Ctx, rendered: dict[str, str], dist: str, port: str = "8000", host: str = "127.0.0.1"
) -> list[str]:
    problems: list[str] = []
    for name, new in rendered.items():
        rel = f"docker/{name}"
        if not ctx.exists(rel):
            continue
        try:
            pair = container_pair(ctx, name, new, dist, port, host=host)
        except _Unmatched as exc:
            problems.append(str(exc))
            continue
        if pair is not None and pair[0] != pair[1]:
            diff = "".join(
                difflib.unified_diff(
                    pair[0].splitlines(True), pair[1].splitlines(True), f"committed/{rel}", f"rendered/{rel}"
                )
            )
            problems.append(f"{rel} differs from the rendered file beyond the expected changes:\n{diff}")
    for name in container.OUTPUT_FILES:
        if ctx.exists(f"docker/{name}") and name not in rendered and not _orphan_agent_compose(ctx, name):
            problems.append(f"docker/{name} is committed but nothing renders it")
    return problems


def _orphan_agent_compose(ctx: Ctx, name: str) -> bool:
    """``agent.compose.yml`` of a connector whose agent runtime is gone: no agent stage, no ``*-agent`` entry point.

    The earlier scaffold kept the agent service after it removed the agent image, so the file names an image no stage
    builds; the render writes ``mcp.compose.yml`` only.
    """
    if name != "agent.compose.yml" or not ctx.exists("docker/Dockerfile"):
        return False
    return "agent" not in {stage for stage, _ in _stages(ctx.read("docker/Dockerfile")) if stage}


def _job_span(lines: list[str], uses: str) -> tuple[int, int] | None:
    """Line range of the job whose ``uses:`` is exactly ``uses`` (jobs sit at indent 2, keys at indent 4)."""
    hit = [i for i, ln in enumerate(lines) if ln.rstrip() == f"    uses: {uses}"]
    if len(hit) != 1:
        return None
    start = hit[0]
    while start > 0 and not re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[start]):
        start -= 1
    end = hit[0] + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith("   ")):
        end += 1
    return start, end


def _with_flag(text: str, uses: str, flag: str) -> str | None:
    """Set ``flag: true`` under the ``with:`` of the job calling ``uses``; None when the shape is not recognised."""
    lines = text.splitlines(keepends=True)
    bare = [ln.rstrip("\n") for ln in lines]
    span = _job_span(bare, uses)
    if span is None:
        return None
    start, end = span
    job = bare[start:end]
    at = start + next(i for i, ln in enumerate(job) if ln.rstrip() == f"    uses: {uses}")
    withs = [i for i in range(start, end) if bare[i].rstrip() == "    with:"]
    if len(withs) > 1:
        return None
    if not withs:
        lines.insert(at + 1, f"    with:\n      {flag}: true\n")
        return "".join(lines)
    w = withs[0]
    j = w + 1
    while j < end and bare[j].startswith("      "):
        if re.match(rf"^      {flag}:\s*", bare[j]):
            return text if bare[j].rstrip() == f"      {flag}: true" else None
        j += 1
    lines.insert(w + 1, f"      {flag}: true\n")
    return "".join(lines)


@rule("pl.o")
def rule_o(ctx: Ctx) -> None:
    if not ctx.exists("docker/Dockerfile"):
        return
    pyproject = ctx.pyproject()
    dist = pyproject["project"]["name"]
    if "version" not in pyproject["project"]:
        ctx.note("pl.o", "no static [project] version; rule n must run first", "pyproject.toml", True)
        return
    try:
        table = committed_table(ctx, pyproject)
        with tempfile.TemporaryDirectory() as scratch:
            tmp = Path(scratch)
            ptext = ctx.read("pyproject.toml")
            if "container" in pyproject.get("tool", {}).get("pipelines", {}):
                ctx.note(
                    "pl.o",
                    "[tool.pipelines.container] already exists while docker/Dockerfile is committed",
                    "pyproject.toml",
                    True,
                )
                return
            ptext = ptext.rstrip("\n") + (
                "\n\n" + _table_text(("tool", "pipelines", "container"), table) if table else "\n"
            )
            (tmp / "pyproject.toml").write_text(ptext, encoding="utf-8")
            if table and project.container_table(tomllib.loads(ptext)) != table:
                raise _Unmatched("derived table does not round-trip through TOML")
            rendered = container.render(tmp)
            (tmp / "docker").mkdir()
            for name, text in rendered.items():
                (tmp / "docker" / name).write_text(text, encoding="utf-8")
    except (_Unmatched, CannotRun, KeyError, tomllib.TOMLDecodeError) as exc:
        ctx.note("pl.o", f"container files cannot be reproduced from pyproject.toml: {exc}", "docker/Dockerfile", True)
        return
    problems = _container_diff(ctx, rendered, dist, str(table.get("port", 8000)), str(table.get("host", "127.0.0.1")))
    if problems:
        ctx.note("pl.o", "committed container files stay:\n" + "\n".join(problems), "docker/Dockerfile", True)
        return
    workflows = (
        sorted(p for p in (ctx.root / ".github" / "workflows").glob("*.y*ml"))
        if (ctx.root / ".github" / "workflows").is_dir()
        else []
    )
    edited: dict[str, str] = {}
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        if CONTAINER_PIPELINE in text:
            new = _with_flag(text, CONTAINER_PIPELINE, "render_connector")
            new = _with_flag(new, PYTHON_PIPELINE, "connector") if new and PYTHON_PIPELINE in new else new
            if new is None or (PYTHON_PIPELINE in text and "connector: true" not in new):
                ctx.note(
                    "pl.o",
                    "caller workflow shape not recognised; add render_connector/connector flags by hand",
                    ctx.rel(path),
                    True,
                )
                return
            edited[ctx.rel(path)] = new
    if not edited:
        ctx.note("pl.o", "no workflow calls container_pipeline.yml@main", ".github/workflows", True)
        return
    sdk = ".github/workflows/sdk-rebuild.yml"
    if ctx.exists(sdk) and ctx.read(sdk) != SDK_REBUILD_WORKFLOW:
        ctx.note("pl.o", "sdk-rebuild.yml exists with other content", sdk, True)
        return
    if table and _append_table(ctx, "pl.o", ("tool", "pipelines", "container"), table) is None:
        return
    for rel, text in edited.items():
        ctx.write(rel, text, "pl.o")
    ctx.write(sdk, SDK_REBUILD_WORKFLOW, "pl.o")
    _remove_files(ctx, "pl.o", [f"docker/{n}" for n in container.OUTPUT_FILES])
    _gitignore(ctx, "pl.o", ["docker/Dockerfile", "docker/debug.Dockerfile", "docker/*.compose.yml"])


# --- pl.p: generated ontology artifacts -------------------------------------------------------------------------------
_SHAPE = re.compile(r"^shape:([A-Za-z0-9_]+)GovernanceShape a sh:NodeShape", re.M)
_TEST_REF = re.compile(r"certification\.json|connector\.shacl\.ttl")


def _stage_ontology(ctx: Ctx, tmp: Path, ptext: str) -> None:
    (tmp / "pyproject.toml").write_text(ptext, encoding="utf-8")
    if ctx.exists("connector_manifest.yml"):
        shutil.copy(ctx.root / "connector_manifest.yml", tmp / "connector_manifest.yml")
    for sub in ("ontology", "connectors"):
        if (ctx.pkg / sub).is_dir():
            shutil.copytree(ctx.pkg / sub, tmp / ctx.pkg_name / sub, dirs_exist_ok=True)


def _renamed_ontology(ctx: Ctx, source: str) -> str | None:
    """The stem of the ontology file when it is not ``<ontology_source>.ttl`` and is the only ``*.ttl`` there."""
    match = generate.SOURCE_RE.search(ctx.read(source))
    folder = ctx.pkg / "ontology"
    if match is None or (folder / f"{match.group(1)}.ttl").is_file():
        return None
    found = sorted(p.stem for p in folder.glob("*.ttl"))
    return found[0] if len(found) == 1 else None


def _with_ontology_table(ptext: str, values: dict[str, Any]) -> str:
    body = "".join(f"{k} = {_toml_scalar(v)}\n" for k, v in values.items())
    return ptext.rstrip("\n") + f"\n\n[tool.pipelines.ontology]\n{body}"


def _generated(ctx: Ctx, tmp: Path, epoch: str) -> dict[str, str]:
    with _source_date_epoch(epoch):
        files = generate.generate(tmp)
    return {p.relative_to(tmp).as_posix(): t for p, t in files.items()}


@rule("pl.p")
def rule_p(ctx: Ctx) -> None:
    shapes = f"{ctx.pkg_name}/ontology/shapes/connector.shacl.ttl"
    cert = f"{ctx.pkg_name}/ontology/certification.json"
    source = f"{ctx.pkg_name}/ontology/mappings/source.yaml"
    if not (ctx.exists(shapes) and ctx.exists(cert)):
        return
    if not (ctx.exists(source) and re.search(r"^ontology_source:", ctx.read(source), re.M)):
        ctx.note(
            "pl.p", "mappings/source.yaml does not declare ontology_source; artifacts stay committed", source, True
        )
        return
    try:
        stamp = json.loads(ctx.read(cert))["validated_at"]
        epoch = str(int(datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()))
    except (ValueError, KeyError, TypeError):
        ctx.note("pl.p", "certification.json has no parseable validated_at", cert, True)
        return
    stale_tests = []
    for path in sorted((ctx.root / "tests").rglob("*.py")) if (ctx.root / "tests").is_dir() else []:
        rel = ctx.rel(path)
        if _TEST_REF.search(path.read_text(encoding="utf-8", errors="replace")):
            if re.match(r"tests/(?:.*/)?test_(?:certification|shacl)[\w]*\.py$", rel):
                stale_tests.append(rel)
            else:
                ctx.note(
                    "pl.p",
                    "test reads the committed ontology artifacts and is not a certification/shacl test",
                    rel,
                    True,
                )
                return
    ptext = ctx.read("pyproject.toml")
    committed = ctx.read(shapes)
    table_values: dict[str, Any] | None = None
    review_widen = False
    existing = tomllib.loads(ptext).get("tool", {}).get("pipelines", {}).get("ontology")
    named = _renamed_ontology(ctx, source)
    if named and existing:
        ctx.note(
            "pl.p",
            "[tool.pipelines.ontology] already exists while the ontology file is not <ontology_source>.ttl",
            "pyproject.toml",
            True,
        )
        return
    if named:
        table_values = {"ttl": named}
        ptext = _with_ontology_table(ptext, table_values)
    try:
        with tempfile.TemporaryDirectory() as scratch:
            tmp = Path(scratch)
            _stage_ontology(ctx, tmp, ptext)
            produced = _generated(ctx, tmp, epoch)
            if produced[shapes] != committed:
                classes = sorted(set(_SHAPE.findall(committed)))
                table_values = {**(table_values or {}), "shape_classes": classes}
                if not classes or existing:
                    raise CannotRun("committed shapes are not a subset expressible as shape_classes")
                again = _with_ontology_table(ctx.read("pyproject.toml"), table_values)
                _stage_ontology(ctx, tmp, again)
                produced = _generated(ctx, tmp, epoch)
                if produced[shapes] != committed:
                    raise CannotRun("shape_classes does not reproduce the committed shapes byte for byte")
                review_widen = True
    except (CannotRun, OSError, KeyError) as exc:
        ctx.note("pl.p", f"generated shapes cannot be matched: {exc}", shapes, True)
        return
    if table_values is not None:
        if _append_table(ctx, "pl.p", ("tool", "pipelines", "ontology"), table_values) is None:
            return
    if review_widen:
        ctx.note(
            "pl.p",
            f"committed shapes are a subset of the declared classes; owner decides whether to widen: {table_values}",
            shapes,
            False,
        )
    _remove_files(ctx, "pl.p", [shapes, cert, *stale_tests])
    _gitignore(ctx, "pl.p", [shapes, cert])
    data = tomllib.loads(ctx.read("pyproject.toml"))
    listed = _lookup(data, ("tool", "setuptools", "package-data")) or {}
    for entries in listed.values():
        names = [e for e in entries if "connector.shacl.ttl" in e or "certification.json" in e]
        if names:
            ctx.note(
                "pl.p",
                f"package-data lists generated files by name: {names}; keep a glob such as ontology/**",
                "pyproject.toml",
                False,
            )


# --- pl.q: pre-commit config -----------------------------------------------------------------------------------------
UPSTREAM_REPOS = (
    "github.com/pre-commit/",
    "github.com/astral-sh/ruff-pre-commit",
    "github.com/jendrikseipp/vulture",
    "github.com/codespell-project/codespell",
    "github.com/PyCQA/bandit",
    "github.com/nbQA-dev/nbQA",
    "github.com/AleksaC/hadolint-py",
    "github.com/IamTheFij/docker-pre-commit",
    "github.com/Knuckles-Team/pipelines",
)
KNOWN_LOCAL = frozenset(
    "dependency-readiness uv-lock okf-no-legacy-concepts check-mermaid lane-guard check-stubs mermaid-validate "
    "check-agent-standards check-cli-help mcp-readme-table readme-env-vars readme-mcp-examples env-var-drift "
    "check-bumpversion pytest security-sanitizer verify-api-integration security-contract".split()
)
OPTION_TOOLS = frozenset({"ruff", "ruff-check", "ruff-format", "mypy", "vulture", "codespell", "bandit"})


_RUFF_EXCLUDE = re.compile(r"^\^\(((?:[\w.-]+/\|?)+)\)$")


def _port_ruff_exclude(ctx: Ctx, excludes: set[str]) -> None:
    """``exclude: ^(tests/|scripts/)`` on the ruff hooks becomes ``[tool.ruff] extend-exclude`` (one agreed pattern only)."""
    if len(excludes) != 1:
        return
    m = _RUFF_EXCLUDE.match(next(iter(excludes)))
    if m is None:
        return
    dirs = [d for d in dict.fromkeys(x.rstrip("/") for x in m.group(1).split("|")) if d and ctx.exists(d)]
    text = ctx.read("pyproject.toml")
    if not dirs or "extend-exclude" in text:
        return
    line = "extend-exclude = [" + ", ".join(f'"{d}"' for d in dirs) + "]\n"
    table = re.search(r"(?m)^\[tool\.ruff\]\n", text)
    new = text[: table.end()] + line + text[table.end() :] if table else text.rstrip("\n") + "\n\n[tool.ruff]\n" + line
    ctx.write("pyproject.toml", new, "pl.q")


@rule("pl.q")
def rule_q(ctx: Ctx) -> None:
    template = (pipelines_root(ctx) / "templates" / "connector" / "pre-commit-config.yaml").read_text(encoding="utf-8")
    if not ctx.exists(".pre-commit-config.yaml"):
        ctx.write(".pre-commit-config.yaml", template, "pl.q")
        return
    old = ctx.read(".pre-commit-config.yaml")
    if old == template:
        return
    try:
        config = yaml.safe_load(old) or {}
        repos = config.get("repos", [])
        unknown: list[str] = []
        options: list[str] = []
        ruff_excludes: set[str] = set()
        for repo in repos:
            url = str(repo.get("repo", ""))
            for hook in repo.get("hooks", []):
                hid = str(hook.get("id", ""))
                if url == "local":
                    ok = hid in KNOWN_LOCAL
                else:
                    ok = any(u in url for u in UPSTREAM_REPOS)
                if not ok:
                    unknown.append(f"{hid} ({url})")
                if hid in ("ruff", "ruff-check", "ruff-format") and hook.get("exclude"):
                    ruff_excludes.add(str(hook["exclude"]))
                if hid in OPTION_TOOLS and (hook.get("args") or hook.get("exclude")):
                    options.append(f"{hid}: args={hook.get('args')} exclude={hook.get('exclude')}")
        _port_ruff_exclude(ctx, ruff_excludes)
    except (yaml.YAMLError, AttributeError, TypeError) as exc:
        ctx.note(
            "pl.q",
            f"existing .pre-commit-config.yaml cannot be scanned ({exc}); replaced anyway",
            ".pre-commit-config.yaml",
            False,
        )
        unknown, options = [], []
    if unknown:
        ctx.note(
            "pl.q", f"hooks outside the known set were dropped: {', '.join(unknown)}", ".pre-commit-config.yaml", False
        )
    if options:
        ctx.note(
            "pl.q",
            "per-repo hook options not moved to pyproject tables: " + "; ".join(options),
            ".pre-commit-config.yaml",
            False,
        )
    ctx.write(".pre-commit-config.yaml", template, "pl.q")


# --- pl.r: security sanitizer and codespell ignore -----------------------------------------------------------------
def _sha(text: bytes) -> str:
    return hashlib.sha256(text).hexdigest()


def _doc_mentions(ctx: Ctx, rule_id: str, needles: tuple[str, ...]) -> None:
    for name in ("README.md", "AGENTS.md", "CONTRIBUTING.md", "CLAUDE.md"):
        if ctx.exists(name):
            for no, ln in enumerate(ctx.read(name).splitlines(), 1):
                if any(n in ln for n in needles):
                    ctx.note(rule_id, f"line {no} mentions a removed file: {ln.strip()[:160]}", name, False)


@rule("pl.r")
def rule_r(ctx: Ctx) -> None:
    script = "scripts/security_sanitizer.py"
    if ctx.exists(script):
        raw = (ctx.root / script).read_bytes()
        if not _sha(raw).startswith(SANITIZER_SHA):
            ref = ctx.options.get("sanitizer_reference")
            if ref and Path(ref).is_file():
                diff = "".join(
                    difflib.unified_diff(
                        Path(ref).read_text().splitlines(True),
                        raw.decode("utf-8", "replace").splitlines(True),
                        "fleet/security_sanitizer.py",
                        script,
                    )
                )
            else:
                diff = "(no fleet reference copy supplied; pass options['sanitizer_reference'] for a diff)"
            ctx.note(
                "pl.r", f"stale security_sanitizer.py deleted; check for a real local rule:\n{diff}", script, False
            )
        ctx.delete(script, "pl.r")
        test = "tests/test_security_sanitizer.py"
        if ctx.exists(test) and "security_sanitizer" in ctx.read(test):
            ctx.delete(test, "pl.r")
        for path in sorted((ctx.root / "tests").rglob("*.py")) if (ctx.root / "tests").is_dir() else []:
            if "security_sanitizer" in path.read_text(encoding="utf-8", errors="replace"):
                ctx.note("pl.r", "test still references the removed security_sanitizer.py", ctx.rel(path), True)
        _doc_mentions(ctx, "pl.r", ("security_sanitizer",))
    ignore = ".codespellignore"
    if ctx.exists(ignore):
        words = sorted(
            {w.strip() for w in ctx.read(ignore).splitlines() if w.strip() and not w.lstrip().startswith("#")}
            - {
                w.strip()
                for w in codespell.DEFAULT_IGNORE.read_text(encoding="utf-8").splitlines()
                if w.strip() and not w.startswith("#")
            }
        )
        if not _sha(ctx.read(ignore).encode()).startswith(CODESPELL_SHA) and not words:
            pass
        if words and _append_table(ctx, "pl.r", ("tool", "pipelines", "codespell"), {"ignore_words": words}) is None:
            return
        ctx.delete(ignore, "pl.r")


# --- pl.t: .security ---------------------------------------------------------------------------------------------------
@rule("pl.t")
def rule_t(ctx: Ctx) -> None:
    if not ctx.exists(".security"):
        return
    keep_contract = ctx.exists("scripts/security_contract.py")
    names = [".security/repository_fuzz.py", ".security/authenticated_negative.py"]
    contract_path = ".security/security-contract.json"
    additions: dict[str, Any] = {}
    if ctx.exists(contract_path) and not keep_contract:
        try:
            doc = json.loads(ctx.read(contract_path))
            policy = doc["license_policy"]
            default = json.loads(security.DEFAULT_CONTRACT.read_text(encoding="utf-8"))["license_policy"]
            allowed = sorted(set(policy.get("allowed", [])) - set(default["allowed"]))
            denied = sorted(set(policy.get("denied", [])) - set(default["denied"]))
        except (ValueError, KeyError, TypeError) as exc:
            ctx.note("pl.t", f"security-contract.json cannot be read: {exc}; .security stays", contract_path, True)
            return
        if policy.get("allowed_exceptions"):
            ctx.note(
                "pl.t",
                f"allowed_exceptions has no pipelines key yet: {policy['allowed_exceptions']}",
                contract_path,
                False,
            )
        if set(default["denied"]) - set(policy.get("denied", [])):
            ctx.note(
                "pl.t",
                "committed denied list is smaller than the shared default (the default is stricter)",
                contract_path,
                False,
            )
        if allowed:
            additions["license_allowed"] = allowed
        if denied:
            additions["license_denied"] = denied
        if additions and _append_table(ctx, "pl.t", ("tool", "pipelines", "security"), additions) is None:
            return
        names.append(contract_path)
    elif keep_contract and ctx.exists(contract_path):
        ctx.note(
            "pl.t",
            "scripts/security_contract.py still reads .security/security-contract.json; validator owner decides",
            contract_path,
            False,
        )
    _remove_files(ctx, "pl.t", [n for n in names if ctx.exists(n)])
    _doc_mentions(ctx, "pl.t", (".security/", "security-results/"))


# --- pl.u: scripts/bootstrap.sh ----------------------------------------------------------------------------------------
SETUP = (
    "- **Setup:** run `uv sync --locked`, then `uvx pre-commit install --hook-type pre-commit --hook-type pre-push`."
)


@rule("pl.u")
def rule_u(ctx: Ctx) -> None:
    if not ctx.exists("scripts/bootstrap.sh"):
        return
    ctx.delete("scripts/bootstrap.sh", "pl.u")
    for name in ("AGENTS.md", "README.md", "CONTRIBUTING.md", "CLAUDE.md"):
        if not ctx.exists(name):
            continue
        out: list[str] = []
        for no, ln in enumerate(ctx.read(name).splitlines(keepends=True), 1):
            if re.match(r"^- \*\*Setup:\*\* run `scripts/bootstrap\.sh`", ln):
                out.append(SETUP + "\n")
            elif "bootstrap.sh" in ln or "BOOTSTRAP_SKIP_HOOKS" in ln:
                if (
                    re.match(r"^\s*(?:[-*]\s+)?.*BOOTSTRAP_SKIP_HOOKS.*$", ln)
                    and "bootstrap.sh" not in ln
                    and ln.lstrip().startswith(("-", "*"))
                ):
                    continue
                ctx.note("pl.u", f"line {no} mentions scripts/bootstrap.sh: {ln.strip()[:160]}", name, False)
                out.append(ln)
            else:
                out.append(ln)
        ctx.write(name, "".join(out), "pl.u")


def _literal_baselines(source: str) -> dict[str, float] | None:
    """The module-level literal ``BASELINES`` table, or None when the script has none."""
    baselines: dict[str, float] | None = None
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "BASELINES" for t in node.targets):
            baselines = {str(k): float(v) for k, v in ast.literal_eval(node.value).items()}
    return baselines


_EXACT_PARITY = re.compile(r"""print\(\s*f?["'][^"'\n]*\b100(?:\.0)?%[^"'\n]*["']\s*\)""")


def _implied_baseline(source: str) -> float | None:
    """The coverage a script without a ``BASELINES`` table enforces, when it states it exactly.

    Two shapes only: one numeric ``baseline = <n>`` assignment that the script compares coverage against
    (``coverage < baseline - ...``), or an exact-parity script that fails (``return 1`` / ``sys.exit(1)``) on any
    mismatch and otherwise prints a literal 100% line, with no other numeric threshold. Anything else is None.
    """
    tree = ast.parse(source)
    assigns = [
        n.value.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "baseline"
        and isinstance(n.value, ast.Constant)
        and isinstance(n.value.value, (int, float))
    ]
    if len(assigns) == 1 and re.search(r"coverage\"?\]?\s*<\s*\(?\s*baseline\b", source):
        return float(assigns[0])
    exits = "return 1" in source or "sys.exit(1)" in source
    if not assigns and "baseline" not in source.lower() and exits and _EXACT_PARITY.search(source):
        return 100.0
    return None


# --- pl.v: verify_api_integration.py -----------------------------------------------------------------------------------
@rule("pl.v")
def rule_v(ctx: Ctx) -> None:
    script = "scripts/verify_api_integration.py"
    if not ctx.exists(script):
        return
    source = ctx.read(script)
    try:
        baselines = _literal_baselines(source)
    except (SyntaxError, ValueError, TypeError, AttributeError):
        ctx.note("pl.v", "BASELINES cannot be read from the committed script; script stays", script, True)
        return
    if baselines is None:
        implied = _implied_baseline(source)
        if implied is None:
            kind = (
                "it is a --source OpenAPI contract check, which connector-api-parity does not replace"
                if "--source" in source
                else "it states no coverage threshold and does not require exact 100% parity"
            )
            ctx.note(
                "pl.v",
                f"script has no literal BASELINES table or `baseline = <number>` threshold, and {kind}; script stays",
                script,
                True,
            )
            return
        baselines = {ctx.dist: implied}
    key = next((k for k in (ctx.dist, ctx.root.name, ctx.fleet) if k in baselines), "")
    baseline = baselines.get(key, 0.0)
    test = "tests/test_verify_api_integration.py"
    if ctx.exists(test) and "verify_api_integration" not in ctx.read(test):
        ctx.note("pl.v", "parity test file does not test the script; it may hold other tests", test, True)
        return
    prefixes: tuple[str, ...] = ()
    result = api_parity.measure(ctx.root, prefixes)
    values: dict[str, Any] = {}
    review: str | None = None
    if result is not None:
        if result["coverage"] < baseline - api_parity.TOLERANCE:
            server = next(iter(sorted(ctx.root.glob("**/mcp_server.py"))), None)
            names = set(
                re.findall(
                    r"^(?:async )?def (github_|gitlab_|adguard_|atlassian_)", server.read_text() if server else "", re.M
                )
            )
            prefixes = tuple(sorted(names))
            again = api_parity.measure(ctx.root, prefixes)
            if again is not None and again["coverage"] >= baseline - api_parity.TOLERANCE and prefixes:
                values["tool_prefixes"] = list(prefixes)
                result = again
            else:
                measured = (again or result)["coverage"]
                baseline = int(measured * 10) / 10
                review = f"measured coverage {measured:.1f}% is below the ported baseline; baseline set to {baseline}"
    if baseline > 0:
        values = {"baseline": baseline, **values}
    if values and _append_table(ctx, "pl.v", ("tool", "pipelines", "api_integration"), values) is None:
        return
    if review:
        ctx.note("pl.v", review, script, False)
    if result is not None and result["coverage"] < 100 and len(result["unmapped"]) > 20:
        ctx.note("pl.v", f"{len(result['unmapped'])} unmapped API methods (tech debt, no ratchet added)", script, False)
    _remove_files(ctx, "pl.v", [script, test])


# --- pl.s: workflow flags -----------------------------------------------------------------------------------------------
@rule("pl.s")
def rule_s(ctx: Ctx) -> None:
    folder = ctx.root / ".github" / "workflows"
    for path in sorted(folder.glob("*.y*ml")) if folder.is_dir() else []:
        rel = ctx.rel(path)
        text = path.read_text(encoding="utf-8")
        new = text

        def skip(match: re.Match[str]) -> str:
            items = [i.strip() for i in match.group(2).split(",") if i.strip()]
            kept = [i for i in items if i != "dupehound-changed"]
            if kept == items:
                return match.group(0)
            return f"{match.group(1)}{','.join(kept)}\n" if kept else ""

        new = re.sub(r"^( *skip-hooks: )([A-Za-z0-9_,\- ]+)\n", skip, new, flags=re.M)
        step = re.compile(r"^( *)- name: [^\n]*\n\1  run: uv tool install bump2version[ \t]*\n", re.M)
        new = step.sub("", new)
        if "bump2version" in new:
            ctx.note(
                "pl.s", "workflow still mentions bump2version in a shape that is not a single install step", rel, False
            )
        if new != text:
            ctx.write(rel, new, "pl.s")
