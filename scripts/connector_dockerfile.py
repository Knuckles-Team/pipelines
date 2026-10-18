#!/usr/bin/env python3
"""Render a connector's docker/Dockerfile from templates/connector/Dockerfile.tmpl.

Deterministic: the output depends only on the template, the EXCEPTIONS table below,
the connector's pyproject.toml, and the facts read from its current Dockerfile
(stage names, CMD/ENTRYPOINT per stage, HOST/PORT defaults, UID, HOME). Re-running on
a generated file reproduces it byte for byte.

    python scripts/connector_dockerfile.py <connector-repo> [--check]

The rendered image installs the published wheel from PyPI with --only-binary :all:,
never copies source, builds no tools, runs as a fixed non-root UID, and keeps the
connector's entrypoint and port.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "connector" / "Dockerfile.tmpl"

# Connectors that genuinely need more than the wheel closure. Every entry is listed in
# the template's PR so the exceptions stay reviewable.
#   sdist_deps:           dependencies that publish no wheel; exempted with --no-binary
#                         and built in the discarded builder stage.
#   builder_apt:          Debian packages the builder needs for those sdists.
#   runtime_apt:          Debian packages the runtime needs (shared libraries / binaries).
#   keep_stages:          stages copied verbatim from the current Dockerfile, placed
#                         before runtime-base (prebuilt-binary or vendor-tool stages).
#   keep_runtime_stages:  stages copied verbatim after the generated runtime stages.
#   runtime_copies:       COPY lines added to runtime-base.
#   stage_copies:         COPY lines added to every generated runtime stage.
EXCEPTIONS: dict[str, dict[str, list[str]]] = {
    # pyaudio publishes no wheels: built in the discarded builder stage only.
    "audio-transcriber": {
        "sdist_deps": ["pyaudio"],
        "builder_apt": ["build-essential", "portaudio19-dev"],
        "runtime_apt": ["libportaudio2"],
    },
    "media-downloader": {"runtime_apt": ["ffmpeg"]},
    # pyspark and uptime-kuma-api publish sdists only (pure Python, no compiler).
    "spark-mcp": {"sdist_deps": ["pyspark"], "runtime_apt": ["default-jre-headless"]},
    "uptime-kuma-agent": {"sdist_deps": ["uptime-kuma-api"]},
    "container-manager-mcp": {
        "keep_stages": ["k8s-tools"],
        "runtime_copies": ["COPY --from=k8s-tools /out/ /usr/local/bin/"],
    },
    "servicenow-api": {
        "keep_stages": ["builder-node"],
        "stage_copies": ["COPY --from=builder-node /usr/local /usr/local"],
    },
    "langfuse-agent": {
        "keep_stages": ["builder-mcp-local"],
        "keep_runtime_stages": ["mcp-local"],
    },
}

RUNTIME_TARGETS = ("mcp", "agent")
FROM_RE = re.compile(r"^FROM\s+(\S+)(?:\s+AS\s+([A-Za-z0-9_.-]+))?\s*$", re.I)


def split_stages(text: str) -> list[tuple[str | None, list[str]]]:
    """Return [(stage_name, lines)] in file order; lines include the FROM line."""
    stages: list[tuple[str | None, list[str]]] = []
    for line in text.splitlines():
        match = FROM_RE.match(line)
        if match:
            stages.append((match.group(2), [line]))
        elif stages:
            stages[-1][1].append(line)
    return stages


def stage_text(lines: list[str]) -> str:
    """Stage text without trailing blank/comment lines that belong to the next stage."""
    out = list(lines)
    while out and (not out[-1].strip() or out[-1].lstrip().startswith("#")):
        out.pop()
    return "\n".join(out) + "\n"


def first(pattern: str, text: str, default: str) -> str:
    match = re.search(pattern, text, re.M)
    return match.group(1) if match else default


def builder_block(dist: str, version: str, stage: str, extra: str | None, sdists: list[str]) -> str:
    req = f"{dist}[{extra}]=={version}" if extra else f"{dist}=={version}"
    exempt = "".join(f" --no-binary {name}" for name in sdists)
    return (
        f"FROM builder-base AS builder-{stage}\n"
        "RUN --mount=type=cache,target=/root/.cache/uv \\\n"
        "    for attempt in 1 2 3 4 5 6 7 8 9 10; do \\\n"
        f"        uv pip install --system --break-system-packages --only-binary :all:{exempt} \\\n"
        f'            --refresh-package {dist} "{req}" && exit 0; \\\n'
        '        echo "wheel not installable yet (attempt ${attempt}); retrying in 30s"; \\\n'
        "        sleep 30; \\\n"
        "    done; \\\n"
        "    exit 1\n"
    )


def render(repo: Path) -> str:
    pyproject = tomllib.loads((repo / "pyproject.toml").read_text())
    project = pyproject["project"]
    dist, version = project["name"], project.get("version")
    if version is None:  # dynamic = ["version"] via setuptools attr = "pkg.module.__version__"
        attr = pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"]
        module = repo / (attr.rsplit(".", 1)[0].replace(".", "/") + ".py")
        version = first(r'^__version__\s*=\s*"([^"]+)"', module.read_text(), "")
        if not version:
            raise SystemExit(f"{repo.name}: cannot resolve dynamic version from {module}")
    extras = set(project.get("optional-dependencies", {}))
    current = (repo / "docker" / "Dockerfile").read_text()
    stages = split_stages(current)
    by_name = {name: lines for name, lines in stages if name}
    exc = EXCEPTIONS.get(repo.name, {})

    scripts = set(project.get("scripts", {}))

    def entry(target: str) -> str | None:
        line = next((ln for ln in by_name[target] if re.match(r"^(CMD|ENTRYPOINT)\b", ln)), None)
        exe = re.search(r'\[\s*"([^"]+)"', line or "")
        return line if line and exe and exe.group(1) in scripts else None

    # A stage whose entrypoint script the package no longer ships is dropped.
    targets = [t for t in RUNTIME_TARGETS if t in by_name and entry(t)]
    if not targets:
        raise SystemExit(f"{repo.name}: no mcp/agent stage in docker/Dockerfile")

    uid = first(r"^USER\s+(\d+)", current, "") or first(r"useradd[^\n]*--uid\s+(\d+)", current, "10001")
    home = first(r"^\s*(?:ENV\s+)?HOME=(\S+?)\s*\\?$", current, "/tmp")
    host = first(r"^ARG HOST=(\S+)", current, "127.0.0.1")
    port = first(r"^ARG PORT=(\S+)", current, "8000")

    builders, runtimes = [], []
    for target in targets:
        cmd = entry(target)
        extra = target if target in extras else ("all" if "all" in extras else None)
        builders.append(builder_block(dist, version, target, extra, exc.get("sdist_deps", [])))
        copies = "".join(f"{c}\n" for c in exc.get("stage_copies", []))
        label = "MCP server only" if target == "mcp" else "full agent runtime; can also run the MCP server"
        runtimes.append(
            f"# {target}: {label}.\n"
            f"FROM runtime-base AS {target}\n"
            f"COPY --from=builder-{target} /usr/local /usr/local\n"
            f"{copies}"
            f"USER {uid}:{uid}\n"
            f"{cmd}\n"
        )
    # mcp first, agent last: the last stage is the default `docker build` target.
    kept = "".join("\n" + stage_text(by_name[s]) for s in exc.get("keep_stages", []))
    kept_rt = "".join("\n" + stage_text(by_name[s]) for s in exc.get("keep_runtime_stages", []))
    apt = exc.get("runtime_apt", [])
    runtime_apt = (
        "RUN apt-get update \\\n"
        f"    && apt-get install -y --no-install-recommends {' '.join(apt)} \\\n"
        "    && rm -rf /var/lib/apt/lists/*\n"
        if apt
        else ""
    )
    builder_apt = exc.get("builder_apt", [])
    if builder_apt:
        builders.insert(
            0,
            "RUN apt-get update \\\n"
            f"    && apt-get install -y --no-install-recommends {' '.join(builder_apt)} \\\n"
            "    && rm -rf /var/lib/apt/lists/*\n",
        )
    runtime_copies = "".join(f"{c}\n" for c in exc.get("runtime_copies", []))

    out = TEMPLATE.read_text()
    for key, value in {
        "@@BUILDERS@@": "\n" + "\n".join(builders),
        "@@EXTRA_STAGES@@": kept,
        "@@RUNTIMES@@": "\n" + "\n".join(runtimes) + kept_rt,
        "@@RUNTIME_APT@@": runtime_apt,
        "@@RUNTIME_COPIES@@": runtime_copies,
        "@@STAGES@@": ", ".join(targets + exc.get("keep_runtime_stages", [])),
        "@@DIST@@": dist,
        "@@HOST@@": host,
        "@@PORT@@": port,
        "@@HOME@@": home,
        "@@UID@@": uid,
    }.items():
        out = out.replace(key, value)
    return re.sub(r"\n{3,}", "\n\n", out).rstrip("\n") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repos", nargs="+", type=Path)
    parser.add_argument("--check", action="store_true", help="fail if a Dockerfile would change")
    args = parser.parse_args()
    drift = 0
    for repo in args.repos:
        path = repo / "docker" / "Dockerfile"
        rendered = render(repo)
        if path.read_text() == rendered:
            continue
        drift += 1
        if args.check:
            print(f"{repo.name}: docker/Dockerfile is not the rendered template", file=sys.stderr)
        else:
            path.write_text(rendered)
            print(f"{repo.name}: rendered")
    return 1 if (args.check and drift) else 0


if __name__ == "__main__":
    sys.exit(main())
