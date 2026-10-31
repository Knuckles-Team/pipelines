"""Dry-run census of the central connector migration over the active connector set (PIPE-GATES-R016.44).

Usage: connector_central_census.py <pipelines checkout> <out.json>. Copies each repo's origin/main into /var/tmp/cm-census/work,
runs migrate_central (no lock refresh, no push) and records blocking items. Set IDENTITY_CATALOG_FILE to also scan privacy.
"""

import json
import os
import subprocess
import sys
import shutil
from concurrent.futures import ProcessPoolExecutor

W = sys.argv[1]
OUT = sys.argv[2]
sys.path.insert(0, W)
from pipelines_hooks.hygiene.connector_central.fleet import WORKSPACE_ROOT  # noqa: E402

AG = str(WORKSPACE_ROOT / "agent-packages" / "agents")


def run(repo):
    from pipelines_hooks.hygiene.connector_central import migrate_central

    d = f"/var/tmp/cm-census/work-g7/{repo}"
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    p = subprocess.run(f"git -C {AG}/{repo} archive origin/main | tar -x -C {d}", shell=True, capture_output=True)
    if p.returncode:
        return repo, {"error": "archive failed"}
    subprocess.run(["git", "init", "-q"], cwd=d, env=env)
    subprocess.run(["git", "add", "-f", "-A"], cwd=d, env=env, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=c", "-c", "user.email=c@c", "commit", "-qm", "x"], cwd=d, env=env, capture_output=True
    )
    try:
        r = migrate_central(d, {"no_lock": True, "pipelines_root": W})
    except Exception as e:
        return repo, {"error": f"{type(e).__name__}: {e}"}
    priv = None
    if "IDENTITY_CATALOG_FILE" not in os.environ:
        return repo, {
            "privacy": None,
            "blocking": [i for i in r["review"] if i["blocking"]],
            "nonblocking": len([i for i in r["review"] if not i["blocking"]]),
            "changed": len(r["changed"]),
            "deleted": len(r["deleted"]),
            "applied": r["applied"],
        }
    try:
        from pipelines_hooks.privacy.gate import scan
        from pipelines_hooks.privacy.identity_catalog import load_identity_catalog
        from pathlib import Path

        saved = dict(os.environ)
        os.environ.update(
            {
                "HOME": "/nonexistent",
                "USER": "runner",
                "LOGNAME": "runner",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
            }
        )
        try:
            rows = scan(Path(d), load_identity_catalog(Path(os.environ["IDENTITY_CATALOG_FILE"])))
        finally:
            os.environ.clear()
            os.environ.update(saved)
        priv = {}
        for _p, _l, cat, _h in rows:
            priv[cat] = priv.get(cat, 0) + 1
    except Exception as e:
        priv = {"error": f"{type(e).__name__}: {e}"[:120]}
    return repo, {
        "privacy": priv,
        "blocking": [i for i in r["review"] if i["blocking"]],
        "nonblocking": len([i for i in r["review"] if not i["blocking"]]),
        "changed": len(r["changed"]),
        "deleted": len(r["deleted"]),
        "applied": r["applied"],
    }


if __name__ == "__main__":
    from pipelines_hooks.hygiene.connector_central.fleet import connector_repos

    repos = sorted(connector_repos())
    res = {}
    with ProcessPoolExecutor(8) as ex:
        for repo, r in ex.map(run, repos):
            res[repo] = r
    json.dump(res, open(OUT, "w"), indent=1)
    ok = [r for r, v in res.items() if "blocking" in v and not v["blocking"]]
    print(len(res), "repos;", len(ok), "with no blocking item")
