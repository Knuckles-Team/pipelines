"""Read a connector's ``pyproject.toml`` and its ``[tool.pipelines.*]`` tables."""

from __future__ import annotations

import ipaddress
import re
import tomllib
from pathlib import Path
from typing import Any, Callable

from pipelines_hooks.core.errors import CannotRun

CONTAINER_KEYS = frozenset(
    {
        "host",
        "compose_host",
        "port",
        "uid",
        "home",
        "entrypoints",
        "sdist_deps",
        "builder_apt",
        "runtime_apt",
        "runtime_copies",
        "stage_copies",
        "extra_stages",
        "extra_runtime_stages",
        "debug_apt",
        "debug_extras",
        "install_extras",
        "compose_env",
        "env_file_optional",
        "env_file_mode",
        "image_var",
        "restart",
        "tmpfs_size",
        "publish_port",
        "container_name",
        "hostname",
        "health_timeout",
        "health_command_timeout",
        "config_mounts",
        "state_volumes",
        "limits",
    }
)
LIMIT_KEYS = frozenset({"memory_limit_env", "memory_limit", "cpu_limit_env", "cpu_limit"})
DEFAULT_COMPOSE_HOST = "127.0.0.1"
_ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")
_BINDING_KEYS = frozenset({"env", "default"})
_DISTRIBUTION_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")


def load(root: Path) -> dict[str, Any]:
    """The parsed ``pyproject.toml`` of the connector at ``root``."""
    path = root / "pyproject.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"cannot read {path}: {exc}") from exc


def canonicalize_distribution_name(name: str) -> str:
    """Normalize a distribution name using the public package-name convention."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _distribution_names(raw: Any, key: str) -> list[str]:
    if not isinstance(raw, list):
        raise CannotRun(f"{key} must be a list of package names")
    if not all(isinstance(name, str) and _DISTRIBUTION_NAME.fullmatch(name) for name in raw):
        raise CannotRun(f"{key} entries must be exact package names")
    names = [canonicalize_distribution_name(name) for name in raw]
    if len(set(names)) != len(names):
        raise CannotRun(f"duplicate {key} entry")
    return sorted(names)


def source_build_allowance(pyproject: dict[str, Any]) -> list[str]:
    """Return the exact named source-build exceptions from ``[tool.pipelines]``.

    The same list drives wheel readiness and connector image rendering.  An empty
    or absent list keeps every dependency under the image's binary-only rule.
    """
    tool = pyproject.get("tool", {})
    if not isinstance(tool, dict):
        raise CannotRun("[tool] must be a table")
    pipelines = tool.get("pipelines", {})
    if not isinstance(pipelines, dict):
        raise CannotRun("[tool.pipelines] must be a table")
    return _distribution_names(pipelines.get("allow-source-build", []), "allow-source-build")


def container_source_builds(pyproject: dict[str, Any], table: dict[str, Any]) -> list[str]:
    """Combine the canonical allowance with the retained legacy container field."""
    names = source_build_allowance(pyproject)
    legacy = _distribution_names(table.get("sdist_deps", []), "[tool.pipelines.container].sdist_deps")
    return sorted(set(names).union(legacy))


def container_table(pyproject: dict[str, Any]) -> dict[str, Any]:
    """The ``[tool.pipelines.container]`` table; an unknown key is refused, never ignored."""
    table = pyproject.get("tool", {}).get("pipelines", {}).get("container", {})
    unknown = sorted(set(table) - CONTAINER_KEYS)
    if unknown:
        raise CannotRun(f"[tool.pipelines.container] has unknown keys: {', '.join(unknown)}")
    for kind, values in dict(table.get("limits", {})).items():
        bad = sorted(set(values) - LIMIT_KEYS) if isinstance(values, dict) else ["<not a table>"]
        if kind not in ("mcp", "agent") or bad:
            raise CannotRun(
                f"[tool.pipelines.container] limits.{kind} is not an mcp/agent table of {sorted(LIMIT_KEYS)}"
            )
    compose_host(table)
    publish_port(table, table.get("port", 8000))
    return dict(table)


def _validated_ip(raw: Any, key: str) -> str:
    if not isinstance(raw, str) or raw != raw.strip() or not raw:
        raise CannotRun(f"[tool.pipelines.container] {key} must be a non-empty IP address")
    host = raw.strip()
    if "%" in host:
        raise CannotRun(f"[tool.pipelines.container] {key} {host!r} must be an IP address")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        raise CannotRun(f"[tool.pipelines.container] {key} {host!r} must be an IP address") from None
    return host


def _validated_port(raw: Any, key: str) -> str:
    if isinstance(raw, bool):
        raise CannotRun(f"[tool.pipelines.container] {key} must be a port from 1 through 65535")
    if isinstance(raw, int):
        text = str(raw)
    elif isinstance(raw, str) and raw == raw.strip() and raw and raw.isdecimal():
        text = raw
    else:
        raise CannotRun(f"[tool.pipelines.container] {key} must be a port from 1 through 65535")
    if not 1 <= int(text) <= 65535:
        raise CannotRun(f"[tool.pipelines.container] {key} must be a port from 1 through 65535")
    return text


def _binding(
    raw: Any,
    key: str,
    default: Any,
    validate: Callable[[Any, str], str],
) -> str:
    value = default if raw is None else raw
    if isinstance(value, dict):
        if set(value) != _BINDING_KEYS:
            raise CannotRun(f"[tool.pipelines.container] {key} binding must contain exactly env and default")
        env = value.get("env")
        if not isinstance(env, str) or not _ENV_NAME.fullmatch(env):
            raise CannotRun(f"[tool.pipelines.container] {key}.env must be an uppercase environment variable name")
        validated = validate(value.get("default"), f"{key}.default")
        return f"${{{env}:-{validated}}}"
    return validate(value, key)


def compose_host(table: dict[str, Any]) -> str:
    """Return a literal IP or a validated Compose environment binding.

    Compose's short port syntax accepts an IP host binding, not a DNS name.
    """
    return _binding(table.get("compose_host"), "compose_host", DEFAULT_COMPOSE_HOST, _validated_ip)


def publish_port(table: dict[str, Any], container_port: Any) -> str:
    """Return a literal port or a validated Compose environment binding."""
    return _binding(table.get("publish_port"), "publish_port", container_port, _validated_port)


def package_dir(root: Path, pyproject: dict[str, Any]) -> Path:
    """The connector package directory: the connector entry point's module, else the project name."""
    points = pyproject.get("project", {}).get("entry-points", {}).get("agent_connector_sdk.connector", {})
    module = next((str(value).split(":")[0].split(".")[0] for value in points.values()), "")
    module = module or str(pyproject.get("project", {}).get("name", "")).replace("-", "_")
    return root / module
