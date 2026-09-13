"""Command-line interface for the Pages readiness contract."""

from __future__ import annotations

import argparse
import json

from .constants import CHECKER_VERSION, MIRROR_CONTRACT, SCHEMA_VERSION
from .delivery import build
from .errors import ReadinessTckError
from .mkdocs import validate_content_source


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "check", "tck"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--root", default=".")
        subparser.add_argument("--site", default="site")
        subparser.add_argument("--content-source", default="pages")
        subparser.add_argument("--readiness-input", default=None)
        subparser.add_argument("--schema", default=None)
        subparser.add_argument(
            "--readiness-manifest", default="agent-readiness-manifest.json"
        )
        subparser.add_argument(
            "--mirror-manifest", default="markdown-mirror-manifest.json"
        )
    validate = subparsers.add_parser("validate-content-source")
    validate.add_argument("--root", default=".")
    validate.add_argument("--content-source", default="pages")
    return parser


def _main_validate_content_source(args: argparse.Namespace) -> int:
    try:
        result = validate_content_source(args.root, args.content_source)
    except ReadinessTckError as exc:
        print(json.dumps({"ok": False, "error_code": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


def _main_build(args: argparse.Namespace) -> int:
    try:
        result = build(
            args.root,
            args.site,
            content_source=args.content_source,
            readiness_input=args.readiness_input or None,
            schema=args.schema or None,
            readiness_manifest=args.readiness_manifest,
            mirror_manifest=args.mirror_manifest,
            check=args.command in {"check", "tck"},
        )
    except ReadinessTckError as exc:
        result = {
            "ok": False,
            "checker_version": CHECKER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "mirror_contract": MIRROR_CONTRACT,
            "error_code": str(exc),
        }
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the requested build, read-only TCK, or content-source check."""

    args = _parser().parse_args(argv)
    if args.command == "validate-content-source":
        return _main_validate_content_source(args)
    return _main_build(args)
