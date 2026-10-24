"""Post-merge checks of one or more migrated connectors: release run, PyPI version, fresh-install stdio startup.

Usage: connector_central_postcheck.py <repo>...  (reads the repo's `central` worktree under the repository-worktrees directory).
"""

"""Post-merge checks for one merged repo: release run success, PyPI version, stdio startup under the installed SDK."""
import json
import subprocess
import sys
import time
import tomllib
import shutil
from pathlib import Path

WT = Path.home() / ".local/state/repository-worktrees"
VERIFY = Path(__file__).resolve().parent / "connector_verify.py"
VERIFY_PREV = Path(__file__).resolve().parent / "connector_prev_tools.py"


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def check(repo):
    wt = WT / repo / "central"
    out = {"repo": repo}
    sh(["git", "fetch", "-q", "origin", "main"], cwd=wt)
    sha = sh(["git", "rev-parse", "origin/main"], cwd=wt).stdout.strip()
    data = tomllib.loads(sh(["git", "show", "origin/main:pyproject.toml"], cwd=wt).stdout)
    dist, ver = data["project"]["name"], data["project"]["version"]
    out.update(dist=dist, version=ver, sha=sha[:7])
    sh(["git", "checkout", "-q", "--detach", "origin/main"], cwd=wt)
    # release run for this sha
    run_id = None
    for _ in range(40):
        r = sh(
            [
                "gh",
                "run",
                "list",
                "-R",
                f"Knuckles-Team/{repo}",
                "--commit",
                sha,
                "--json",
                "name,status,conclusion,databaseId",
            ]
        )
        runs = [x for x in json.loads(r.stdout or "[]") if "Release" in x["name"] or "Upload" in x["name"]]
        if runs:
            run_id = runs[0]["databaseId"]
            break
        time.sleep(15)
    if run_id is None:
        out["release"] = "no release run found"
        return out
    for _ in range(120):
        v = json.loads(
            sh(
                ["gh", "run", "view", str(run_id), "-R", f"Knuckles-Team/{repo}", "--json", "status,conclusion,jobs"]
            ).stdout
        )
        if v["status"] == "completed":
            break
        time.sleep(15)
    out["release"] = v.get("conclusion")
    out["jobs"] = {j["name"]: j["conclusion"] for j in v.get("jobs", [])}
    if v.get("conclusion") != "success":
        return out
    venv = Path(f"/var/tmp/connector-central/pc-venv/{repo}")
    shutil.rmtree(venv, ignore_errors=True)
    sh(["uv", "venv", "-q", str(venv), "--python", "3.14"])
    ok = False
    for _ in range(20):
        p = sh(["uv", "pip", "install", "-q", "--python", str(venv / "bin/python"), f"{dist}=={ver}"])
        if p.returncode == 0:
            ok = True
            break
        time.sleep(30)
    out["pypi"] = ver if ok else "not installable"
    if not ok:
        return out
    sdk = sh(
        [str(venv / "bin/python"), "-c", "import importlib.metadata as m;print(m.version('agent-connector-sdk'))"]
    ).stdout.strip()
    out["sdk"] = sdk
    p = sh([str(venv / "bin/python"), str(VERIFY), str(wt), "--names"])
    try:
        out["startup"] = json.loads([ln for ln in p.stdout.splitlines() if ln.startswith("{")][-1])
    except Exception:
        out["startup"] = {"ok": False, "error": (p.stdout + p.stderr)[-300:]}
    shutil.rmtree(venv, ignore_errors=True)
    names = out["startup"].pop("tool_names", None)
    out["tool_names_vs_pre_migration"] = compare_tool_names(repo, dist, ver, names)
    return out


def previous_version(dist, ver):
    """The PyPI release just below ``ver`` (the last pre-migration release), or None."""
    r = sh(["pip", "index", "versions", dist])
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("Available versions:")), "")
    versions = [v.strip() for v in line.split(":", 1)[-1].split(",") if v.strip()]
    older = [
        v
        for v in versions
        if v != ver and tuple(int(x) for x in v.split(".")[:3]) < tuple(int(x) for x in ver.split(".")[:3])
    ]
    return older[0] if older else None


def compare_tool_names(repo, dist, ver, names):
    """Tool names of the migrated release against the last earlier release, listed over stdio in a fresh install."""
    if names is None:
        return {"status": "no names listed"}
    prev = previous_version(dist, ver)
    if prev is None:
        return {"status": "no earlier release"}
    venv = Path(f"/var/tmp/connector-central/pc-venv/{repo}-prev")
    shutil.rmtree(venv, ignore_errors=True)
    sh(["uv", "venv", "-q", str(venv), "--python", "3.14"])
    p = sh(["uv", "pip", "install", "-q", "--python", str(venv / "bin/python"), f"{dist}=={prev}"])
    if p.returncode:
        return {"status": "earlier release not installable", "previous": prev}
    q = sh([str(venv / "bin/python"), str(VERIFY_PREV), str(venv / "bin/python"), dist])
    shutil.rmtree(venv, ignore_errors=True)
    try:
        before = json.loads([ln for ln in q.stdout.splitlines() if ln.startswith("[")][-1])
    except Exception:
        return {"status": "earlier release did not start", "previous": prev, "detail": (q.stdout + q.stderr)[-200:]}
    return {
        "status": "same" if sorted(before) == sorted(names) else "differs",
        "previous": prev,
        "before": len(before),
        "after": len(names),
        "removed": sorted(set(before) - set(names)),
        "added": sorted(set(names) - set(before)),
    }


if __name__ == "__main__":
    for r in sys.argv[1:]:
        print(json.dumps(check(r)), flush=True)
