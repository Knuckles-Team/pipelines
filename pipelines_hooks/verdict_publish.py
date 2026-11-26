"""Publish a gate verdict to the engine over plain HTTP through arbora.

The arbora endpoint and token come from the CI environment. Without an
endpoint the publish is skipped and logged. A publish failure never changes
a verdict: the gate result is decided before this module is called and no
error leaves it. The transport is ``urllib.request``; no ecosystem package
is imported. The same helper serves the state publisher and the
``states-agree`` check.
"""

from __future__ import annotations

import http.client
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pipelines_hooks.core.settings import setting

#: The served operation that records one gate verdict (MEDULLA-SCM-R008).
VERDICT_OPERATION = "source.gate_verdict"
#: The default network timeout of one publish, in seconds.
TIMEOUT_SECONDS = 10.0


class PublishableVerdict(Protocol):
    """The fields of a gate verdict this module reads (``GateVerdict``)."""

    @property
    def gate(self) -> str: ...

    @property
    def status(self) -> int: ...

    @property
    def evidence_digest(self) -> str: ...

    @property
    def seconds(self) -> float: ...


@dataclass(frozen=True)
class ArboraTarget:
    """Where records go: the API base URL and the bearer token."""

    endpoint: str
    token: str


def target_from_environment() -> ArboraTarget | None:
    """The configured target, or ``None`` when no endpoint is set."""
    endpoint = setting("PIPELINES_ARBORA_ENDPOINT").rstrip("/")
    if not endpoint:
        return None
    return ArboraTarget(endpoint=endpoint, token=setting("PIPELINES_ARBORA_TOKEN"))


def post_operation(
    endpoint: str, token: str, operation: str, params: Mapping[str, Any], *, timeout: float = TIMEOUT_SECONDS
) -> Any:
    """Call one served operation and return its result; raise ``OSError`` on any failure."""
    request = urllib.request.Request(  # noqa: S310 - the endpoint is operator configuration
        f"{endpoint.rstrip('/')}/ops/{operation}",
        data=json.dumps(params, sort_keys=True).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, http.client.HTTPException, ValueError, TimeoutError) as exc:
        raise OSError(f"{operation}: {exc}") from None
    if not isinstance(body, dict) or body.get("ok") is not True:
        raise OSError(f"{operation}: the endpoint refused the call")
    result = body.get("result")
    if isinstance(result, dict) and isinstance(result.get("value"), dict):
        return result["value"]
    return result


def verdict_record(
    verdict: PublishableVerdict, *, repository: str = "", revision: str = "", input_digest: str = ""
) -> dict[str, Any]:
    """The record of one verdict: gate id, input digest, verdict, evidence digest and duration."""
    return {
        "repository": repository,
        "revision": revision,
        "gate_id": verdict.gate,
        "input_digest": input_digest,
        "verdict": "pass" if verdict.status == 0 else "fail",
        "status": verdict.status,
        "evidence_digest": verdict.evidence_digest,
        "duration_ms": int(round(verdict.seconds * 1000)),
    }


def publish_verdict(
    verdict: PublishableVerdict,
    endpoint: str,
    token: str,
    *,
    repository: str = "",
    revision: str = "",
    input_digest: str = "",
) -> bool:
    """Post one verdict; ``False`` (logged) when it was skipped or failed. Never raises."""
    if not endpoint:
        print(f"verdict-publish: skipped {verdict.gate} (no arbora endpoint configured)", file=sys.stderr)
        return False
    record = verdict_record(verdict, repository=repository, revision=revision, input_digest=input_digest)
    try:
        post_operation(endpoint, token, VERDICT_OPERATION, record)
    except OSError as exc:
        print(f"verdict-publish: could not publish {verdict.gate}: {exc}", file=sys.stderr)
        return False
    return True
