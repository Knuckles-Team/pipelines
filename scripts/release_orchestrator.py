#!/usr/bin/env python3
"""Dependency-ordered digest release CLI: ``validate``, ``plan``, ``publish``,
``verify-consumers``, ``check-reproducible-build``. See ``scripts/release/``."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_cli = import_module("scripts.release.cli")

main = _cli.main

if __name__ == "__main__":
    raise SystemExit(main())
