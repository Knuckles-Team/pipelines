#!/usr/bin/env python3
"""Batch driver for the connector manifest-cut migration (PIPE-GATES-R016.16).

Per connector: worktree -> sync -> migrate -> commit -> verify -> push -> PR -> wait for ``gates`` -> rebase-merge.
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
import shutil
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
CENTRAL_MESSAGE = "chore: move the connector onto the central SDK and pipelines components (SDK 0.5.2)"
CENTRAL_TRAILER = (
    "Spec: none (mechanical central connector migration)\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
)
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
    sh("patch", ["git", "apply", "--recount", "--unidiff-zero", str(patch)], wt)
    body = patch.read_text(encoding="utf-8")
    touched = re.findall(r"(?m)^\+\+\+ b/(\S+)", body) + re.findall(r"(?m)^--- a/(\S+)\n\+\+\+ /dev/null", body)
    led.record(repo, repo_patch=patch.name, repo_patch_files=touched)
    return sorted(set(paths) | set(touched))


class NoOp(Exception):
    """The repo has nothing to migrate: the cut files are already absent on origin/main."""


def worktree_diff(wt: Path) -> str:
    return sh("commit", ["git", "diff"], wt)


def commit_all(
    wt: Path,
    paths: list[str],
    step: str,
    env: dict[str, str],
    led: Ledger,
    repo: str,
    message: str,
    trailer: str = TRAILER,
) -> None:
    """R016.29: stage the allowlist and commit; the commit hooks format the files.

    A formatter hook that rewrites files fails the commit; the allowlist is re-staged and the commit retried while each
    attempt changes something. A run that changes nothing is a real failure. A commit already present ahead of
    origin/main (an earlier attempt) is kept; with nothing to stage and nothing ahead, the repo is a no-op.
    """
    seen = ""
    for attempt in range(1, 5):
        stage(wt, paths, step)
        stat = sh(step, ["git", "diff", "--cached", "--shortstat"], wt).strip()
        if not stat:
            ahead = int(sh(step, ["git", "rev-list", "--count", "origin/main..HEAD"], wt).strip() or 0)
            if ahead:
                led.record(repo, already_committed=True)
                return
            raise NoOp(repo)
        led.record(repo, diffstat=stat)
        try:
            sh(step, ["git", "commit", "-m", message, "-m", trailer], wt, env)
            led.record(repo, commit_attempts=attempt)
            return
        except StepFailed as exc:
            now = worktree_diff(wt)
            if not now or now == seen:
                raise exc
            seen = now
    raise StepFailed(step, "formatter hooks kept changing the tree after 4 commit attempts")


def hook(*args: str) -> list[str]:
    return ["uv", "run", "--project", str(PIPELINES), "--frozen", "pipelines-hook", *args]


class StepFailed(Exception):
    def __init__(self, step: str, output: str) -> None:
        super().__init__(step)
        self.step, self.output, self.full = step, output[-2000:], output


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
    kind = "sdk-rebump" if a.rebump else ("central" if a.central else "manifest-cut")
    message = REBUMP_MESSAGE if a.rebump else (CENTRAL_MESSAGE if a.central else FIXED_MESSAGE)
    wt = a.worktrees / repo / kind
    branch = f"chore/{kind}"
    tmp = Path(a.tmpdir) / repo
    tmp.mkdir(parents=True, exist_ok=True)
    pc_home = Path(a.tmpdir).parent / "pc" / repo
    # A `rev: main` hook checkout is never updated after its first install: a cache of an earlier run runs stale hook code.
    shutil.rmtree(pc_home, ignore_errors=True)
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
        if a.sdk_path:  # after the central migrate the floor is 0.5.2; the lock cannot resolve it before PyPI has it
            sh(
                step,
                ["uv", "pip", "install", "--python", f"{venv}/bin/python", "--no-deps", "-e", str(a.sdk_path)],
                wt,
                env,
            )
        # R016.29: hooks that run `python` (check-cli-help, env-var-drift) must see the synced repo environment.
        env["PATH"] = f"{venv}/bin:{os.environ.get('PATH', '')}"
        env_file = wt / ".env"  # R016.29: an ignored, missing .env fails the compose-check hook of a fresh worktree
        if not env_file.exists() and sh(step, ["git", "check-ignore", ".env"], wt, ok=(0, 1)).strip():
            env_file.write_text("", encoding="utf-8")  # empty: .env.example values would leak into the tests
        step = "migrate"
        # Reviewed per-repo patches use the ``<repo>.pre.patch`` and ``<repo>.central-pre.patch`` names.
        pre_paths = apply_repo_patch(
            a.patches / f"{repo}.{'central-pre' if a.central else 'pre'}.patch", wt, [], led, repo
        )  # also central: a reviewed fix the pass needs first
        served_path = tmp / "served-tools.json"
        served_path.unlink(missing_ok=True)
        try:  # R016.27: the served tool names (the central pass does not read them)
            if a.central:
                raise IndexError
            out = sh(step, [f"{venv}/bin/python", str(HERE / "connector_served_tools.py"), str(wt)], wt, env)
            served_path.write_text(
                [ln for ln in out.splitlines() if ln.startswith("SERVED_TOOLS ")][-1].split(" ", 1)[1], encoding="utf-8"
            )
        except (StepFailed, IndexError):
            pass
        report_path = tmp / "migrate.json"
        report_path.unlink(missing_ok=True)  # a report of an earlier run must never stand in for this one
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
        if a.central:
            cmd = [c for c in cmd if c not in ("--eg-repo", str(a.eg_repo))] + [
                "--central",
                "--pipelines-root",
                str(PIPELINES),
            ]
            if a.sdk_path:
                cmd += ["--sdk-path", str(a.sdk_path)]
        elif a.rebump:
            cmd = [c for c in cmd if c not in ("--eg-repo", str(a.eg_repo))] + ["--rebump"]
        elif served_path.exists():
            cmd += ["--served-tools", str(served_path)]
        sdk_distribution = getattr(a, "sdk_distribution", None)
        if sdk_distribution:
            cmd += ["--sdk-distribution", sdk_distribution]
        if a.sdk_path and not a.central:
            cmd.append("--no-lock")
        sh(step, cmd, wt, {**env, "UV_PROJECT_ENVIRONMENT": str(a.pipelines_venv)}, ok=(0, 2))
        if not report_path.exists():  # R016.29: exit 0 or 2 without a report means the codemod never ran
            raise StepFailed(step, "migrate wrote no report")
        report = json.loads(report_path.read_text())
        led.record(repo, review=report["review"], changed=len(report["changed"]), deleted=len(report["deleted"]))
        blocking = [i for i in report["review"] if i["blocking"]]
        if blocking:
            raise StepFailed(step, json.dumps(blocking, indent=1))
        step = "commit"
        paths = sorted(set(report["changed"]) | set(report["deleted"]) | set(pre_paths))
        if not a.rebump and not a.central:
            paths = apply_repo_patch(a.patches / f"{repo}.patch", wt, paths, led, repo)
        try:
            commit_all(wt, paths, step, env, led, repo, message, CENTRAL_TRAILER if a.central else TRAILER)
        except NoOp:
            gone = sh(step, ["git", "ls-tree", "-r", "--name-only", "origin/main"], wt)
            if any(n.rsplit("/", 1)[-1] in ("connector_manifest.yml", "mcp_source_presets.json") for n in gone.split()):
                raise StepFailed(step, "nothing to commit but the cut files are still on origin/main") from None
            led.record(repo, status="merged", noop=True, merged_at=time.strftime("%FT%TZ", time.gmtime()))
            return
        step = "verify"
        # R016.25: the migrate step raised the SDK floor and lock; the venv synced before it still holds the old SDK.
        if not a.sdk_path:
            sync(step, wt, env, led, repo)
        py = f"{venv}/bin/python"
        v = sh(
            step,
            [py, str(HERE / "connector_verify.py"), str(wt)],
            wt,
            env,
        )
        led.record(repo, verify=json.loads([ln for ln in v.splitlines() if ln.startswith("{")][-1]))
        if a.central:
            central_verify(wt, py, env, led, repo, a)
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
        pkg = next(p.name for p in sorted(wt.iterdir()) if (p / "connector_sources.py").exists())
        scope = sh(
            step,
            hook("pr-test-scope", "--base-ref", "origin/main", "--src-root", pkg, "--tests-root", "tests"),
            wt,
            {**env, "UV_PROJECT_ENVIRONMENT": str(a.pipelines_venv)},
        ).strip()
        scope = re.sub(r"\s*warning: .*", "", scope, flags=re.S).strip()  # uv's environment warning shares stderr
        led.record(
            repo,
            test_scope="FULL"
            if scope == "FULL"
            else ("NONE" if scope == "NONE" else f"{len(scope.splitlines())} files"),
        )
        if scope != "NONE":
            targets = ["tests"] if scope == "FULL" else scope.splitlines()
            # No `-p`: a connector test that parses sys.argv reads it as the server port flag.
            try:
                sh(step, [py, "-m", "pytest", "-q", "-x", *targets], wt, env)
            except StepFailed as exc:
                # R016.29: a wheel built for a newer CPU (no AVX2 on this host) aborts pytest; the PR gate runs the tests.
                if (
                    "Fatal Python error: Illegal instruction" not in exc.full
                ):  # R016.37: the header is cut from the 2000-char tail
                    raise
                led.record(
                    repo, local_tests_skipped="host CPU lacks an instruction set a wheel needs; PR gates run them"
                )
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
        # Rebase-merge, never squash: a squash rewrites the landing SHA that the generated status.json records, so
        # the status commit (last on the branch) would be stale on main (PIPE-GATES-R016.16).
        sh(step, ["gh", "pr", "merge", url, "-R", slug, "--rebase", "--delete-branch"], wt)
        led.record(repo, status="merged", merged_at=time.strftime("%FT%TZ", time.gmtime()))
        step = "status-on-main"
        check_status_on_main(wt, env, a, led, repo)
    except StepFailed as exc:
        led.record(repo, status="failed", failed_step=exc.step, output_tail=exc.output)
        (tmp / f"failed-{exc.step}.log").write_text(
            exc.full, encoding="utf-8"
        )  # the ledger keeps only the last 2000 chars
    except Exception as exc:  # noqa: BLE001 - recorded, then this repo stops
        led.record(repo, status="failed", failed_step=step, output_tail=f"{type(exc).__name__}: {exc}")


def check_status_on_main(wt: Path, env: dict[str, str], a: argparse.Namespace, led: Ledger, repo: str) -> None:
    """After the merge, ``spec-status`` on the merged main must change nothing; the result goes to the ledger."""
    if not (wt / "specs").is_dir():
        return
    sh("status-on-main", ["git", "fetch", "origin", "main"], wt, env)
    sh("status-on-main", ["git", "checkout", "-q", "--detach", "origin/main"], wt, env)
    try:
        sh(
            "status-on-main",
            hook("spec-status", "--root", str(wt)),
            wt,
            {**env, "UV_PROJECT_ENVIRONMENT": str(a.pipelines_venv)},
        )
        led.record(repo, status_on_main="fresh (0 changes)")
    except StepFailed as exc:
        led.record(repo, status_on_main="STALE: " + exc.output[-400:])


def central_verify(wt: Path, py: str, env: dict[str, str], led: Ledger, repo: str, a: argparse.Namespace) -> None:
    """R016.100: the central pass's own checks: SDK conformance plugin, ``connector-standard`` and ``render --check``.

    A failing check fails the repo; in ``--dry-run`` it is recorded in the ledger instead so the pilot reports it.
    """
    venv_env = {**env, "UV_PROJECT_ENVIRONMENT": str(a.pipelines_venv)}
    connector = ["uv", "run", "--project", str(PIPELINES), "--frozen", "pipelines-connector"]
    checks = {
        "conformance": ([py, "-m", "pytest", "-q", "-k", "connector_conformance"], env),
        "connector_standard": (hook("connector-standard"), venv_env),
        "render_check": ([*connector, "render", "--root", str(wt), "--check"], venv_env),
    }
    for name, (cmd, cenv) in checks.items():
        try:
            out = sh("verify", cmd, wt, cenv)
            led.record(repo, **{name: "pass: " + (out.strip().splitlines() or [""])[-1][-200:]})
        except StepFailed as exc:
            led.record(repo, **{name: "FAIL: " + exc.output[-1200:]})
            if not a.dry_run:
                raise


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
        # A skipped job (the container build on a PR) is not a failure: every other `gates` check has to pass.
        if checks and "pass" in buckets and buckets <= {"pass", "skipping"}:
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
    ap.add_argument(
        "--workspace",
        type=Path,
        default=Path("/home/apps/workspace/workspace.yml"),
        help="workspace manifest; the repo set is its agents group intersected with the non-archived GitHub repos",
    )
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
    ap.add_argument("--central", action="store_true", help="the central connector migration (rules R016.50 to R016.99)")
    ap.add_argument("--rebump", action="store_true", help="already-migrated repos: SDK floor, patch bump and lock only")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true", help="migrate and verify only; no push")
    ap.add_argument("--sdk-path", type=Path, default=None, help="install this SDK checkout instead of PyPI (dry-run)")
    ap.add_argument(
        "--sdk-distribution",
        choices=("agent-connector-sdk", "scion-sdk"),
        default=None,
        help="explicit SDK distribution migration target; omitted preserves each project's detected spelling",
    )
    a = ap.parse_args()
    a.jobs = min(a.jobs, 4)
    sys.path.insert(0, str(PIPELINES))
    from pipelines_hooks.hygiene.connector_central.fleet import connector_repos, only_active

    if a.repos or a.fleet_list:
        asked = a.repos or [ln.strip() for ln in a.fleet_list.read_text().splitlines() if ln.strip()]
        repos = only_active(asked, a.workspace)
    else:
        repos = connector_repos(a.workspace)
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
