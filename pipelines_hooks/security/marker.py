"""The one inline exemption convention shared by every credential scanner.

A line may carry ``# sanitizer:ignore - <reason>``: a reviewed synthetic
fixture marked once, next to the literal it exempts, WITH a non-empty reason
after a ``-``/``—``/``:`` separator. A bare marker is not accepted -- the
convention is "document why", not "silence the check" -- and there is no
file-level, path-level or value-list exemption anywhere.
"""

from __future__ import annotations

import re

SANITIZER_IGNORE_RE = re.compile(r"#\s*sanitizer:ignore\s*[-—:]\s*\S")


def is_exempt(line: str) -> bool:
    """Whether a line carries the justified inline exemption marker."""
    return SANITIZER_IGNORE_RE.search(line) is not None
