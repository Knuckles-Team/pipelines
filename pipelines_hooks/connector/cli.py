"""``pipelines-connector {version,render,generate} ...``: the connector build commands (not hooks)."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence

from pipelines_hooks.core.errors import CannotRun

COMMANDS = {
    "version": "pipelines_hooks.connector.version",
    "render": "pipelines_hooks.connector.container",
    "generate": "pipelines_hooks.connector.generate",
}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in COMMANDS:
        print(f"usage: pipelines-connector {{{','.join(COMMANDS)}}} [args]", file=sys.stderr)
        return 2
    try:
        return int(importlib.import_module(COMMANDS[args[0]]).main(args[1:]))
    except CannotRun as exc:
        print(f"pipelines-connector {args[0]}: CANNOT RUN: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
