"""Publish the computed row and task states to the engine (PIPE-GATES-R004.3).

States come from the one generator (``specs/generator.py``) and the task
parser of ``specs/narrative.py``; nothing here derives a state. Each record
binds repository, revision, row or task ID, state and input digest. A
publish failure never changes the gate verdict, and with no endpoint the
publish is skipped and logged. The engine reads the records under
MEDULLA-SDLC-R005.7.
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pipelines_hooks.specs.narrative import TASK_RE
from pipelines_hooks.verdict_publish import post_operation

#: The served operation that records computed states.
STATE_OPERATION = "source.spec_state"
#: Records per call, so a large repository is a bounded number of requests.
BATCH_SIZE = 200
_TASK_ID_RE = re.compile(r"^- \[[ xX]\] (T\d{3,})")


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def task_states(tasks_text: str) -> list[tuple[str, str, str]]:
    """``(task id, row id, state)`` for each task line; a ticked box is ``done``, otherwise ``open``."""
    found = []
    for line in tasks_text.splitlines():
        match = TASK_RE.match(line)
        if match is not None:
            task_id = _TASK_ID_RE.search(line)
            if task_id is not None:
                found.append((task_id.group(1), match.group(1), "done" if line[3] in "xX" else "open"))
    return found


def collect_states(
    generated: Mapping[Path, Mapping[str, Any]], *, repository: str, revision: str
) -> list[dict[str, str]]:
    """One record per row and per task of every computed spec document."""
    records: list[dict[str, str]] = []
    for status_path, document in sorted(generated.items(), key=lambda item: str(item[0])):
        spec_dir = status_path.parent
        requirements = spec_dir / "requirements.md"
        row_input = _digest(requirements.read_text(encoding="utf-8")) if requirements.is_file() else _digest("")
        base = {"repository": repository, "revision": revision}
        for row in document.get("requirements", ()):
            records.append(
                {
                    **base,
                    "kind": "row",
                    "id": str(row["id"]),
                    "state": str(row["delivery_state"]),
                    "input_digest": row_input,
                }
            )
        tasks = spec_dir / "tasks.md"
        if tasks.is_file():
            text = tasks.read_text(encoding="utf-8")
            for task_id, row_id, state in task_states(text):
                records.append(
                    {
                        **base,
                        "kind": "task",
                        "id": f"{document.get('spec_id', spec_dir.name)}/{task_id}",
                        "row": row_id,
                        "state": state,
                        "input_digest": _digest(text),
                    }
                )
    return records


def publish_states(states: Sequence[Mapping[str, str]], endpoint: str, token: str) -> bool:
    """Post the records; ``False`` (logged) when skipped or failed. Never raises."""
    if not endpoint:
        print("states-publish: skipped (no arbora endpoint configured)", file=sys.stderr)
        return False
    try:
        for start in range(0, len(states), BATCH_SIZE):
            post_operation(endpoint, token, STATE_OPERATION, {"records": list(states[start : start + BATCH_SIZE])})
    except OSError as exc:
        print(f"states-publish: could not publish the states: {exc}", file=sys.stderr)
        return False
    return True
