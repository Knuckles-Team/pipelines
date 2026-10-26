"""connector-render: the connector Dockerfile, debug Dockerfile and compose files, rendered at build time.

    pipelines-connector render [--root R] [--out DIR] [--check]

Deterministic: the output depends only on the shared templates and the connector's
``pyproject.toml`` (``[project]`` and the optional ``[tool.pipelines.container]`` table).
Compose resource limits default to ``${MCP_CONTAINER_MEMORY_LIMIT:-2g}`` / ``${MCP_CONTAINER_CPU_LIMIT:-1.0}`` for both
image kinds; a repo that runs differently sets ``limits`` per kind, each key optional::

    [tool.pipelines.container]
    limits = {agent = {memory_limit_env = "AGENT_CONTAINER_MEMORY_LIMIT", memory_limit = "4g",
                       cpu_limit_env = "AGENT_CONTAINER_CPU_LIMIT", cpu_limit = "2.0"}}
``env_file_optional = true`` keeps ``../.env`` optional (compose starts without it) instead of required.
Nothing is read from a committed Dockerfile; a connector commits none of these files.
``--check`` renders into memory and fails when a tracked copy exists under ``docker/``
(a committed rendering is a second source of truth), printing nothing else.

The image installs the published wheel from PyPI with ``--only-binary :all:``, never
copies source, runs as a fixed non-root UID, and re-resolves the SDK inside the wheel's
supported range on every build (``ARG SDK_VERSION`` busts the layer when the SDK ships).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path, PurePosixPath
from typing import Any

from pipelines_hooks.connector import project
from pipelines_hooks.core.distributions import SDK as SDK_ROLE
from pipelines_hooks.core.distributions import is_distribution, project_distribution
from pipelines_hooks.core.errors import CannotRun

TEMPLATES = Path(__file__).resolve().parent / "templates"
RUNTIME_TARGETS = ("mcp", "agent")
OUTPUT_FILES = ("Dockerfile", "debug.Dockerfile", "mcp.compose.yml", "agent.compose.yml")
DEFAULT_LIMITS = {
    "memory_limit_env": "MCP_CONTAINER_MEMORY_LIMIT",
    "memory_limit": "2g",
    "cpu_limit_env": "MCP_CONTAINER_CPU_LIMIT",
    "cpu_limit": "1.0",
}
ENV_FILE_REQUIRED = "      - ../.env\n"
ENV_FILE_OPTIONAL = "      - path: ../.env\n        required: false\n"
CONFIG_ROOT = PurePosixPath("/etc")
_INTERPOLATION = re.compile(r"\$\{[A-Z_][A-Z0-9_]*(?:(?::?[-?])[^}\s]*)?\}")
_PLAIN_PATH = re.compile(r"/[^\s#'\"]*")
_VOLUME_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
STATE_VOLUME_KEYS = frozenset({"name", "target"})
DEFAULT_DEBUG_APT = (
    "ripgrep tree fd-find curl nano build-essential cmake libssl-dev libcurl4-openssl-dev pkg-config cargo rustc"
)


def builder_block(
    dist: str,
    version: str,
    stage: str,
    extra: str | None,
    sdists: list[str],
    sdk_distribution: str = "agent-connector-sdk",
) -> str:
    req = f"{dist}[{extra}]=={version}" if extra else f"{dist}=={version}"
    exempt = "".join(f" --no-binary {name}" for name in sdists)
    return (
        f"FROM builder-base AS builder-{stage}\n"
        "ARG SDK_VERSION=\n"
        "RUN --mount=type=cache,target=/root/.cache/uv \\\n"
        "    for attempt in 1 2 3 4 5 6 7 8 9 10; do \\\n"
        f"        uv pip install --system --break-system-packages --only-binary :all:{exempt} \\\n"
        f'            --refresh-package {dist} --upgrade-package {sdk_distribution} "{req}" && exit 0; \\\n'
        '        echo "wheel not installable yet (attempt ${attempt}); retrying in 30s"; \\\n'
        "        sleep 30; \\\n"
        "    done; \\\n"
        "    exit 1\n"
    )


def _entrypoints(table: dict[str, Any], scripts: set[str], dist: str) -> dict[str, str]:
    declared = dict(table.get("entrypoints", {}))
    found: dict[str, str] = {}
    for target in RUNTIME_TARGETS:
        name = declared.get(target) or next((s for s in sorted(scripts) if s.endswith(f"-{target}")), "")
        if not name and target == "mcp" and dist in scripts:
            name = dist
        if name:
            if name not in scripts:
                raise CannotRun(f"entrypoint {name!r} for {target} is not a [project.scripts] entry")
            found[target] = name
    if not found:
        raise CannotRun("no mcp or agent entrypoint: add [project.scripts] or [tool.pipelines.container.entrypoints]")
    return found


def _apt(packages: list[str]) -> str:
    return (
        "RUN apt-get update \\\n"
        f"    && apt-get install -y --no-install-recommends {' '.join(packages)} \\\n"
        "    && rm -rf /var/lib/apt/lists/*\n"
    )


def _dockerfile(
    dist: str,
    version: str,
    extras: set[str],
    table: dict[str, Any],
    entries: dict[str, str],
    sdk_distribution: str = "agent-connector-sdk",
) -> str:
    uid, home = str(table.get("uid", 10001)), str(table.get("home", "/tmp"))
    sdists = list(table.get("sdist_deps", []))
    targets = list(entries)
    builders, runtimes = [], []
    for target in targets:
        extra = target_extra(extras, table, target)
        builders.append(builder_block(dist, version, target, extra, sdists, sdk_distribution))
        copies = "".join(f"{c}\n" for c in table.get("stage_copies", []))
        label = "MCP server only" if target == "mcp" else "full agent runtime; can also run the MCP server"
        runtimes.append(
            f"# {target}: {label}.\nFROM runtime-base AS {target}\n"
            f"COPY --from=builder-{target} /usr/local /usr/local\n{copies}"
            f'USER {uid}:{uid}\nCMD ["{entries[target]}"]\n'
        )
    if table.get("builder_apt"):
        builders.insert(0, _apt(list(table["builder_apt"])))
    extra_stages = "".join("\n" + str(s).strip("\n") + "\n" for s in table.get("extra_stages", []))
    extra_runtime = "".join("\n" + str(s).strip("\n") + "\n" for s in table.get("extra_runtime_stages", []))
    values = {
        "@@BUILDERS@@": "\n" + "\n".join(builders),
        "@@EXTRA_STAGES@@": extra_stages,
        "@@RUNTIMES@@": "\n" + "\n".join(runtimes) + extra_runtime,
        "@@RUNTIME_APT@@": _apt(list(table["runtime_apt"])) if table.get("runtime_apt") else "",
        "@@RUNTIME_COPIES@@": "".join(f"{c}\n" for c in table.get("runtime_copies", [])),
        "@@STAGES@@": ", ".join(targets),
        "@@DIST@@": dist,
        "@@HOST@@": str(table.get("host", "127.0.0.1")),
        "@@PORT@@": str(table.get("port", 8000)),
        "@@HOME@@": home,
        "@@UID@@": uid,
    }
    return _fill(TEMPLATES / "Dockerfile.tmpl", values)


def target_extra(extras: set[str], table: dict[str, Any], target: str) -> str | None:
    """Return the package extra installed by a rendered runtime target.

    Keep this selector shared with the release guard.  A connector may provide MCP
    through a base dependency and omit an ``mcp`` optional dependency; the rendered
    target then deliberately installs the bare package.  ``install_extras`` remains
    an explicit per-target override, including an empty list for the bare package.
    """
    extra = target if target in extras else ("all" if "all" in extras else None)
    if target in table.get("install_extras", {}):
        extra = ",".join(table["install_extras"][target]) or None
    return extra


def _config_mount_entries(raw: Any) -> list[dict[str, str]]:
    """Validate and normalize the read-only bind entries declared by ``config_mounts``."""
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise CannotRun("[tool.pipelines.container] config_mounts is a list of tables")
    entries, seen = [], set()
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {"source", "target"}:
            raise CannotRun("each config mount is a table of exactly source and target")
        source, target = entry["source"], entry["target"]
        if not isinstance(source, str) or not isinstance(target, str):
            raise CannotRun("config mount source and target are strings")
        path = PurePosixPath(source)
        if not (_INTERPOLATION.fullmatch(source) or (path.is_absolute() and _PLAIN_PATH.fullmatch(source))) or (
            ".." in path.parts
        ):
            raise CannotRun(
                f"config mount source {source!r} must be an absolute host path or one ${{VAR}} interpolation"
            )
        under = PurePosixPath(target)
        if (
            not under.is_absolute()
            or ".." in under.parts
            or str(under) != target
            or CONFIG_ROOT not in under.parents
            or not _PLAIN_PATH.fullmatch(target)
        ):
            raise CannotRun(f"config mount target {target!r} must be a normalized absolute directory under /etc")
        if target in seen:
            raise CannotRun(f"two config mounts share the target {target!r}")
        seen.add(target)
        entries.append({"source": source, "target": target})
    return entries


def config_mounts_block(raw: Any) -> str:
    """The compose ``volumes:`` block of ``config_mounts`` as read-only bind mounts."""
    entries = _config_mount_entries(raw)
    if not entries:
        return ""
    return "    volumes:\n" + "".join(
        f"      - type: bind\n        source: {entry['source']}\n        target: {entry['target']}\n        read_only: true\n"
        for entry in entries
    )


def _state_volume_entries(raw: Any) -> list[dict[str, str]]:
    """Validate the typed named writable volumes declared by ``state_volumes``."""
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise CannotRun("[tool.pipelines.container] state_volumes is a list of tables")
    entries, names, targets = [], set(), set()
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != STATE_VOLUME_KEYS:
            raise CannotRun("each state volume is a table of exactly name and target")
        name, target = entry["name"], entry["target"]
        if not isinstance(name, str) or not _VOLUME_NAME.fullmatch(name):
            raise CannotRun("state volume name must be a Docker named-volume name")
        if not isinstance(target, str):
            raise CannotRun("state volume target is a string")
        path = PurePosixPath(target)
        if (
            "$" in target
            or not path.is_absolute()
            or target == "/"
            or ":" in target
            or ".." in path.parts
            or str(path) != target
            or not _PLAIN_PATH.fullmatch(target)
        ):
            raise CannotRun(f"state volume target {target!r} must be a literal normalized absolute path other than /")
        if CONFIG_ROOT == path or CONFIG_ROOT in path.parents:
            raise CannotRun(f"state volume target {target!r} must not be under /etc")
        if name in names:
            raise CannotRun(f"two state volumes share the name {name!r}")
        if target in targets:
            raise CannotRun(f"two state volumes share the target {target!r}")
        names.add(name)
        targets.add(target)
        entries.append({"name": name, "target": target})
    return entries


def state_volumes_block(raw: Any) -> str:
    """The service ``volumes:`` block for typed named writable state volumes."""
    service, _ = compose_volume_blocks(None, raw)
    return service


def compose_volume_blocks(config_raw: Any, state_raw: Any) -> tuple[str, str]:
    """Return the service and top-level Compose blocks for config and state volumes."""
    config_entries = _config_mount_entries(config_raw)
    state_entries = _state_volume_entries(state_raw)
    targets = [entry["target"] for entry in config_entries]
    for entry in state_entries:
        if entry["target"] in targets:
            raise CannotRun(f"config and state volumes share the target {entry['target']!r}")
    if not config_entries and not state_entries:
        return "", ""
    service_lines = ["    volumes:\n"]
    service_lines.extend(
        f"      - type: bind\n        source: {entry['source']}\n        target: {entry['target']}\n        read_only: true\n"
        for entry in config_entries
    )
    service_lines.extend(
        f"      - type: volume\n        source: {entry['name']}\n        target: {entry['target']}\n"
        for entry in state_entries
    )
    top_level = ""
    if state_entries:
        top_level = "volumes:\n" + "".join(f"  {entry['name']}: {{}}\n" for entry in state_entries)
    return "".join(service_lines), top_level


def _fill(template: Path, values: dict[str, str]) -> str:
    out = template.read_text(encoding="utf-8")
    for key, value in values.items():
        out = out.replace(key, value)
    return re.sub(r"\n{3,}", "\n\n", out).rstrip("\n") + "\n"


def render(root: Path, sdk_distribution: str | None = None) -> dict[str, str]:
    """``{file name: text}`` for every container file of the connector at ``root``."""
    pyproject = project.load(root)
    meta = pyproject.get("project", {})
    dist, version = meta.get("name"), meta.get("version")
    if not dist or not version:
        raise CannotRun("pyproject.toml needs a static [project] name and version")
    sdk = sdk_distribution or project_distribution(meta, SDK_ROLE)
    if not is_distribution(sdk, SDK_ROLE):
        raise CannotRun(f"unsupported SDK distribution: {sdk}")
    table = project.container_table(pyproject)
    extras = set(meta.get("optional-dependencies", {}))
    entries = _entrypoints(table, set(meta.get("scripts", {})), dist)
    debug_extras = list(table.get("debug_extras", sorted(extras & set(RUNTIME_TARGETS))))
    port, uid = str(table.get("port", 8000)), str(table.get("uid", 10001))
    files = {"Dockerfile": _dockerfile(dist, version, extras, table, entries, sdk)}
    files["debug.Dockerfile"] = _fill(
        TEMPLATES / "debug.Dockerfile.tmpl",
        {
            "@@HOST@@": str(table.get("host", "127.0.0.1")),
            "@@PORT@@": port,
            "@@DEBUG_APT@@": " ".join(table.get("debug_apt", DEFAULT_DEBUG_APT.split())),
            "@@DEBUG_EXTRAS@@": f"[{','.join(debug_extras)}]" if debug_extras else "",
            "@@UID@@": uid,
            "@@HOME@@": str(table.get("home", "/tmp")),
            "@@ENTRY@@": entries.get("mcp", next(iter(entries.values()))),
        },
    )
    env = "".join(f"      - {line}\n" for line in table.get("compose_env", []))
    volumes, top_level_volumes = compose_volume_blocks(table.get("config_mounts"), table.get("state_volumes"))
    env_file = ENV_FILE_OPTIONAL if table.get("env_file_optional") else ENV_FILE_REQUIRED
    for target in entries:
        service = f"{dist}-{target}"
        limits = {**DEFAULT_LIMITS, **dict(table.get("limits", {}).get(target, {}))}
        files[f"{target}.compose.yml"] = _fill(
            TEMPLATES / "compose.yml.tmpl",
            {
                "@@SERVICE@@": service,
                "@@IMAGE_VAR@@": re.sub(r"[^A-Z0-9]", "_", service.upper()) + "_IMAGE",
                "@@UID@@": uid,
                "@@PORT@@": port,
                "@@COMPOSE_ENV@@": env,
                "@@VOLUMES@@": volumes,
                "@@TOP_LEVEL_VOLUMES@@": top_level_volumes,
                "@@ENV_FILE@@": env_file,
                "@@MEMORY_ENV@@": str(limits["memory_limit_env"]),
                "@@MEMORY@@": str(limits["memory_limit"]),
                "@@CPU_ENV@@": str(limits["cpu_limit_env"]),
                "@@CPU@@": str(limits["cpu_limit"]),
            },
        )
    return files


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-render", description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, default=None, help="output directory (default: <root>/docker)")
    parser.add_argument("--check", action="store_true", help="render in memory; fail on a committed rendering")
    parser.add_argument(
        "--sdk-distribution",
        choices=("agent-connector-sdk", "scion-sdk"),
        default=None,
        help="SDK distribution to refresh in the image; omitted detects the project's dependency",
    )
    args = parser.parse_args(argv)
    files = render(args.root, args.sdk_distribution)
    if args.check:
        committed = [
            name for name in OUTPUT_FILES if (args.root / "docker" / name).exists() and _tracked(args.root, name)
        ]
        for name in committed:
            print(f"connector-render: docker/{name} is committed; it is rendered at build time", flush=True)
        return 1 if committed else 0
    out = args.out or args.root / "docker"
    out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8")
        print(f"connector-render: wrote {out / name}")
    return 0


def _tracked(root: Path, name: str) -> bool:
    from pipelines_hooks.core.gitenv import run_git

    result = run_git(root, ("ls-files", "--error-unmatch", f"docker/{name}"))
    return result.returncode == 0
