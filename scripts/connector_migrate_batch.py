#!/usr/bin/env python3
"""Batch driver for the connector manifest-cut migration (PIPE-GATES-R016.16).

Per connector: worktree -> sync -> migrate -> commit -> verify -> push -> PR -> wait for ``gates`` -> squash-merge.
At most ``--jobs`` (default 4) repos are in flight. Outcomes go to a JSON ledger the driver resumes from; a failure stops
that repo only and lands in ``review.json`` with the step and an output tail. No retries, except one infra re-run of a
cancelled/infra-failed ``gates`` run (stated in the ledger as ``infra_rerun``) and one re-stage after a formatter hook.
``--dry-run`` stops after verify (no push). ``--sdk-path`` installs a local SDK checkout instead of PyPI (pre-release use only).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIPELINES = HERE.parent
FIXED_MESSAGE = "chore: cut the connector manifest files; declare data sources in code (SDK 0.4.1)"
REBUMP_MESSAGE = "chore: require agent-connector-sdk>=0.4.1"
TRAILER = "Spec: SDK-CONNECTOR-CONTROL-R075\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
STEPS = ("worktree", "sync", "migrate", "commit", "verify", "push", "pr", "gates", "merge")
lock = threading.Lock()


def stage(wt: Path, paths: list[str], step: str) -> None:
    """Stage exactly the reported allowlist: additions by path, deletions with ``git rm --cached --ignore-unmatch`` (idempotent)."""
    present = [p for p in paths if (wt / p).exists()]
    gone = [p for p in paths if not (wt / p).exists()]
    if present:
        sh(step, ["git", "add", "--", *present], wt)
    if gone:
        sh(step, ["git", "rm", "--cached", "--ignore-unmatch", "-q", "--", *gone], wt)


def apply_repo_patch(patch: Path, wt: Path, paths: list[str], led: Ledger, repo: str) -> list[str]:
    """Apply a reviewed one-off patch for this repo (not a codemod rule); returns the extended path list."""
    if not patch.is_file():
        return paths
    sh("patch", ["git", "apply", str(patch)], wt)
    touched = re.findall(r"(?m)^\+\+\+ b/(\S+)", patch.read_text(encoding="utf-8"))
    led.record(repo, repo_patch=patch.name, repo_patch_files=touched)
    return sorted(set(paths) | set(touched))


def hook(*args: str) -> list[str]:
    return ["uv", "run", "--project", str(PIPELINES), "--frozen", "pipelines-hook", *args]


class StepFailed(Exception):
    def __init__(self, step: str, output: str) -> None:
        super().__init__(step)
        self.step, self.output = step, output[-2000:]


def sh(
    step: str, cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, ok: tuple[int, ...] = (0,)
) -> str:
    base = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    r = subprocess.run(cmd, cwd=cwd, env={**base, **(env or {})}, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode not in ok:
        raise StepFailed(step, f"$ {' '.join(cmd)}\n{out}")
    return out


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, dict] = json.loads(path.read_text()) if path.exists() else {}

    def record(self, repo: str, **kw: object) -> None:
        with lock:
            self.data.setdefault(repo, {}).update(kw)
            self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n")

    def done(self, repo: str) -> bool:
        return self.data.get(repo, {}).get("status") in ("merged", "dry-run-verified")


def workflow_sync_args(wt: Path) -> list[str] | None:
    """The ``sync-args:`` the repo's own PR gate passes to ``uv sync`` (``connector-pr.yml``), if any."""
    wf = wt / ".github/workflows/connector-pr.yml"
    if not wf.is_file():
        return None
    m = re.search(r"(?m)^\s*sync-args:\s*(.+?)\s*$", wf.read_text(encoding="utf-8"))
    return m.group(1).split() if m else None


def sync(step: str, wt: Path, env: dict[str, str], led: Ledger, repo: str) -> None:
    """``uv sync --frozen`` with every extra; when that cannot build (CUDA extras), the PR gate's own extras (R016.25)."""
    try:
        sh(step, ["uv", "sync", "--frozen", "--all-extras", "--all-groups"], wt, env)
    except StepFailed:
        args = workflow_sync_args(wt)
        if not args:
            raise
        sh(step, ["uv", "sync", "--frozen", *args], wt, env)
        led.record(repo, sync_args=" ".join(args))


def migrate_repo(repo: str, a: argparse.Namespace, led: Ledger) -> None:
    src = a.fleet / repo
    kind = "sdk-rebump" if a.rebump else "manifest-cut"
    message = REBUMP_MESSAGE if a.rebump else FIXED_MESSAGE
    wt = a.worktrees / repo / kind
    branch = f"chore/{kind}"
    tmp = Path(a.tmpdir) / repo
    tmp.mkdir(parents=True, exist_ok=True)
    pc_home = Path(a.tmpdir).parent / "pc" / repo
    pc_home.mkdir(parents=True, exist_ok=True)
    # R016.25: one pre-commit cache per repo; the shared sqlite cache reports "database is locked" under concurrency.
    env = {"TMPDIR": str(tmp), "PRE_COMMIT_HOME": str(pc_home)}
    step = "worktree"
    try:
        sh(step, ["git", "fetch", "origin", "main"], src)
        if wt.exists() and led.data.get(repo, {}).get("status") == "failed":
            # R016.25: a re-run starts from clean origin/main, never from the half-migrated tree of the failed run.
            sh(step, ["git", "worktree", "remove", "--force", str(wt)], src)
            sh(step, ["git", "branch", "-D", branch], src, ok=(0, 1))
            led.record(repo, status="retry", rerun=True)
        if not wt.exists():
            wt.parent.mkdir(parents=True, exist_ok=True)
            sh(step, ["git", "worktree", "add", str(wt), "-b", branch, "origin/main"], src)
        step = "sync"
        venv = str(tmp / "venv")
        env["UV_PROJECT_ENVIRONMENT"] = venv
        sync(step, wt, env, led, repo)
        if a.sdk_path:
            sh(
                step,
                ["uv", "pip", "install", "--python", f"{venv}/bin/python", "--no-deps", "-e", str(a.sdk_path)],
                wt,
                env,
            )
        step = "migrate"
        report_path = tmp / "migrate.json"
        cmd = hook(
            "connector-ontology-map",
            "migrate",
            "--root",
            str(wt),
            "--eg-repo",
            str(a.eg_repo),
            "--out",
            str(report_path),
        )
        if a.rebump:
            cmd = [c for c in cmd if c not in ("--eg-repo", str(a.eg_repo))] + ["--rebump"]
        if a.sdk_path:
            cmd.append("--no-lock")
        sh(step, cmd, wt, {**env, "UV_PROJECT_ENVIRONMENT": str(a.pipelines_venv)}, ok=(0, 2))
        report = (
            json.loads(report_path.read_text())
            if report_path.exists()
            else {"review": [], "changed": [], "deleted": []}
        )
        led.record(repo, review=report["review"], changed=len(report["changed"]), deleted=len(report["deleted"]))
        blocking = [i for i in report["review"] if i["blocking"]]
        if blocking:
            raise StepFailed(step, json.dumps(blocking, indent=1))
        step = "commit"
        paths = sorted(set(report["changed"]) | set(report["deleted"]))
        if not a.rebump:
            paths = apply_repo_patch(a.patches / f"{repo}.patch", wt, paths, led, repo)
        stage(wt, paths, step)
        stat = sh(step, ["git", "diff", "--cached", "--shortstat"], wt).strip()
        led.record(repo, diffstat=stat)
        commit = ["git", "commit", "-m", message, "-m", TRAILER]
        try:
            sh(step, commit, wt, env)
        except StepFailed:
            # A formatter hook rewrote the staged files: re-stage the same allowlist once and commit again.
            stage(wt, paths, step)
            sh(step, commit, wt, env)
            led.record(repo, restaged_after_hook=True)
        step = "verify"
        # R016.25: the migrate step raised the SDK floor and lock; the venv synced before it still holds the old SDK.
        sync(step, wt, env, led, repo)
        py = f"{venv}/bin/python"
        v = sh(
            step,
            [py, str(HERE / "connector_verify.py"), str(wt)],
            wt,
            env,
        )
        led.record(repo, verify=json.loads([ln for ln in v.splitlines() if ln.startswith("{")][-1]))
        fleet_dir = tmp / "fleet"
        fleet_dir.mkdir(exist_ok=True)
        link = fleet_dir / repo
        if not link.exists():
            link.symlink_to(wt)
        g = sh(
            step,
            hook(
                "connector-ontology-map",
                "graph-check",
                "--fleet",
                str(fleet_dir),
                "--eg-repo",
                str(a.eg_repo),
                "--ref",
                "HEAD",
                "--warn",
            ),
            wt,
            {**env, "UV_PROJECT_ENVIRONMENT": str(a.pipelines_venv)},
        )
        led.record(repo, graph_check=g.strip().splitlines()[-12:])
        pkg = next(p.name for p in wt.iterdir() if (p / "connector_sources.py").exists())
        scope = sh(
            step,
            hook("pr-test-scope", "--base-ref", "origin/main", "--src-root", pkg, "--tests-root", "tests"),
            wt,
            {**env, "UV_PROJECT_ENVIRONMENT": str(a.pipelines_venv)},
        ).strip()
        led.record(
            repo,
            test_scope="FULL"
            if scope == "FULL"
            else ("NONE" if scope == "NONE" else f"{len(scope.splitlines())} files"),
        )
        if scope != "NONE":
            targets = ["tests"] if scope == "FULL" else scope.splitlines()
            # No `-p`: a connector test that parses sys.argv reads it as the server port flag.
            sh(step, [py, "-m", "pytest", "-q", "-x", *targets], wt, env)
        if a.dry_run:
            led.record(repo, status="dry-run-verified")
            return
        step = "push"
        sh(step, ["git", "push", "-u", "origin", branch], wt, env)
        step = "pr"
        url = (
            sh(
                step,
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    "main",
                    "--head",
                    branch,
                    "--title",
                    message,
                    "--body",
                    (
                        "SDK floor, patch bump and lock refresh only (pipelines `connector-ontology-map migrate --rebump`).\n\n"
                        if a.rebump
                        else "Mechanical manifest-cut migration (pipelines `connector-ontology-map migrate`).\n\n"
                    )
                    + "Spec: SDK-CONNECTOR-CONTROL-R075\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)",
                ],
                wt,
            )
            .strip()
            .splitlines()[-1]
        )
        led.record(repo, pr=url)
        step = "gates"
        wait_gates(repo, url, wt, led)
        step = "merge"
        slug = url.split("github.com/", 1)[1].split("/pull/")[0]
        # -R keeps gh from checking main out in the shared checkout, where main is already in use.
        sh(step, ["gh", "pr", "merge", url, "-R", slug, "--squash", "--delete-branch"], wt)
        led.record(repo, status="merged", merged_at=time.strftime("%FT%TZ", time.gmtime()))
    except StepFailed as exc:
        led.record(repo, status="failed", failed_step=exc.step, output_tail=exc.output)
    except Exception as exc:  # noqa: BLE001 - recorded, then this repo stops
        led.record(repo, status="failed", failed_step=step, output_tail=f"{type(exc).__name__}: {exc}")


def parse_checks(text: str) -> dict[str, str]:
    """``{check name: pass|fail|pending|cancel|skipping}`` from plain `gh pr checks` output (tab separated)."""
    out = {}
    for line in text.splitlines():
        cols = line.split("\t")
        if len(cols) >= 2 and re.search(r"gates", cols[0]):
            out[cols[0]] = cols[1].strip()
    return out


def wait_gates(repo: str, url: str, wt: Path, led: Ledger) -> None:
    """Wait for the ``gates`` check; one infra re-run is allowed for a cancelled run and is recorded."""
    reran = False
    for _ in range(120):
        out = sh("gates", ["gh", "pr", "checks", url], wt, ok=(0, 1, 8))
        checks = parse_checks(out)
        buckets = set(checks.values())
        if checks and buckets == {"pass"}:
            return
        if "cancel" in buckets and not reran:
            sh("gates", ["gh", "run", "rerun", "--failed"], wt, ok=(0, 1))
            reran = True
            led.record(repo, infra_rerun="gates run was cancelled; re-run once")
        elif "fail" in buckets or "cancel" in buckets:
            raise StepFailed("gates", out)
        time.sleep(30)
    raise StepFailed("gates", "timed out waiting for gates")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repos", nargs="*", help="connector repo names (default: the fleet list file)")
    ap.add_argument("--fleet", type=Path, default=Path("/home/apps/workspace/agent-packages/agents"))
    ap.add_argument("--fleet-list", type=Path, default=None, help="file with one repo name per line")
    ap.add_argument("--eg-repo", type=Path, default=Path("/home/apps/workspace/agent-packages/epistemic-graph"))
    ap.add_argument(
        "--worktrees",
        type=Path,
        default=Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "repository-worktrees",
    )
    ap.add_argument("--ledger", type=Path, default=Path("/var/tmp/connector-migrate/ledger.json"))
    ap.add_argument("--review", type=Path, default=Path("/var/tmp/connector-migrate/review.json"))
    ap.add_argument("--tmpdir", default="/var/tmp/connector-migrate/tmp")
    ap.add_argument("--pipelines-venv", type=Path, default=Path("/var/tmp/cm/venv"))
    ap.add_argument(
        "--patches", type=Path, default=HERE / "connector_migrate_patches", help="reviewed per-repo <repo>.patch files"
    )
    ap.add_argument("--rebump", action="store_true", help="already-migrated repos: SDK floor, patch bump and lock only")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true", help="migrate and verify only; no push")
    ap.add_argument("--sdk-path", type=Path, default=None, help="install this SDK checkout instead of PyPI (dry-run)")
    a = ap.parse_args()
    a.jobs = min(a.jobs, 4)
    repos = a.repos or [ln.strip() for ln in a.fleet_list.read_text().splitlines() if ln.strip()]
    a.ledger.parent.mkdir(parents=True, exist_ok=True)
    led = Ledger(a.ledger)
    todo = [r for r in repos if not led.done(r)]
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        list(pool.map(lambda r: migrate_repo(r, a, led), todo))
    failed = {
        r: {k: v for k, v in d.items() if k in ("failed_step", "output_tail", "review")}
        for r, d in led.data.items()
        if d.get("status") == "failed"
    }
    warnings = {
        r: [i for i in d.get("review", []) if not i["blocking"]] for r, d in led.data.items() if d.get("review")
    }
    a.review.write_text(json.dumps({"failed": failed, "non_blocking": warnings}, indent=1, sort_keys=True) + "\n")
    print(json.dumps({r: d.get("status") for r, d in led.data.items()}, indent=1, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
