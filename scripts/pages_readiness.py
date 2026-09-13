#!/usr/bin/env python3
"""Build and verify the canonical Pages Markdown delivery contract."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_readiness = import_module("scripts.readiness")

CHECKER_VERSION = _readiness.CHECKER_VERSION
MAX_GENERATED_FILE_BYTES = _readiness.MAX_GENERATED_FILE_BYTES
MIRROR_CONTRACT = _readiness.MIRROR_CONTRACT
ReadinessTckError = _readiness.ReadinessTckError
SCHEMA_ID = _readiness.SCHEMA_ID
SCHEMA_VERSION = _readiness.SCHEMA_VERSION
build = _readiness.build
main = _readiness.main
mkdocs_docs_dir = _readiness.mkdocs_docs_dir
site_output_path = _readiness.site_output_path
validate_content_source = _readiness.validate_content_source

__all__ = [
    "CHECKER_VERSION",
    "MAX_GENERATED_FILE_BYTES",
    "MIRROR_CONTRACT",
    "ReadinessTckError",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "build",
    "main",
    "mkdocs_docs_dir",
    "site_output_path",
    "validate_content_source",
]

if __name__ == "__main__":
    raise SystemExit(main())
