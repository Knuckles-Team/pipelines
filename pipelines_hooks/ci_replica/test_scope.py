"""pr-test-scope: the tests a pull request's diff actually needs to re-run.

Operator decision (2026-10-09): PR gates run a fast subset -- lint, type
check, the spec check, and only the tests the diff could plausibly break --
so a PR auto-merges within minutes; `push` to main and release tags still
run the full suite unchanged (that path never calls this gate).

``--lang python`` maps each changed ``<src-root>/**/*.py`` file to its mirror
``<tests-root>/.../test_<name>.py`` (the layout most repos in this fleet use:
``graph_os/fleet/foo.py`` <-> ``tests/fleet/test_foo.py``), and always
includes a changed file that already lives under ``tests-root``. A changed
file with no mirror falls back to a static import-graph scan
(:mod:`pipelines_hooks.ci_replica.import_graph`): every test file that
imports the changed module, or imports a module that itself -- transitively,
up to 3 further hops -- imports it, is selected instead. Only a change to a
global fixture (``conftest.py``, ``pyproject.toml``, the lockfile) forces the
conservative fallback: print ``FULL`` so the caller re-runs everything rather
than trusting a narrowed scope against shared test infrastructure. No
matching production or test change at all prints ``NONE`` so the caller
skips the test step entirely.

``--lang rust`` maps each changed file under ``--workspace-root`` to the
nearest ancestor crate (the directory holding its ``Cargo.toml``) and prints
one crate name per line for ``cargo test -p <crate>``; a workspace-wide file
(the root ``Cargo.toml``/``Cargo.lock``) forces ``FULL``.

Output contract (stdout, one token per line): ``NONE`` | ``FULL`` | a
newline-separated, order-stable list of test paths (python) or crate names
(rust). Exit status is always 0 once the diff could be read; an unreadable
diff is :class:`CannotRun` (exit 2), matching every other differential gate.
"""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from pipelines_hooks.ci_replica.import_graph import module_for_path, test_files_importing
from pipelines_hooks.clones.dupehound import changed_paths
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.settings import setting

FULL = "FULL"
NONE = "NONE"

#: Changing any of these always forces the full suite: they are not owned by
#: one mirrored test file, they change what every test runs against.
_GLOBAL_PYTHON_TRIGGERS = ("conftest.py", "pyproject.toml", "uv.lock")
_GLOBAL_RUST_TRIGGERS = ("Cargo.lock",)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pr-test-scope", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref", "--diff", dest="base_ref", required=True)
    parser.add_argument("--lang", choices=("python", "rust"), default="python")
    parser.add_argument("--src-root", default="graph_os", help="python only: the package under test")
    parser.add_argument("--tests-root", default="tests", help="python only: the mirrored test tree")
    parser.add_argument("--workspace-root", default=".", help="rust only: the Cargo workspace root")
    return parser.parse_args(argv)


def _is_global_trigger(path: str, triggers: tuple[str, ...]) -> bool:
    return any(path == trigger or path.endswith(f"/{trigger}") for trigger in triggers)


def _mirrored_test(tests_root: str, rel: str, tree: Path) -> str | None:
    """The mirror test path for ``<src_root>/<rel>`` if it exists on disk."""
    sub_dir, _, name = rel.rpartition("/")
    candidate = f"{tests_root}/{sub_dir}/test_{name}" if sub_dir else f"{tests_root}/test_{name}"
    return candidate if (tree / candidate).is_file() else None


class _DedupedScope:
    """The order-stable, deduplicated list this gate prints, or a fallback."""

    def __init__(self) -> None:
        self._selected: list[str] = []
        self._seen: set[str] = set()

    def add(self, item: str) -> None:
        if item not in self._seen:
            self._seen.add(item)
            self._selected.append(item)

    def resolve(self) -> list[str]:
        return self._selected or [NONE]


def _handle_python_path(scope: _DedupedScope, path: str, root: Path, src_prefix: str, tests_prefix: str) -> bool:
    """Apply one changed path to ``scope``. True means the caller must return ``FULL``."""
    if _is_global_trigger(path, _GLOBAL_PYTHON_TRIGGERS):
        return True
    if path.startswith(tests_prefix) and path.endswith(".py"):
        scope.add(path)
        return False
    if not (path.startswith(src_prefix) and path.endswith(".py")):
        return False
    rel = path[len(src_prefix) :]
    mirror = _mirrored_test(tests_prefix.rstrip("/"), rel, root)
    if mirror is not None:
        scope.add(mirror)
        return False
    _add_import_graph_matches(scope, root, src_prefix, tests_prefix, rel)
    return False


def _add_import_graph_matches(scope: _DedupedScope, root: Path, src_prefix: str, tests_prefix: str, rel: str) -> None:
    """No mirrored test file: fall back to the import graph, not FULL.

    A changed module with no mirror and no importers within the graph adds
    nothing to the scope -- that is not treated as an unreadable diff.
    """
    changed_module = module_for_path(root, src_prefix.rstrip("/"), rel)
    for test_path in test_files_importing(
        root, src_prefix.rstrip("/"), tests_prefix=tests_prefix.rstrip("/"), changed_module=changed_module
    ):
        scope.add(test_path)


def _python_scope(root: Path, changed: list[str], src_root: str, tests_root: str) -> list[str]:
    src_prefix, tests_prefix = f"{src_root}/", f"{tests_root}/"
    scope = _DedupedScope()
    for path in changed:
        if _handle_python_path(scope, path, root, src_prefix, tests_prefix):
            return [FULL]
    return scope.resolve()


def _crate_name(cargo_toml: Path) -> str | None:
    try:
        data = tomllib.loads(cargo_toml.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    name = data.get("package", {}).get("name")
    return name if isinstance(name, str) else None


def _nearest_crate(root: Path, workspace_root: Path, rel: str) -> str | None:
    directory = (workspace_root / rel).parent
    while True:
        candidate = directory / "Cargo.toml"
        if candidate.is_file():
            name = _crate_name(candidate)
            if name:
                return name
        if directory in (workspace_root, root) or directory == directory.parent:
            return None
        directory = directory.parent


def _rust_root_cargo_toml(workspace_root: str) -> str:
    trimmed = workspace_root.rstrip(".").rstrip("/")
    return f"{trimmed}/Cargo.toml".lstrip("/")


def _handle_rust_path(scope: _DedupedScope, root: Path, ws: Path, workspace_root: str, path: str) -> bool:
    """Apply one changed path to ``scope``. True means the caller must return ``FULL``."""
    if _is_global_trigger(path, _GLOBAL_RUST_TRIGGERS) or path == _rust_root_cargo_toml(workspace_root):
        return True
    if not path.endswith(".rs") and not path.endswith("Cargo.toml"):
        return False
    crate = _nearest_crate(root, ws, path)
    if crate is None:
        # A changed Rust file this gate cannot attribute to a crate is the
        # same unmapped case as the python path: force the safe fallback.
        return True
    scope.add(crate)
    return False


def _rust_scope(root: Path, changed: list[str], workspace_root: str) -> list[str]:
    ws = (root / workspace_root).resolve()
    scope = _DedupedScope()
    for path in changed:
        if _handle_rust_path(scope, root, ws, workspace_root, path):
            return [FULL]
    return scope.resolve()


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    root = repo_root(args.root)
    base_ref = args.base_ref or setting("PR_TEST_SCOPE_BASE_REF") or None
    changed = changed_paths(root, base_ref)
    if args.lang == "python":
        result = _python_scope(root, changed, args.src_root.rstrip("/"), args.tests_root.rstrip("/"))
    else:
        result = _rust_scope(root, changed, args.workspace_root)
    print("\n".join(result))
    return 0
