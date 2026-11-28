"""PIPE-GATES-R086.20 to R086.28: the census resolves receivers across comprehensions, files, calls and unions."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pipelines_hooks.code import state_machine
from pipelines_hooks.code.state_machine_types import MAX_HOPS, PackageIndex
from tests.hooks.state_machine_repo import POLICY, git

JOB = """\
class Job:
    status: str

    def close(self) -> None:
        self.status = "closed"
"""
HEALTH = """\
from enum import StrEnum


class Health(StrEnum):
    UP = "up"
    DOWN = "down"


class Evidence:
    status: Health
    ready: bool
"""


def _census(tmp_path: Path, files: dict[str, str]) -> list[str]:
    """The finding lines of a census over a throwaway package holding ``files`` (under ``pkg/``)."""
    root = tmp_path / "repo"
    for name, text in {"pkg/__init__.py": "", **{f"pkg/{n}": t for n, t in files.items()}}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    (root / "pyproject.toml").write_text(POLICY.format(mode="blocking", extra=""), encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")
    return [finding.render() for finding in state_machine.run(root, census=True).findings]


def _attributed(lines: list[str], file: str) -> bool:
    """A string compare in ``file`` was counted against ``Job``."""
    return any(
        line.startswith(f"pkg/{file}:") and " Job SM-STRING-STATUS" in line and "string compare" in line
        for line in lines
    )


def _unresolved(lines: list[str]) -> list[str]:
    return [line for line in lines if "<unresolved>" in line]


@pytest.mark.spec("PIPE-GATES-R086.20")
def test_a_generator_variable_is_bound_to_the_element_type(tmp_path: Path) -> None:
    use = 'def f(jobs: list[Job]) -> bool:\n    return any(j.status == "open" for j in jobs)\n'
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert _attributed(lines, "jobs.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.20")
def test_a_list_comprehension_variable_and_a_nested_clause_are_bound(tmp_path: Path) -> None:
    use = (
        "class Box:\n    jobs: list[Job]\n\n\n"
        'def f(boxes: list[Box]) -> list[Job]:\n    return [j for b in boxes for j in b.jobs if j.status == "open"]\n'
    )
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert _attributed(lines, "jobs.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.20")
def test_a_comprehension_variable_over_an_unknown_iterable_stays_unresolved(tmp_path: Path) -> None:
    use = 'def f(things) -> bool:\n    return any(t.status == "open" for t in things)\n'
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert len(_unresolved(lines)) == 1, lines


HOLDER = "from pkg.jobs import Job\n\n\nclass Holder:\n    inner: Job\n    items: list[Job]\n"


@pytest.mark.spec("PIPE-GATES-R086.21")
def test_a_field_chain_through_a_class_of_another_file_resolves(tmp_path: Path) -> None:
    use = 'from pkg.holder import Holder\n\n\ndef f(h: Holder) -> bool:\n    return h.inner.status == "open"\n'
    lines = _census(tmp_path, {"jobs.py": JOB, "holder.py": HOLDER, "use.py": use})
    assert _attributed(lines, "use.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.21")
def test_a_relative_import_and_a_re_export_resolve(tmp_path: Path) -> None:
    files = {
        "jobs.py": JOB,
        "holder.py": HOLDER,
        "api.py": "from .holder import Holder\n",
        "use.py": 'from .api import Holder\n\n\ndef f(h: Holder) -> bool:\n    return any(i.status == "x" for i in h.items)\n',
    }
    lines = _census(tmp_path, files)
    assert _attributed(lines, "use.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.21")
def test_the_index_is_bounded_and_deterministic() -> None:
    chain = {f"m{i}.py": f"from m{i + 1} import Job\n" for i in range(MAX_HOPS + 3)}
    chain[f"m{MAX_HOPS + 3}.py"] = "class Job:\n    status: str\n"
    trees = {path: ast.parse(text) for path, text in chain.items()}
    index = PackageIndex(trees)
    assert index.resolve(f"m{MAX_HOPS + 2}.py", "Job") is not None
    assert index.resolve("m0.py", "Job") is None  # more re-exports than the bound
    again = PackageIndex(dict(reversed(list(trees.items()))))
    assert list(index.modules) == list(again.modules) == sorted(trees)


@pytest.mark.spec("PIPE-GATES-R086.22")
def test_a_call_result_takes_the_return_annotation_of_a_function_of_another_file(tmp_path: Path) -> None:
    loader = "from pkg.jobs import Job\n\n\ndef load() -> Job:\n    return Job()\n"
    use = 'from pkg.loader import load\n\n\ndef f() -> bool:\n    return load().status == "open"\n'
    lines = _census(tmp_path, {"jobs.py": JOB, "loader.py": loader, "use.py": use})
    assert _attributed(lines, "use.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.22")
def test_a_tuple_unpacking_binds_each_element_of_the_tuple_return_type(tmp_path: Path) -> None:
    store = (
        "from pkg.jobs import Job\n\n\nclass Store:\n"
        "    async def load(self) -> tuple[Job, int]:\n        return Job(), 1\n"
    )
    use = (
        "from pkg.store import Store\n\n\n"
        'async def f(store: Store) -> bool:\n    job, _ = await store.load()\n    return job.status == "open"\n'
    )
    lines = _census(tmp_path, {"jobs.py": JOB, "store.py": store, "use.py": use})
    assert _attributed(lines, "use.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.22")
def test_asyncio_run_returns_what_the_coroutine_returns(tmp_path: Path) -> None:
    use = (
        "import asyncio\n\n\nclass Loop:\n    async def tick(self) -> Job:\n        return Job()\n\n"
        '    def go(self) -> bool:\n        return asyncio.run(self.tick()).status == "open"\n'
    )
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert _attributed(lines, "jobs.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.22")
def test_a_tuple_unpacking_of_a_call_with_no_annotation_stays_unresolved(tmp_path: Path) -> None:
    use = 'def f(store) -> bool:\n    job, _ = store.load()\n    return job.status == "open"\n'
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert len(_unresolved(lines)) == 1, lines


@pytest.mark.spec("PIPE-GATES-R086.23")
def test_a_union_is_checked_arm_by_arm_and_only_a_lifecycle_arm_reports(tmp_path: Path) -> None:
    use = 'class Err:\n    code: int\n\n\ndef f(x: Job | Err) -> bool:\n    return x.status == "open"\n'
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert _attributed(lines, "jobs.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.23")
def test_a_union_of_two_types_that_are_not_lifecycles_reports_nothing(tmp_path: Path) -> None:
    use = 'class A:\n    code: int\n\n\nclass B:\n    code: int\n\n\ndef f(x: A | B) -> bool:\n    return x.status == "open"\n'
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert not _attributed(lines, "jobs.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.24")
def test_a_tuple_display_has_the_element_type_its_items_share(tmp_path: Path) -> None:
    use = (
        "class Pair:\n    left: Job\n    right: Job\n\n\n"
        'def f(pair: Pair) -> bool:\n    return any(j.status == "x" for j in (pair.left, pair.right))\n\n\n'
        'def g(pair: Pair) -> None:\n    for j in (pair.left, pair.right):\n        assert j.status == "y"\n'
    )
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert sum("string compare" in line for line in lines) == 2, lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.24")
def test_a_tuple_display_of_mixed_types_has_no_element_type(tmp_path: Path) -> None:
    use = (
        "class Other:\n    note: str\n\n\nclass Pair:\n    left: Job\n    right: Other\n\n\n"
        'def f(pair: Pair) -> bool:\n    return any(j.status == "x" for j in (pair.left, pair.right))\n'
    )
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert len(_unresolved(lines)) == 1, lines


@pytest.mark.spec("PIPE-GATES-R086.25")
def test_a_container_return_annotation_gives_the_element_type_of_the_result(tmp_path: Path) -> None:
    use = (
        "class Board:\n    async def fetch_all(self) -> dict[str, Job]:\n        return {}\n\n"
        "    async def count(self) -> int:\n        results = await self.fetch_all()\n"
        '        return sum(1 for _, job in results.items() if job.status == "open")\n'
    )
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert _attributed(lines, "jobs.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.26")
def test_a_list_display_local_has_the_element_type_of_its_items(tmp_path: Path) -> None:
    use = (
        "def make() -> Job:\n    return Job()\n\n\n"
        'def f() -> bool:\n    records = [make(), make()]\n    return any(r.status == "open" for r in records)\n'
    )
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert _attributed(lines, "jobs.py"), lines
    assert not _unresolved(lines), lines


KIND = "class Channel:\n    id: str\n    is_dm: bool = False\n    is_group: bool = False\n"


@pytest.mark.spec("PIPE-GATES-R086.27")
def test_kind_flags_that_nothing_assigns_after_construction_are_not_a_lifecycle(tmp_path: Path) -> None:
    lines = _census(tmp_path, {"channel.py": KIND})
    assert not [line for line in lines if "SM-LIFECYCLE-FLAGS" in line], lines


@pytest.mark.spec("PIPE-GATES-R086.27")
def test_flags_assigned_in_a_constructor_only_are_still_kinds(tmp_path: Path) -> None:
    init = KIND + "\n    def __init__(self) -> None:\n        self.is_dm = True\n        self.is_group = False\n"
    lines = _census(tmp_path, {"channel.py": init})
    assert not [line for line in lines if "SM-LIFECYCLE-FLAGS" in line], lines


@pytest.mark.spec("PIPE-GATES-R086.27")
def test_flags_assigned_by_a_method_are_a_lifecycle(tmp_path: Path) -> None:
    moves = KIND + "\n    def lock(self) -> None:\n        self.is_dm = True\n        self.is_group = False\n"
    lines = _census(tmp_path, {"channel.py": moves})
    assert [line for line in lines if "Channel SM-LIFECYCLE-FLAGS" in line], lines


@pytest.mark.spec("PIPE-GATES-R086.27")
def test_flags_assigned_from_another_file_through_a_typed_receiver_are_a_lifecycle(tmp_path: Path) -> None:
    use = (
        "from pkg.channel import Channel\n\n\ndef lock(c: Channel) -> None:\n    c.is_dm = True\n"
        "\n\ndef unlock(c: Channel) -> Channel:\n    return c.model_copy(update={'is_group': True})\n"
    )
    lines = _census(tmp_path, {"channel.py": KIND, "use.py": use})
    assert [line for line in lines if "Channel SM-LIFECYCLE-FLAGS" in line], lines


@pytest.mark.spec("PIPE-GATES-R086.27")
def test_a_flag_assigned_through_a_receiver_that_does_not_resolve_stays_a_lifecycle(tmp_path: Path) -> None:
    use = "def lock(thing) -> None:\n    thing.is_dm = True\n    thing.is_group = True\n"
    lines = _census(tmp_path, {"channel.py": KIND, "use.py": use})
    assert [line for line in lines if "Channel SM-LIFECYCLE-FLAGS" in line], lines


ROLLUP = HEALTH + "\n\ndef rollup(items: list[str]) -> Health:\n    return Health.UP if items else Health.DOWN\n"


@pytest.mark.spec("PIPE-GATES-R086.28")
def test_a_status_only_recomputed_and_copied_is_a_derived_rollup(tmp_path: Path) -> None:
    use = (
        "\n\ndef mark(e: Evidence, items: list[str]) -> Evidence:\n    status = rollup(items)\n"
        '    return e.model_copy(update={"status": status, "ready": status == Health.UP})\n'
    )
    lines = _census(tmp_path, {"health.py": ROLLUP + use})
    assert not [line for line in lines if "SM-NO-DECLARATION" in line], lines


@pytest.mark.spec("PIPE-GATES-R086.28")
def test_a_status_replaced_by_a_constant_is_still_a_lifecycle(tmp_path: Path) -> None:
    use = '\n\ndef stop(e: Evidence) -> Evidence:\n    return e.model_copy(update={"status": Health.DOWN})\n'
    lines = _census(tmp_path, {"health.py": ROLLUP + use})
    assert [line for line in lines if "Evidence SM-NO-DECLARATION" in line], lines


@pytest.mark.spec("PIPE-GATES-R086.28")
def test_a_recomputed_replacement_that_guards_on_the_current_status_is_still_a_lifecycle(tmp_path: Path) -> None:
    use = (
        "\n\ndef mark(e: Evidence, items: list[str]) -> Evidence:\n"
        '    if e.status == Health.DOWN:\n        return e\n    return e.model_copy(update={"status": rollup(items)})\n'
    )
    lines = _census(tmp_path, {"health.py": ROLLUP + use})
    assert [line for line in lines if "Evidence SM-NO-DECLARATION" in line], lines


@pytest.mark.spec("PIPE-GATES-R086.28")
def test_a_status_that_one_function_assigns_in_place_is_still_a_lifecycle(tmp_path: Path) -> None:
    use = (
        "\n\ndef mark(e: Evidence, items: list[str]) -> Evidence:\n"
        '    again = e.model_copy(update={"status": rollup(items)})\n    return again\n\n\n'
        "def force(e: Evidence, items: list[str]) -> None:\n    e.status = rollup(items)\n"
    )
    lines = _census(tmp_path, {"health.py": ROLLUP + use})
    assert [line for line in lines if "Evidence SM-NO-DECLARATION" in line], lines


@pytest.mark.spec("PIPE-GATES-R086.20")
def test_two_comprehensions_that_reuse_a_variable_name_do_not_clash(tmp_path: Path) -> None:
    use = (
        "class Note:\n    text: str\n\n\n"
        'def f(notes: list[Note], jobs: list[Job]) -> bool:\n    names = [i.text for i in notes]\n    return any(i.status == "x" for i in jobs) and bool(names)\n'
    )
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert _attributed(lines, "jobs.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.21")
def test_a_field_stored_from_an_annotated_constructor_parameter_has_that_type(tmp_path: Path) -> None:
    service = (
        "from pkg.holder import Holder\n\n\nclass Service:\n    def __init__(self, holder: Holder) -> None:\n"
        '        self._holder = holder\n\n    def ready(self) -> bool:\n        return self._holder.inner.status == "open"\n'
    )
    lines = _census(tmp_path, {"jobs.py": JOB, "holder.py": HOLDER, "service.py": service})
    assert _attributed(lines, "service.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.21")
def test_a_class_imported_inside_a_function_resolves(tmp_path: Path) -> None:
    use = 'def f() -> bool:\n    from pkg.loader import load\n\n    return load().status == "open"\n'
    loader = "from pkg.jobs import Job\n\n\ndef load() -> Job:\n    return Job()\n"
    lines = _census(tmp_path, {"jobs.py": JOB, "loader.py": loader, "use.py": use})
    assert _attributed(lines, "use.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.25")
def test_an_iterable_annotation_gives_the_element_type(tmp_path: Path) -> None:
    use = 'def f(jobs: Iterable[Job]) -> bool:\n    return all(j.status != "x" for j in jobs)\n'
    lines = _census(tmp_path, {"jobs.py": "from collections.abc import Iterable\n\n\n" + JOB + "\n\n" + use})
    assert _attributed(lines, "jobs.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.23")
def test_a_field_chain_through_a_union_takes_the_field_type_of_the_arms(tmp_path: Path) -> None:
    use = (
        "class Left:\n    inner: Job\n\n\nclass Right:\n    inner: Job\n\n\n"
        'def f(x: Left | Right) -> bool:\n    return x.inner.status == "open"\n'
    )
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert _attributed(lines, "jobs.py"), lines
    assert not _unresolved(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.26")
def test_a_local_assigned_a_comprehension_has_the_type_of_its_element_expression(tmp_path: Path) -> None:
    use = (
        "def make(n: int) -> Job:\n    return Job()\n\n\n"
        'def f(sizes: list[int]) -> bool:\n    records = [make(n) for n in sizes]\n    return any(r.status == "open" for r in records)\n'
    )
    lines = _census(tmp_path, {"jobs.py": JOB + "\n\n" + use})
    assert _attributed(lines, "jobs.py"), lines
    assert not _unresolved(lines), lines
