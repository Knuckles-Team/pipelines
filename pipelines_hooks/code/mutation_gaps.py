"""mutation-gaps: surviving mutants of core modules reported as test gaps.

A scheduled run (``.github/workflows/mutation.yml``) mutates every module under
``[tool.pipelines_hooks.mutation_gaps] modules`` (default ``pipelines_hooks/core``),
runs the repository's tests against each mutant in a throwaway copy of the
tracked tree, and reports each mutant the tests did not kill as a test gap with
its module, line and operator. The default runner is the deterministic AST
mutator below; the test command is replaceable through ``test_command``.
"""

from __future__ import annotations

import argparse
import ast
import copy
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.errors import CannotRun, Unavailable
from pipelines_hooks.core.gitenv import repo_root, run_git, sanitized_env
from pipelines_hooks.core.tracked import tracked_or_walked

DEFAULT_MODULES = ("pipelines_hooks/core",)
DEFAULT_SCHEDULE = "weekly"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_TEST_COMMAND = (sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-p", "no:xdist")

_COMPARE_SWAP: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.GtE: ast.Lt,
    ast.Gt: ast.LtE,
    ast.LtE: ast.Gt,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}
_BINOP_SWAP: dict[type[ast.operator], type[ast.operator]] = {ast.Add: ast.Sub, ast.Sub: ast.Add}


@dataclass(frozen=True)
class MutationPolicy:
    """Which modules are mutated, how often, and how the tests are run."""

    modules: tuple[str, ...] = DEFAULT_MODULES
    schedule: str = DEFAULT_SCHEDULE
    test_command: tuple[str, ...] = DEFAULT_TEST_COMMAND
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    root: Path = field(default_factory=Path.cwd)


@dataclass(frozen=True)
class SurvivingMutation:
    """One mutant the tests did not kill."""

    module: str
    line: int
    operator: str

    def render(self) -> str:
        return f"{self.module}:{self.line} {self.operator}"


@dataclass(frozen=True)
class Mutant:
    """One candidate mutation of one module, with its mutated source."""

    module: str
    line: int
    operator: str
    source: str


#: A runner reports whether the tests killed (rejected) the mutant.
Runner = Callable[[Mutant], bool]


@dataclass(frozen=True)
class ModuleResult:
    module: str
    killed: int
    survivors: tuple[SurvivingMutation, ...]
    finding: str | None = None


def policy_from_config(root: Path) -> MutationPolicy:
    section = load_config(root).section("mutation_gaps")
    modules = string_tuple(section["modules"], "mutation_gaps.modules") if "modules" in section else DEFAULT_MODULES
    command = (
        string_tuple(section["test_command"], "mutation_gaps.test_command")
        if "test_command" in section
        else DEFAULT_TEST_COMMAND
    )
    schedule = section.get("schedule", DEFAULT_SCHEDULE)
    timeout = section.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if schedule not in {"weekly", "daily", "monthly"}:
        raise CannotRun("[tool.pipelines_hooks.mutation_gaps] schedule must be daily, weekly or monthly")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
        raise CannotRun("[tool.pipelines_hooks.mutation_gaps] timeout_seconds must be a positive integer")
    return MutationPolicy(modules=modules, schedule=schedule, test_command=command, timeout_seconds=timeout, root=root)


def _candidates(tree: ast.AST) -> Iterator[tuple[int, int, str]]:
    """Yield ``(ordinal, line, operator)`` for each mutable node, in walk order."""
    for ordinal, node in enumerate(ast.walk(tree)):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Compare) and type(node.ops[0]) in _COMPARE_SWAP:
            yield ordinal, line, f"compare {type(node.ops[0]).__name__}->{_COMPARE_SWAP[type(node.ops[0])].__name__}"
        elif isinstance(node, ast.BoolOp):
            yield ordinal, line, "boolop " + ("And->Or" if isinstance(node.op, ast.And) else "Or->And")
        elif isinstance(node, ast.BinOp) and type(node.op) in _BINOP_SWAP:
            yield ordinal, line, f"binop {type(node.op).__name__}->{_BINOP_SWAP[type(node.op)].__name__}"
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            yield ordinal, line, f"constant {node.value}->{not node.value}"


def _apply(tree: ast.AST, ordinal: int) -> None:
    node = list(ast.walk(tree))[ordinal]
    if isinstance(node, ast.Compare):
        node.ops[0] = _COMPARE_SWAP[type(node.ops[0])]()
    elif isinstance(node, ast.BoolOp):
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif isinstance(node, ast.BinOp):
        node.op = _BINOP_SWAP[type(node.op)]()
    elif isinstance(node, ast.Constant):
        node.value = not node.value


def mutants_of(module: str, source: str) -> list[Mutant]:
    """Every deterministic mutant of one module's source."""
    try:
        tree = ast.parse(source, filename=module)
    except SyntaxError as exc:
        raise CannotRun(f"mutation-gaps: cannot parse {module}: {exc}") from exc
    result: list[Mutant] = []
    for ordinal, line, operator in _candidates(tree):
        mutated = copy.deepcopy(tree)
        _apply(mutated, ordinal)
        result.append(Mutant(module, line, operator, ast.unparse(ast.fix_missing_locations(mutated)) + "\n"))
    return result


def _has_tests(root: Path, module: str) -> bool:
    stem = Path(module).stem
    for path in tracked_or_walked(root, ("test_*.py", "*_test.py"), root=root):
        try:
            if stem in path.read_text(encoding="utf-8"):
                return True
        except (OSError, UnicodeError):
            continue
    return False


def _module_files(policy: MutationPolicy) -> list[str]:
    files: list[str] = []
    for base in policy.modules:
        target = policy.root / base
        if not target.exists():
            raise CannotRun(f"mutation-gaps: declared module path {base} does not exist")
        found = [target] if target.is_file() else tracked_or_walked(target, ("*.py",), root=policy.root)
        files.extend(path.relative_to(policy.root).as_posix() for path in found if path.name != "__init__.py")
    return sorted(set(files))


def evaluate(policy: MutationPolicy, runner: Runner) -> list[ModuleResult]:
    """Run every mutant of every declared module through ``runner``."""
    results: list[ModuleResult] = []
    for module in _module_files(policy):
        if not _has_tests(policy.root, module):
            results.append(ModuleResult(module, 0, (), finding="no-tests-for-module"))
            continue
        source = (policy.root / module).read_text(encoding="utf-8")
        survived: list[SurvivingMutation] = []
        killed = 0
        for mutant in mutants_of(module, source):
            if runner(mutant):
                killed += 1
            else:
                survived.append(SurvivingMutation(module, mutant.line, mutant.operator))
        results.append(ModuleResult(module, killed, tuple(survived)))
    return results


def survivors(policy: MutationPolicy, runner: Runner) -> list[SurvivingMutation]:
    """One :class:`SurvivingMutation` per mutant the tests did not kill, none for killed ones."""
    return [mutation for result in evaluate(policy, runner) for mutation in result.survivors]


def _tracked_files(root: Path) -> list[str]:
    result = run_git(root, ("ls-files", "-z"), preserve_index=True)
    if result.returncode != 0:
        raise CannotRun("mutation-gaps: cannot list tracked files")
    return [name for name in (result.stdout or "").split("\0") if name]


class SubprocessRunner:
    """The default runner: the test command against a mutant in a throwaway tracked-tree copy."""

    def __init__(self, policy: MutationPolicy) -> None:
        executable = policy.test_command[0]
        if shutil.which(executable) is None and not Path(executable).is_file():
            raise Unavailable(f"the mutation test runner {executable!r} is not installed")
        self.policy = policy
        self._tmp = tempfile.TemporaryDirectory(prefix="mutation-gaps-")
        self.copy = Path(self._tmp.name)
        for rel in _tracked_files(policy.root):
            source = policy.root / rel
            if source.is_file():
                (self.copy / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, self.copy / rel)

    def close(self) -> None:
        self._tmp.cleanup()

    def baseline_passes(self) -> bool:
        return self._run()

    def _run(self) -> bool:
        try:
            done = subprocess.run(
                list(self.policy.test_command),
                cwd=self.copy,
                env=sanitized_env(),
                capture_output=True,
                timeout=self.policy.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False
        return done.returncode == 0

    def __call__(self, mutant: Mutant) -> bool:
        target = self.copy / mutant.module
        original = target.read_bytes()
        target.write_text(mutant.source, encoding="utf-8")
        try:
            return not self._run()
        finally:
            target.write_bytes(original)


def render(results: list[ModuleResult]) -> list[str]:
    lines: list[str] = []
    for result in results:
        if result.finding:
            lines.append(f"{result.module}: {result.finding}")
            continue
        lines.extend(mutation.render() for mutation in result.survivors)
        lines.append(f"{result.module}: killed {result.killed}, survived {len(result.survivors)}")
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mutation-gaps", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    policy = policy_from_config(root)
    runner = SubprocessRunner(policy)
    try:
        if not runner.baseline_passes():
            raise CannotRun("mutation-gaps: the unmutated tests do not pass, so no mutant can be judged")
        results = evaluate(policy, runner)
    finally:
        runner.close()
    for line in render(results):
        print(f"  {line}")
    gaps = sum(len(r.survivors) for r in results) + sum(1 for r in results if r.finding)
    if gaps:
        print(f"mutation-gaps: {gaps} test gap(s): add tests that fail on each surviving mutant")
        return 1
    print("mutation-gaps: OK: every mutant was killed")
    return 0
