"""Build ``container_generations.json`` (recorded older container-file generations) from the connector fleet.

The repositories are the driver's set (``fleet.connector_repos()``: the workspace ``agents`` group that is active on
GitHub), never whatever directories sit under the fleet directory. For each one ``git archive origin/main`` is extracted, the container files
are rendered from ``pyproject.toml`` exactly as rule ``pl.o`` does, and the committed file is compared with the render.

* ``dockerfile_forms``: fingerprints of single-stage ``Dockerfile`` files (no ``runtime-base`` stage).
* ``stubs``: fingerprints of stub ``debug.Dockerfile`` / ``*.compose.yml`` files (``STUBS`` says what a stub is).
* ``rewrites``: the reviewed ``REWRITES`` below, each kept only when its old block occurs in at least ``--min-repos``
  repositories. ``--candidates`` prints the line blocks that differ in several repositories, to review new rewrites.

Every table entry must occur in ``--min-repos`` repositories, so only generator output survives, never a hand edit.

Usage: ``python scripts/connector_central_generations.py [--fleet DIR] [--out FILE] [--min-repos 3] [--candidates]``
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines_hooks.connector import container  # noqa: E402
from pipelines_hooks.core.errors import CannotRun  # noqa: E402
from pipelines_hooks.hygiene.connector_central import container_generations as gen  # noqa: E402
from pipelines_hooks.hygiene.connector_central import pipelines as P  # noqa: E402
from pipelines_hooks.hygiene.connector_central import rule_order  # noqa: E402
from pipelines_hooks.hygiene.connector_central.base import RULES, make_ctx  # noqa: E402
from pipelines_hooks.hygiene.connector_central.fleet import connector_repos  # noqa: E402

DEFAULT_FLEET = Path("/home/apps/workspace/agent-packages/agents")

#: What is a stub of the earlier scaffold: a short file that carries one of these instruction lines.
STUBS: dict[str, tuple[str, ...]] = {
    "debug.Dockerfile": ("ARG MCP_RUN_PYTHON_IMAGE",),
    "mcp.compose.yml": ("build: .",),
    "agent.compose.yml": ("build: .",),
}
STUB_MAX_LINES = 24

#: Reviewed older-generation block rewrites, by candidate id (see ``--candidates``) with the reason each is accepted.
#: Only a candidate that is in this table and occurs in ``--min-repos`` repositories is recorded.
ACCEPTED: dict[str, str] = {
    # debug image: the earlier generation installed uv, starship and rustup into /root with curl installers
    "fb4050bfca": "debug PATH no longer names /root/.local/bin",
    "8cb867685e": "debug image no longer sets the rustup/cargo homes of the curl-installed toolchain",
    "00af4ded7a": "debug image installs distro packages (cargo, rustc) instead of curl-piped installers",
    "7a18cc06d2": "debug install drops --upgrade --verbose",
    "1a320107f9": "debug PATH names the cargo bin directory",
    "4b09c53a59": "debug base image python:3.12 becomes the fleet python:3.14",
    "6f304d57c6": "debug base image python:3.11 becomes the fleet python:3.14",
    "b249e6ba78": "debug image copies the pinned uv binary the install line uses",
    # debug image of the generation that carried per-image OAuth/OIDC build args (auth is now SDK-owned)
    "41d7fc51c6": "debug default transport is stdio, as the runtime image",
    "946f0b12be": "debug image drops the per-image OAuth/OIDC/Eunomia build args",
    "71b18f0cc9": "debug image drops the per-image OAuth/OIDC/Eunomia environment lines",
    # compose
    "b5fd02ae46": "the published port binds to 127.0.0.1 (hardening)",
    "f6c7c4e788": "the mcp service names its own <DIST>_MCP_IMAGE variable, not the agent one",
}


HARDENING = [
    "    init: true",
    '    user: "10001:10001"',
    "    read_only: true",
    "    cap_drop:",
    "      - ALL",
    "    security_opt:",
    "      - no-new-privileges:true",
    "    pids_limit: 256",
    "    mem_limit: ${MCP_CONTAINER_MEMORY_LIMIT:-2g}",
    "    cpus: ${MCP_CONTAINER_CPU_LIMIT:-1.0}",
    "    tmpfs:",
    "      - /tmp:rw,noexec,nosuid,nodev,size=64m",
]
INSTALL = "RUN uv pip install --system --no-cache --break-system-packages .<EXTRAS>"
IMAGE = "    image: ${<DISTVAR>_MCP_IMAGE:?set-<DISTVAR>_MCP_IMAGE-to-image@sha256-digest}"
#: Reviewed blocks whose hunks are not a plain line diff (moved or inserted blocks), in application order (the compose
#: environment-file and image-variable blocks come last: they match the text the earlier compose rewrites produce). Each is kept
#: only when its old block matches the committed file in at least ``--min-repos`` repositories, like ``ACCEPTED``.
MANUAL: list[dict[str, Any]] = [
    {
        "id": "pre-release-install",
        "reason": "the earlier debug image allowed pre-releases and upgraded in verbose mode; the render installs the stable release",
        "file": "debug.Dockerfile",
        "old": [
            "RUN uv pip install --system --upgrade --verbose --no-cache --break-system-packages --prerelease=allow .<EXTRAS>"
        ],
        "new": [INSTALL],
    },
    {
        "id": "root-starship-copy",
        "reason": "the earlier debug image ran as root and copied a starship config into /root; the render is non-root",
        "file": "debug.Dockerfile",
        "old": ["COPY docker/starship.toml /root/.config/starship.toml"],
        "new": [],
    },
    {
        "id": "debug-app-user",
        "reason": "the earlier debug image ran as root; the render creates the app user after the install",
        "file": "debug.Dockerfile",
        "old": [INSTALL],
        "new": [
            INSTALL,
            "RUN groupadd --system --gid 10001 app \\",
            "    && useradd --system --uid 10001 --gid 10001 --no-create-home \\",
            "        --home-dir /tmp --shell /usr/sbin/nologin app \\",
            "    && chown -R 10001:10001 /app",
            "ENV HOME=/tmp \\",
            "    XDG_CONFIG_HOME=/tmp/.config \\",
            "    XDG_CACHE_HOME=/tmp/.cache",
            "USER 10001:10001",
        ],
    },
    {
        "id": "debug-merged-apt-install",
        "reason": "the earlier debug image installed the packages and the wheel in one layer after the source copy",
        "file": "debug.Dockerfile",
        "old": [
            "WORKDIR /app",
            "COPY . /app",
            "RUN apt-get update \\",
            "    && apt-get install -y --no-install-recommends <PKGS> \\",
            "    && uv pip install --system --no-cache --break-system-packages .<EXTRAS> \\",
            "    && rm -rf /var/lib/apt/lists/*",
        ],
        "new": [
            "RUN apt-get update \\",
            "    && apt-get install -y --no-install-recommends <PKGS> \\",
            "    && apt-get clean \\",
            "    && rm -rf /var/lib/apt/lists/*",
            "WORKDIR /app",
            "COPY . /app",
            INSTALL,
        ],
    },
    {
        "id": "compose-hardening",
        "reason": "the earlier compose file carried none of the container hardening the render declares",
        "file": "mcp.compose.yml",
        "old": ["  <DIST>-mcp:"],
        "new": ["  <DIST>-mcp:", *HARDENING],
    },
    {
        "id": "compose-fixed-image",
        "reason": "the earlier compose file named a fixed registry tag; the render takes an immutable image from the environment",
        "file": "mcp.compose.yml",
        "old": ["    image: knucklessg1/<ANY>"],
        "new": [IMAGE],
    },
    {
        "id": "compose-restart",
        "reason": "the earlier compose file restarted unless stopped; the render restarts always",
        "file": "mcp.compose.yml",
        "old": ["    restart: unless-stopped"],
        "new": ["    restart: always"],
    },
    {
        "id": "compose-image-variable-without-kind",
        "reason": "the earlier compose file named the image variable after the connector only; the render adds the image kind",
        "file": "mcp.compose.yml",
        "old": ["    image: ${<DISTVAR>_IMAGE:?set-<DISTVAR>_IMAGE-to-image@sha256-digest}"],
        "new": [IMAGE],
    },
    {
        "id": "compose-image-default",
        "reason": "the earlier compose file defaulted the image to a fixed registry tag; the render requires an immutable image",
        "file": "mcp.compose.yml",
        "old": ["    image: ${<DISTVAR>_MCP_IMAGE:-<ANY>}"],
        "new": [IMAGE],
    },
    {
        "id": "compose-image-default-quoted",
        "reason": "the earlier compose file defaulted the image to a placeholder digest; the render requires an immutable image",
        "file": "mcp.compose.yml",
        "old": ['    image: "${<DISTVAR>_MCP_IMAGE:-<ANY>}"'],
        "new": [IMAGE],
    },
    {
        "id": "compose-env-example-file",
        "reason": "the earlier compose file also loaded the committed example environment file; the render loads only ../.env",
        "file": "mcp.compose.yml",
        "old": ["      - path: ../.env.example", "        required: true"],
        "new": [],
    },
    {
        "id": "verbose-install",
        "reason": "the earlier debug image installed in verbose mode; the render does not",
        "file": "debug.Dockerfile",
        "old": ["RUN uv pip install --system --verbose --no-cache --break-system-packages .<EXTRAS>"],
        "new": [INSTALL],
    },
    {
        "id": "compose-container-name",
        "reason": "the earlier compose file left the container and host name to the engine; the render names both",
        "file": "mcp.compose.yml",
        "old": [IMAGE, "    restart: always"],
        "new": [IMAGE, "    container_name: <DIST>-mcp", "    hostname: <DIST>-mcp", "    restart: always"],
    },
    {
        "file": "mcp.compose.yml",
        "id": "compose-image-shared-variable-quoted",
        "new": ["    image: ${<DISTVAR>_MCP_IMAGE:?set-<DISTVAR>_MCP_IMAGE-to-image@sha256-digest}"],
        "old": ['    image: "${MCP_IMAGE:?set-MCP_IMAGE-to-image@sha256-digest}"'],
        "reason": "the earlier compose file took the image from one shared MCP_IMAGE variable; the render names the variable after the connector and image kind",
    },
    {
        "file": "mcp.compose.yml",
        "id": "compose-env-file",
        "new": ["    restart: always", "    env_file:", "      - ../.env", "    environment:"],
        "old": ["    restart: always", "    environment:"],
        "reason": "the earlier compose file read no environment file; the render reads ../.env",
    },
    {
        "file": "mcp.compose.yml",
        "id": "compose-env-file-after-volumes",
        "new": ["        read_only: true", "    env_file:", "      - ../.env", "    environment:"],
        "old": ["        read_only: true", "    environment:"],
        "reason": "the earlier compose file read no environment file; the render reads ../.env after the mounted volumes",
    },
    {
        "file": "debug.Dockerfile",
        "id": "debug-host-default",
        "new": ["ARG HOST=<HOST>"],
        "old": ["ARG HOST=0.0.0.0"],
        "reason": "the earlier debug image bound all interfaces by default; the render binds the host the runtime image binds",
    },
]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=env)


def _extract(repo: Path, dest: Path) -> bool:
    archive = _git(repo, "archive", "origin/main")
    if archive.returncode:
        return False
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
    return True


def repo_paths(fleet: Path, names: Sequence[str] | None = None) -> list[Path]:
    """The checkouts of the driver's connector set (workspace ``agents`` group, active on GitHub), sorted by name.

    A directory under ``fleet`` that is not in that set (a retired or archived clone) is never scanned, and a
    connector in the set without a checkout is reported on stderr, not dropped silently.
    """
    wanted = sorted(connector_repos() if names is None else names)
    paths = [fleet / name for name in wanted if (fleet / name / ".git").exists()]
    for name in wanted:
        if not (fleet / name / ".git").exists():
            print(f"connector_central_generations: no checkout of {name} under {fleet}", file=sys.stderr)
    return paths


def scan(fleet: Path) -> dict[str, dict[str, Any]]:
    """Per repo: the single-stage Dockerfile fingerprint, stub fingerprints and the raw (committed, render) pairs."""
    out: dict[str, dict[str, Any]] = {}
    for repo in repo_paths(fleet):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            if not _extract(repo, root) or not (root / "docker" / "Dockerfile").is_file():
                continue
            ctx = make_ctx(root)
            if ctx is None or "version" not in ctx.pyproject().get("project", {}):
                continue
            # the pass is integrated: pl.o sees the pyproject the rules before it left (l4 drops extras, n adds versions)
            for rid in rule_order():
                if rid == "pl.o":
                    break
                try:
                    RULES[rid](ctx)
                except Exception:  # noqa: BLE001 - a crashing earlier rule leaves the files as they were
                    break
            if "version" not in ctx.pyproject().get("project", {}):
                continue
            info: dict[str, Any] = {"stubs": {}, "pairs": {}, "form": None}
            dist = ctx.dist
            current = ctx.read("docker/Dockerfile")
            if "runtime-base" not in {n for n, _ in P._stages(current)}:
                info["form"] = gen.digest(gen.dockerfile_form(current, dist))
            for name, markers in STUBS.items():
                if ctx.exists(f"docker/{name}"):
                    lines = gen.loose_lines(ctx.read(f"docker/{name}"))
                    if len(lines) <= STUB_MAX_LINES and any(m in {ln.strip() for ln in lines} for m in markers):
                        info["stubs"][name] = gen.digest("\n".join(lines) + "\n")
            try:
                table = P.committed_table(ctx, ctx.pyproject())
                port = str(table.get("port", 8000))
                tmp = root / "_render"
                tmp.mkdir()
                shutil.copy(root / "pyproject.toml", tmp / "pyproject.toml")
                body = "".join(f"{k} = {P._toml_scalar(v)}\n" for k, v in table.items())
                if table:
                    (tmp / "pyproject.toml").write_text(
                        (root / "pyproject.toml").read_text().rstrip("\n") + f"\n\n[tool.pipelines.container]\n{body}"
                    )
                rendered = container.render(tmp)
                for name, new in rendered.items():
                    if ctx.exists(f"docker/{name}"):
                        pair = P.container_pair(ctx, name, new, dist, port, rewrite=False)
                        if pair is not None:
                            info["pairs"][name] = (pair[0], pair[1], dist, port)
            except (P._Unmatched, CannotRun, KeyError, tomllib.TOMLDecodeError):
                pass
            out[repo.name] = info
    return out


def _hunks(a: str, b: str) -> list[tuple[list[str], list[str]]]:
    al, bl = a.splitlines(), b.splitlines()
    result = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, al, bl, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        ctx_before = al[max(i1 - 1, 0) : i1] if i1 == i2 and i1 else []
        result.append((ctx_before + al[i1:i2], ctx_before + bl[j1:j2]))
    return result


def _abstract(lines: list[str], dist: str, port: str) -> list[str]:
    var = gen.placeholders(dist, port)
    out = []
    for line in lines:
        for key in ("<DIST>", "<DISTVAR>"):
            line = line.replace(var[key], key)
        line = line.replace(f"{port}:{port}", "<PORT>:<PORT>").replace(f"localhost:{port}", "localhost:<PORT>")
        if "uv pip install" in line:
            line = re.sub(r'\.(\[[^\]]*\])?("?)$', rf".{gen.EXTRAS}\2", line)
        out.append(line)
    return out


def candidates(scanned: dict[str, dict[str, Any]], min_repos: int) -> list[tuple[int, str, str, list[str], list[str]]]:
    seen: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for repo, info in scanned.items():
        for name, (a, b, dist, port) in info["pairs"].items():
            if name == "Dockerfile":
                continue
            for old, new in _hunks(a, b):
                key = (name, "\n".join(_abstract(old, dist, port)), "\n".join(_abstract(new, dist, port)))
                seen[key].add(repo)
    rows = [
        (len(r), gen.digest("\0".join(k))[:10], k[0], k[1].split("\n"), k[2].split("\n") if k[2] else [])
        for k, r in seen.items()
        if len(r) >= min_repos
    ]
    return sorted(rows, key=lambda x: (-x[0], x[1]))


def recorded_ids(path: Path) -> set[str]:
    """The rewrite ids already recorded in ``path``: a generation stays recorded while any repository still carries it.

    Migrated repositories stop carrying an older block, so counting them again would drop the entry that the
    remaining, not yet migrated repositories still need. Such an entry is marked ``retained``; a new entry still needs
    ``--min-repos`` repositories.
    """
    try:
        return {str(r["id"]) for r in json.loads(path.read_text(encoding="utf-8")).get("rewrites", [])}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def build(
    scanned: dict[str, dict[str, Any]], min_repos: int, recorded: frozenset[str] | set[str] = frozenset()
) -> dict[str, Any]:
    forms: dict[str, set[str]] = defaultdict(set)
    stubs: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for repo, info in scanned.items():
        if info["form"]:
            forms[info["form"]].add(repo)
        for name, h in info["stubs"].items():
            stubs[name][h].add(repo)
    rewrites = [
        {
            "id": cid,
            "reason": ACCEPTED[cid],
            "file": name,
            "old": old,
            "new": new,
            "repos": count,
            **({"retained": True} if count < min_repos else {}),
        }
        for count, cid, name, old, new in candidates(scanned, 1)
        if cid in ACCEPTED and (count >= min_repos or cid in recorded)
    ]
    for entry in MANUAL:
        seen = 0
        for info in scanned.values():
            if entry["file"] in info["pairs"]:
                text, _, dist, port = info["pairs"][entry["file"]]
                counts: dict[int, int] = {}
                gen.rewrite_entries([*rewrites, entry], entry["file"], text, dist, port, counts)
                seen += bool(counts.get(len(rewrites)))
        if seen >= min_repos:
            rewrites.append({**entry, "repos": seen})
        elif seen and entry["id"] in recorded:
            rewrites.append({**entry, "repos": seen, "retained": True})
    return {
        "dockerfile_forms": {h: len(r) for h, r in sorted(forms.items()) if len(r) >= min_repos},
        "stubs": {
            name: {h: len(r) for h, r in sorted(by.items()) if len(r) >= min_repos}
            for name, by in sorted(stubs.items())
        },
        "rewrites": rewrites,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fleet", type=Path, default=DEFAULT_FLEET)
    ap.add_argument("--out", type=Path, default=gen.GENERATIONS_PATH)
    ap.add_argument("--min-repos", type=int, default=3)
    ap.add_argument("--candidates", action="store_true", help="print differing blocks seen in several repositories")
    args = ap.parse_args(argv)
    scanned = scan(args.fleet)
    if args.candidates:
        for count, cid, name, old, new in candidates(scanned, args.min_repos):
            print(f"== {cid} {count} {name}\n-" + "\n-".join(old) + "\n+" + "\n+".join(new))
        return 0
    table = build(scanned, args.min_repos, recorded_ids(args.out))
    args.out.write_text(json.dumps(table, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"{len(table['dockerfile_forms'])} Dockerfile form(s); "
        f"{sum(len(v) for v in table['stubs'].values())} stub(s); {len(table['rewrites'])} rewrite(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
