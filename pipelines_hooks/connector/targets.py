"""Additional named image targets: ``[tool.pipelines.container.targets.<name>]``.

A connector that must ship a second image next to its connector image (an application that
needs a real GUI process under a display, for example) declares it as configuration. The
renderer writes ``docker/<name>.Dockerfile`` and ``docker/<name>.entrypoint.sh`` from a template
owned by pipelines; the connector commits no Dockerfile and no entrypoint. The release pipeline
publishes the image in the same run as ``<image>:<version>-<name>`` with the tag set of the
primary image (PIPE-RELEASE-R001.16).

The one template today is ``gui-runtime`` (PIPE-RELEASE-R001.17). Keys of a target table::

    template        "gui-runtime" (required)
    base            image reference pinned by digest (default: a pinned Ubuntu LTS)
    version         the application version; "${version}" is replaced in app.url, setup and env
    uid, home       fixed non-root identity (default 10001, /home/app)
    display         X display (default ":99"); screen "1280x720x24"
    display_mode    "auto" (GPU X server when a GPU display exists, else software), "nvidia" or "xvfb"
    app             {url, sha256, dest, strip_components, link}: one archive, verified by checksum
    apt, setup      extra packages; extra shell steps run as root after the archive unpacks
    files           [{source, target}]: files of the build context copied into the image
    env             extra environment variables
    command         argv the entrypoint runs as the GUI process (required)
    viewer          true adds a watch/drive sidecar mode (x11vnc plus a web client); off at runtime
    viewer_port     the web client port (default 6080)
    licenses        SPDX expression for the image label; notice: lines written to the image
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path, PurePosixPath
from typing import Any

from pipelines_hooks.core.errors import CannotRun

TEMPLATES = Path(__file__).resolve().parent / "templates"
TEMPLATE_NAMES = ("gui-runtime",)
RESERVED_NAMES = frozenset({"mcp", "agent", "debug", "latest"})
DEFAULT_BASE = "ubuntu:24.04@sha256:562111b88caa79c71391c0c4d3c2114a7d5c35915c20561fd893cb1e07929e6b"
DISPLAY_MODES = ("auto", "nvidia", "xvfb")
TARGET_KEYS = frozenset(
    {
        "template",
        "base",
        "version",
        "uid",
        "home",
        "display",
        "screen",
        "display_mode",
        "app",
        "apt",
        "setup",
        "files",
        "env",
        "command",
        "viewer",
        "viewer_port",
        "licenses",
        "notice",
    }
)
APP_KEYS = frozenset({"url", "sha256", "dest", "strip_components", "link"})
_NAME = re.compile(r"[a-z][a-z0-9-]{0,30}")
_BASE = re.compile(r"[a-z0-9][a-z0-9./_-]*(?::[A-Za-z0-9_.-]+)?@sha256:[0-9a-f]{64}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_APT = re.compile(r"[a-z0-9][a-z0-9.+-]*")
_ENV = re.compile(r"[A-Z_][A-Z0-9_]*")
_DISPLAY = re.compile(r":[0-9]{1,3}")
_SCREEN = re.compile(r"[1-9][0-9]{2,4}x[1-9][0-9]{2,4}x(?:16|24|30)")
_PLAIN_PATH = re.compile(r"/[A-Za-z0-9_./-]*")
_RELATIVE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*")
_SAFE_TEXT = re.compile(r"[^\x00-\x1f\x7f]*")
_URL = re.compile(r"https://[A-Za-z0-9._~:/?#%@!$&*+,;=\[\]${}-]+")


def _fail(name: str, message: str) -> CannotRun:
    return CannotRun(f"[tool.pipelines.container.targets.{name}] {message}")


def _text(name: str, key: str, value: Any) -> str:
    if not isinstance(value, str) or not _SAFE_TEXT.fullmatch(value) or not value.strip():
        raise _fail(name, f"{key} must be a single-line string")
    return value


def _path(name: str, key: str, value: Any, *, absolute: bool = True) -> str:
    pattern = _PLAIN_PATH if absolute else _RELATIVE
    if not isinstance(value, str) or not pattern.fullmatch(value) or ".." in PurePosixPath(value).parts:
        kind = "normalized absolute path" if absolute else "relative path without .."
        raise _fail(name, f"{key} must be a {kind}")
    if absolute and (value == "/" or str(PurePosixPath(value)) != value):
        raise _fail(name, f"{key} must be a normalized absolute path other than /")
    if not absolute and str(PurePosixPath(value)) != value:
        raise _fail(name, f"{key} must be a normalized relative path")
    return value


def _strings(name: str, key: str, value: Any, pattern: re.Pattern[str] | None = None) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise _fail(name, f"{key} must be a list of non-empty strings")
    for item in value:
        if pattern is not None and not pattern.fullmatch(item):
            raise _fail(name, f"{key} entry {item!r} is not valid")
        if not _SAFE_TEXT.fullmatch(item):
            raise _fail(name, f"{key} entries must be single-line")
    return list(value)


def _validate_app(name: str, app: Any) -> None:
    if not isinstance(app, dict) or not {"url", "sha256"} <= set(app):
        raise _fail(name, "app is a table with at least url and sha256")
    unknown = sorted(set(app) - APP_KEYS)
    if unknown:
        raise _fail(name, f"app has unknown keys: {', '.join(unknown)}")
    if not isinstance(app["url"], str) or not _URL.fullmatch(app["url"]):
        raise _fail(name, "app.url must be an https URL")
    if not isinstance(app["sha256"], str) or not _SHA256.fullmatch(app["sha256"]):
        raise _fail(name, "app.sha256 must be a lowercase hex SHA-256 digest")
    if not (app["url"].endswith(".tar.xz") or app["url"].endswith(".tar.gz")):
        raise _fail(name, "app.url must name a .tar.xz or .tar.gz archive")
    if "dest" in app:
        _path(name, "app.dest", app["dest"])
    strip = app.get("strip_components", 1)
    if isinstance(strip, bool) or not isinstance(strip, int) or not 0 <= strip <= 5:
        raise _fail(name, "app.strip_components must be an integer from 0 to 5")
    if "link" in app:
        _path(name, "app.link", app["link"], absolute=False)


def _validate_target(name: str, target: Any) -> None:
    if not _NAME.fullmatch(name) or name in RESERVED_NAMES:
        raise CannotRun(f"image target name {name!r} must be lowercase letters, digits and dashes and not reserved")
    if not isinstance(target, dict):
        raise _fail(name, "must be a table")
    unknown = sorted(set(target) - TARGET_KEYS)
    if unknown:
        raise _fail(name, f"has unknown keys: {', '.join(unknown)}")
    if target.get("template") not in TEMPLATE_NAMES:
        raise _fail(name, f"template must be one of {', '.join(TEMPLATE_NAMES)}")
    if not isinstance(target.get("base", DEFAULT_BASE), str) or not _BASE.fullmatch(target.get("base", DEFAULT_BASE)):
        raise _fail(name, "base must be an image reference pinned by a sha256 digest")
    if "version" in target:
        _text(name, "version", target["version"])
    for key, default in (("uid", 10001), ("viewer_port", 6080)):
        value = target.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
            raise _fail(name, f"{key} must be an integer from 1 to 65535")
    if target.get("uid", 10001) < 1000:
        raise _fail(name, "uid must be a non-root identity (1000 or higher)")
    _path(name, "home", target.get("home", "/home/app"))
    if not _DISPLAY.fullmatch(str(target.get("display", ":99"))):
        raise _fail(name, "display must look like :99")
    if not _SCREEN.fullmatch(str(target.get("screen", "1280x720x24"))):
        raise _fail(name, "screen must look like 1280x720x24")
    if target.get("display_mode", "auto") not in DISPLAY_MODES:
        raise _fail(name, f"display_mode must be one of {', '.join(DISPLAY_MODES)}")
    if not isinstance(target.get("viewer", False), bool):
        raise _fail(name, "viewer must be true or false")
    if "app" in target:
        _validate_app(name, target["app"])
    _strings(name, "apt", target.get("apt", []), _APT)
    _strings(name, "setup", target.get("setup", []))
    command = _strings(name, "command", target.get("command", []))
    if not command:
        raise _fail(name, "command is required: the argv of the GUI process")
    for entry in target.get("files", []):
        if not isinstance(entry, dict) or set(entry) != {"source", "target"}:
            raise _fail(name, "each file is a table of exactly source and target")
        _path(name, "files.source", entry["source"], absolute=False)
        _path(name, "files.target", entry["target"])
    env = target.get("env", {})
    if not isinstance(env, dict) or not all(_ENV.fullmatch(k) and isinstance(v, str) for k, v in env.items()):
        raise _fail(name, "env is a table of uppercase names to strings")
    for value in env.values():
        _text(name, "env value", value)
    if "licenses" in target:
        _text(name, "licenses", target["licenses"])
    _strings(name, "notice", target.get("notice", []))


def validate(raw: Any) -> None:
    """Refuse an unknown key, a bad value or a reserved name; accept an absent table."""
    if raw in (None, {}):
        return
    if not isinstance(raw, dict):
        raise CannotRun("[tool.pipelines.container.targets] is a table of named targets")
    for name, target in raw.items():
        _validate_target(name, target)


def names(table: dict[str, Any]) -> list[str]:
    """The declared target names in a stable order."""
    return sorted(dict(table.get("targets", {})))


def output_files(table: dict[str, Any]) -> list[str]:
    """The rendered file names of every declared target."""
    return [f"{name}.{suffix}" for name in names(table) for suffix in ("Dockerfile", "entrypoint.sh")]


def _fill(template: Path, values: dict[str, str]) -> str:
    out = template.read_text(encoding="utf-8")
    for key, value in values.items():
        out = out.replace(key, value)
    return re.sub(r"\n{3,}", "\n\n", out).rstrip("\n") + "\n"


def _sub(text: str, version: str) -> str:
    return text.replace("${version}", version)


def _apt_block(packages: list[str]) -> str:
    return (
        "RUN apt-get update \\\n"
        f"    && apt-get install -y --no-install-recommends {' '.join(packages)} \\\n"
        "    && rm -rf /var/lib/apt/lists/*\n"
    )


def _app_block(app: dict[str, Any] | None, version: str) -> str:
    if not app:
        return ""
    dest = app.get("dest", "/opt/app")
    flag = "J" if app["url"].endswith(".tar.xz") else "z"
    strip = app.get("strip_components", 1)
    url = shlex.quote(_sub(app["url"], version))
    steps = [
        f"curl -sSfL --retry 5 --retry-delay 5 -o /tmp/app.archive {url}",
        f'echo "{app["sha256"]}  /tmp/app.archive" | sha256sum -c -',
        f"mkdir -p {dest}",
        f"tar -x{flag}f /tmp/app.archive -C {dest} --strip-components={strip}",
        "rm -f /tmp/app.archive",
    ]
    if "link" in app:
        steps.append(f"ln -s {dest}/{app['link']} /usr/local/bin/{PurePosixPath(app['link']).name}")
    return "RUN " + " \\\n    && ".join(steps) + "\n"


def _lines(prefix: str, items: list[str]) -> str:
    return "".join(f"{prefix}{item}\n" for item in items)


def _files_block(entries: list[dict[str, str]]) -> str:
    """COPY lines with explicit modes. ``COPY --chmod`` also applies to the directories it creates,
    so every parent directory is created world-traversable first; a file mode of 0644 lets the
    non-root runtime user read what root copied."""
    parents = sorted({str(PurePosixPath(entry["target"]).parent) for entry in entries} - {"/"})
    lines = f"RUN install -d -m 0755 {' '.join(parents)}\n" if parents else ""
    return lines + "".join(f"COPY --chmod=0644 {entry['source']} {entry['target']}\n" for entry in entries)


def render_target(name: str, target: dict[str, Any]) -> dict[str, str]:
    """``{file name: text}`` of one target: its Dockerfile and its entrypoint."""
    version = str(target.get("version", ""))
    uid, home = str(target.get("uid", 10001)), str(target.get("home", "/home/app"))
    viewer = bool(target.get("viewer", False))
    base_apt = ["ca-certificates", "curl", "xz-utils", "xvfb", "xauth", "xserver-xorg-core"]
    base_apt += ["libgl1", "libegl1", "libglx-mesa0", "libgl1-mesa-dri"]
    if viewer:
        base_apt += ["x11vnc", "novnc", "websockify"]
    packages = base_apt + [p for p in target.get("apt", []) if p not in base_apt]
    setup = [_sub(step, version) for step in target.get("setup", [])]
    files = _files_block(target.get("files", []))
    env = {k: _sub(v, version) for k, v in sorted(target.get("env", {}).items())}
    env_lines = "".join(f"ENV {k}={shlex.quote(v)}\n" for k, v in env.items())
    notice = target.get("notice", [])
    notice_block = ""
    if notice:
        doc = f"/usr/share/doc/{name}-image/NOTICE"
        notice_block = (
            f"RUN mkdir -p /usr/share/doc/{name}-image \\\n"
            f"    && printf '%s\\n' {' '.join(shlex.quote(_sub(line, version)) for line in notice)} > {doc}\n"
        )
    labels = ""
    if "licenses" in target:
        labels = f"LABEL org.opencontainers.image.licenses={shlex.quote(str(target['licenses']))}\n"
    dockerfile = _fill(
        TEMPLATES / "gui-runtime.Dockerfile.tmpl",
        {
            "@@NAME@@": name,
            "@@BASE@@": target.get("base", DEFAULT_BASE),
            "@@APT@@": _apt_block(packages),
            "@@APP@@": _app_block(target.get("app"), version),
            "@@SETUP@@": "".join(f"RUN {step}\n" for step in setup),
            "@@FILES@@": files,
            "@@NOTICE@@": notice_block,
            "@@UID@@": uid,
            "@@HOME@@": home,
            "@@DISPLAY@@": str(target.get("display", ":99")),
            "@@SCREEN@@": str(target.get("screen", "1280x720x24")),
            "@@MODE@@": str(target.get("display_mode", "auto")),
            "@@VIEWER_PORT@@": str(target.get("viewer_port", 6080)),
            "@@ENV@@": env_lines,
            "@@LABELS@@": labels,
        },
    )
    entrypoint = _fill(
        TEMPLATES / "gui-runtime.entrypoint.sh.tmpl",
        {
            "@@COMMAND@@": shlex.join([_sub(arg, version) for arg in target["command"]]),
            "@@NAME@@": name,
        },
    )
    return {f"{name}.Dockerfile": dockerfile, f"{name}.entrypoint.sh": entrypoint}


def render_all(table: dict[str, Any]) -> dict[str, str]:
    """Every rendered target file of the connector's container table."""
    files: dict[str, str] = {}
    for name in names(table):
        files.update(render_target(name, dict(table["targets"][name])))
    return files
