"""Hermetic unit profile for ``test-quality --unit-profile``.

The unit runner denies outbound network connections and container-client access, uses a
temporary HOME, drops credential variables and fixes the hash seed, the random seed and
the clock the declared doubles read.  Enforcement is a ``sitecustomize`` guard placed first
on ``PYTHONPATH``; Python subprocesses inherit it, and ``subprocess``/``os.exec*``/``os.system``
calls to container or network clients are denied by name.  Every denial is logged with the
requesting test identity.  Every required category must have tests and every external seam a
deterministic double that exists; the runner must be Python.  Anything else is ``CannotRun``.
Unit results never stand in for real-component integration receipts.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env

GUARD = """\
import json, os, socket, subprocess

_LOG = os.environ["PIPELINES_UNIT_DENIAL_LOG"]
_DENIED = {"docker", "podman", "nerdctl", "crictl", "ctr", "buildah", "curl", "wget", "ssh", "nc", "ncat"}


def _deny(kind, target):
    who = os.environ.get("PYTEST_CURRENT_TEST") or "process-%d" % os.getpid()
    with open(_LOG, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"kind": kind, "target": str(target), "who": who}) + "\\n")
    raise PermissionError("unit profile denies %s: %s" % (kind, target))


def _check_address(address):
    if isinstance(address, str):
        if any(m in address for m in ("docker.sock", "podman.sock", "containerd.sock")):
            _deny("container", address)
        return
    _deny("network", address)


_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
socket.socket.connect = lambda self, address: (_check_address(address), _connect(self, address))[1]
socket.socket.connect_ex = lambda self, address: (_check_address(address), _connect_ex(self, address))[1]


def _argv0(args):
    first = args[0] if isinstance(args, (list, tuple)) and args else args
    return os.path.basename(str(first).split()[0]) if first else ""


def _guard_exec(args):
    if _argv0(args) in _DENIED:
        _deny("container-or-network-client", args)


_popen = subprocess.Popen.__init__


def _popen_init(self, args, *a, **k):
    _guard_exec(args)
    return _popen(self, args, *a, **k)


subprocess.Popen.__init__ = _popen_init
_system = os.system
os.system = lambda command: (_guard_exec(command), _system(command))[1]
for _name in ("execv", "execve", "execvp", "execvpe", "posix_spawn", "posix_spawnp"):
    if hasattr(os, _name):
        def _wrap(_orig=getattr(os, _name)):
            return lambda path, *rest: (_guard_exec([path]), _orig(path, *rest))[1]
        setattr(os, _name, _wrap())
"""
_SECRET_ENV = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|CREDENTIAL|DOCKER_HOST|AUTH)", re.I)
_IGNORE = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "node_modules")


@dataclass
class UnitResult:
    findings: list[tuple[str, int, str]] = field(default_factory=list)
    evidence: dict[str, object] = field(default_factory=dict)


def check(root: Path, policy_path: Path) -> UnitResult:
    try:
        raw = policy_path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
        runner = [str(a) for a in data["runner"]]
        categories = {c["name"]: list(c["tests"]) for c in data["categories"]}
        required = list(data["required_categories"])
        seams = list(data.get("seams", []))
        seed, clock = int(data["seed"]), str(data["clock"])
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as exc:
        raise CannotRun(f"{policy_path.name}: unit profile is unreadable or incomplete: {exc!r}") from exc
    if "python" not in Path(runner[0]).name:
        raise CannotRun(f"{policy_path.name}: unsupported isolation for runner {runner[0]!r}; the guard needs Python")
    omitted = [c for c in required if not categories.get(c)]
    if omitted:
        raise CannotRun(f"{policy_path.name}: required unit categories without tests: {omitted}")
    for seam in seams:
        double = root / str(seam.get("double", ""))
        if not seam.get("double") or not double.is_file() or not seam.get("contract"):
            raise CannotRun(
                f"{policy_path.name}: seam {seam.get('name', '?')} lacks an existing deterministic double and contract"
            )
    tests = sorted({t for c in categories.values() for t in c})
    result = UnitResult()
    with tempfile.TemporaryDirectory(prefix="unit-") as tmp:
        work, guard, home = Path(tmp) / "tree", Path(tmp) / "guard", Path(tmp) / "home"
        shutil.copytree(root, work, ignore=_IGNORE)
        guard.mkdir()
        home.mkdir()
        (guard / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
        log = Path(tmp) / "denials.jsonl"
        log.touch()
        env = {k: v for k, v in sanitized_env().items() if not _SECRET_ENV.search(k)}
        env.update(
            HOME=str(home),
            PYTHONHASHSEED=str(seed),
            PIPELINES_UNIT_SEED=str(seed),
            PIPELINES_UNIT_CLOCK=clock,
            PIPELINES_UNIT_DENIAL_LOG=str(log),
            PYTHONPATH=str(guard),
            TMPDIR=str(home),
        )
        try:
            proc = subprocess.run(  # noqa: S603 -- declared argv
                [*runner, *tests],
                cwd=work,
                env=env,
                capture_output=True,
                text=True,
                timeout=int(data.get("timeout", 300)),
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise CannotRun(f"unit runner did not finish: {exc!r}") from exc
        denials = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
    if proc.returncode not in (0, 1):
        raise CannotRun(f"unit runner exited {proc.returncode}: {(proc.stdout + proc.stderr)[-300:]}")
    result.findings = [(str(d["who"]).split("::")[0].split(" ")[0], 1, "isolation-violation") for d in denials]
    if proc.returncode == 1 and not denials:
        raise CannotRun("unit tests failed without an isolation denial; the unit profile needs a green run")
    result.evidence = {
        "policy_digest": hashlib.sha256(raw).hexdigest(),
        "categories": {c: sorted(t) for c, t in categories.items()},
        "doubles": [{"seam": s["name"], "double": s["double"], "contract": s["contract"]} for s in seams],
        "seed": seed,
        "clock": clock,
        "isolation": "sitecustomize guard on PYTHONPATH (inherited by Python subprocesses) plus executable denylist",
        "denied": denials,
        "source_digest": hashlib.sha256(b"".join((root / t.split("::")[0]).read_bytes() for t in tests)).hexdigest(),
        "integration_receipts": "required separately; an offline pass does not imply external integration",
    }
    return result
