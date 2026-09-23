"""Command-line entrypoint: build/check the shared corpus, emit/check-repo a slice."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from skill_graph.corpus import build_graph, generate
from skill_graph.model import REPOS
from skill_graph.render_components import render_components_eg
from skill_graph.render_components_au import render_components_au
from skill_graph.render_repo import render_repo_reference_md

_COMPONENT_RENDERERS = {
    "epistemic-graph": lambda corpus, repo_root: render_components_eg(corpus),
    "agent-utilities": lambda corpus, repo_root: render_components_au(repo_root),
}


def _write_or_check(mode: str, files: dict[str, str], label: str) -> int:
    if mode.startswith("emit") or mode == "build":
        for destination_str, content in files.items():
            destination = Path(destination_str)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        print(f"{label}: wrote {len(files)} file(s)")
        return 0
    mismatches = []
    for destination_str, content in files.items():
        destination = Path(destination_str)
        try:
            actual = destination.read_text(encoding="utf-8")
        except OSError:
            mismatches.append(f"missing: {destination}")
            continue
        if actual != content:
            mismatches.append(f"stale: {destination}")
    if mismatches:
        print(f"{label}: out of sync with source registries:", file=sys.stderr)
        for mismatch in mismatches:
            print(f"  - {mismatch}", file=sys.stderr)
        return 1
    print(f"{label}: check complete")
    return 0


def _build_parser(default_workspace: Path, default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("build", "check", "emit-repo", "check-repo", "emit-components", "check-components"),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=default_workspace,
        help=(
            "path to the agent-packages directory containing every repo in REPOS "
            f"(default: the sibling checkout at {default_workspace}, this "
            "workspace's own layout -- a standalone clone of just `pipelines`, or "
            "of a single downstream repo with no sibling checkouts, skips this "
            "gate rather than failing it)"
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help="pipelines repository root (where pages/ lives) -- build/check only",
    )
    parser.add_argument(
        "--slug",
        choices=tuple(REPOS),
        help="repo to project a man-page reference for -- emit-repo/check-repo only",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="destination file inside that repo -- emit-repo/check-repo only",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="destination docs/ dir inside that repo -- emit-components/check-components only",
    )
    parser.add_argument(
        "--required",
        action="store_true",
        help="fail instead of skipping when --workspace does not exist",
    )
    return parser


def _run_repo_mode(args: argparse.Namespace) -> int:
    corpus = build_graph(args.workspace.resolve())
    content = render_repo_reference_md(corpus, args.slug)
    return _write_or_check(args.mode, {str(args.out): content}, f"skill_graph[{args.slug}]")


def _no_component_registry(corpus: Any, repo_root: Path) -> dict[str, str]:
    return {}


def _run_components_mode(args: argparse.Namespace) -> int:
    renderer = _COMPONENT_RENDERERS.get(args.slug, _no_component_registry)
    corpus = build_graph(args.workspace.resolve())
    repo_root = args.workspace.resolve() / REPOS[args.slug][0]
    files = renderer(corpus, repo_root)
    return _write_or_check(
        args.mode,
        {str(args.out_dir / k): v for k, v in files.items()},
        f"skill_graph[components:{args.slug}]",
    )


def _run_pages_mode(args: argparse.Namespace) -> int:
    files = generate(args.workspace.resolve())
    return _write_or_check(args.mode, {str(args.root / k): v for k, v in files.items()}, "skill_graph")


# mode -> (required arg names beyond --workspace, runner)
_MODE_TABLE = {
    "emit-repo": (("slug", "out"), _run_repo_mode),
    "check-repo": (("slug", "out"), _run_repo_mode),
    "emit-components": (("slug", "out_dir"), _run_components_mode),
    "check-components": (("slug", "out_dir"), _run_components_mode),
    "build": ((), _run_pages_mode),
    "check": ((), _run_pages_mode),
}


def _missing_required_args(args: argparse.Namespace, required: tuple[str, ...]) -> bool:
    return any(getattr(args, name) is None for name in required)


def _workspace_skip(args: argparse.Namespace) -> int | None:
    """None means proceed; an int means return it immediately."""
    if args.workspace.is_dir():
        return None
    if args.required:
        print(f"skill_graph: CANNOT RUN: {args.workspace} does not exist", file=sys.stderr)
        return 2
    print(f"skill_graph: {args.mode} skipped (no sibling checkout at {args.workspace})")
    return 0


def main(argv: list[str] | None = None) -> int:
    default_workspace = Path(__file__).resolve().parents[3] / "agent-packages"
    default_root = Path(__file__).resolve().parents[2]
    parser = _build_parser(default_workspace, default_root)
    args = parser.parse_args(argv)
    required, runner = _MODE_TABLE[args.mode]
    if _missing_required_args(args, required):
        parser.error(f"{args.mode} requires --{' and --'.join(n.replace('_', '-') for n in required)}")
    skip = _workspace_skip(args)
    if skip is not None:
        return skip
    return runner(args)
