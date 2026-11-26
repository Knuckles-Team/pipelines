"""Hydration journey gate: a graph-loaded workflow through the harness, then ingest and readback (PIPE-GATES-R019).

``python3 -I hydration_journey.py --workflow ID --harness-command "CMD ARGS"`` runs
the harness through its published command on the workflow the graph holds. The
harness prints one JSON receipt: ``workflow_revision``, ``plan_digest``, the run
``output`` text, the ``ingest_request`` the run produced and the ``expected``
results (``id``, ``content_digest``, ``revision``) it claims to have written.
The gate then calls ``SourceIngest`` and ``VerifyIngestReadback`` through the
arbora endpoint of ``PIPELINES_ARBORA_ENDPOINT`` and fails when the readback is
not matched or the digest the engine bound differs from the digest of the run
output. The gate adds no orchestrator: it runs the command, forwards the
request and compares digests.

Exit 0 the readback matches; 1 it differs; 2 the journey could not run (no
harness, no endpoint, an operation the endpoint does not serve).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipelines_hooks.gate_runner import evidence_digest  # noqa: E402
from pipelines_hooks.verdict_publish import post_operation  # noqa: E402

INGEST_OPERATION = "eg.ingest.SourceIngest"
READBACK_OPERATION = "eg.ingest.VerifyIngestReadback"
HARNESS_TIMEOUT_SECONDS = 1800


class CannotRun(RuntimeError):
    """The journey could not produce a trustworthy verdict (exit 2)."""


@dataclass(frozen=True)
class HarnessReceipt:
    """What the harness reports for one run of the workflow."""

    workflow_revision: int
    plan_digest: str
    output: str
    ingest_request: Mapping[str, Any]
    expected: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class Verdict:
    """The journey's outcome: ``findings`` is empty exactly when the readback digest matches."""

    findings: tuple[str, ...]

    @property
    def status(self) -> int:
        return 1 if self.findings else 0


Harness = Callable[[str], HarnessReceipt]
Call = Callable[[str, Mapping[str, Any]], Any]


def run_harness(command: str, workflow: str) -> HarnessReceipt:
    """Run the published harness command on one workflow and parse its JSON receipt."""
    args = [*shlex.split(command), workflow]
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False, timeout=HARNESS_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CannotRun(f"the harness could not run: {exc}") from None
    if result.returncode != 0:
        raise CannotRun(f"the harness exited {result.returncode}: {result.stderr.strip()[:300]}")
    try:
        data = json.loads(result.stdout)
        return HarnessReceipt(
            workflow_revision=int(data["workflow_revision"]),
            plan_digest=str(data["plan_digest"]),
            output=str(data["output"]),
            ingest_request=dict(data["ingest_request"]),
            expected=tuple(dict(item) for item in data["expected"]),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise CannotRun(f"the harness printed no usable receipt: {exc}") from None


def run_journey(workflow: str, harness: Harness, call: Call) -> Verdict:
    """The harness run, then ``SourceIngest``, then ``VerifyIngestReadback``, then the digest comparison."""
    receipt = harness(workflow)
    run_output_digest = evidence_digest(receipt.output)
    try:
        written = call(INGEST_OPERATION, {"request": dict(receipt.ingest_request)})
        write_digest = str(written["write_receipt_digest"])
        readback = call(
            READBACK_OPERATION,
            {
                "request": {
                    "write_receipt_digest": write_digest,
                    "expected_graph_revision": int(written.get("graph_revision", 0)),
                    "results": [dict(item) for item in receipt.expected],
                    "hydration_run": {
                        "workflow_id": workflow,
                        "workflow_revision": receipt.workflow_revision,
                        "plan_digest": receipt.plan_digest,
                        "run_output_digest": run_output_digest,
                    },
                }
            },
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise CannotRun(f"the engine could not answer the journey: {exc}") from None
    findings = []
    if readback.get("verdict") != "matched":
        findings.append(f"readback verdict is {readback.get('verdict')!r}, not 'matched'")
    bound = (readback.get("hydration_run") or {}).get("run_output_digest")
    if bound != run_output_digest:
        findings.append(f"readback digest {bound!r} differs from the run output digest {run_output_digest}")
    return Verdict(tuple(findings))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="hydration-journey", description=__doc__)
    parser.add_argument("--workflow", required=True, help="the graph-loaded workflow the harness runs")
    parser.add_argument(
        "--harness-command", required=True, help="the published harness command; the workflow ID is appended"
    )
    args = parser.parse_args(argv)
    endpoint = (os.environ.get("PIPELINES_ARBORA_ENDPOINT") or "").strip()
    token = (os.environ.get("PIPELINES_ARBORA_TOKEN") or "").strip()
    try:
        if not endpoint:
            raise CannotRun("no arbora endpoint is configured")
        verdict = run_journey(
            args.workflow,
            lambda workflow: run_harness(args.harness_command, workflow),
            lambda operation, params: post_operation(endpoint, token, operation, params),
        )
    except CannotRun as exc:
        print(f"hydration-journey: CANNOT RUN: {exc}", file=sys.stderr)
        return 2
    for finding in verdict.findings:
        print(f"hydration-journey: FAIL: {finding}")
    if not verdict.findings:
        print(f"hydration-journey: OK: readback of {args.workflow} matches the run output")
    return verdict.status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
