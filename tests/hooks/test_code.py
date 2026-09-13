"""The code-shape gates fire on planted violations and pass clean fixtures."""

from __future__ import annotations

from tests.hooks.conftest import PYPROJECT, Repo

UNIMPLEMENTED = "raise " + "NotImplementedError"


def test_no_stub_fires_on_an_unmarked_raise_and_accepts_abstract_and_declared_seams(repo: Repo) -> None:
    repo.commit({"pkg/port.py": f"def call():\n    {UNIMPLEMENTED}\n"})
    assert repo.run("no-stub") == 1
    abstract = f"from abc import abstractmethod\n\n\nclass Port:\n    @abstractmethod\n    def call(self):\n        {UNIMPLEMENTED}\n"
    repo.commit({"pkg/port.py": abstract})
    assert repo.run("no-stub") == 0
    seams = PYPROJECT + '\n[tool.pipelines_hooks.stubs]\ndeclared_seams = { "pkg/sink.py" = ["PENDING"] }\n'
    repo.commit({"pyproject.toml": seams, "pkg/sink.py": f"PENDING = 'wave'\n\n\ndef ingest():\n    {UNIMPLEMENTED}(PENDING)\n"})
    assert repo.run("no-stub") == 0


def test_stubs_fires_on_an_empty_body_and_a_deferred_work_comment(repo: Repo) -> None:
    repo.commit({"pkg/real.py": "def real(value):\n    return value * 2\n"})
    assert repo.run("stubs") == 0
    repo.commit({"pkg/empty.py": "def empty():\n    pass\n"})
    assert repo.run("stubs") == 1
    repo.commit({"pkg/empty.py": "def empty():\n    return None  # " + "TO" + "DO wire the cache\n"})
    assert repo.run("stubs") == 1


def test_swallowed_errors_fires_on_an_added_silent_handler_and_accepts_logged_cause(repo: Repo) -> None:
    logged = "import logging\nlog = logging.getLogger(__name__)\n\n\ndef f():\n    try:\n        return 1\n    except OSError as exc:\n        log.warning('failed: %s', exc)\n"
    repo.commit({"pkg/io.py": logged})
    assert repo.run("swallowed-errors") == 0
    repo.write("pkg/io.py", logged + "\n\ndef g():\n    try:\n        return 2\n    except Exception:\n        pass\n")
    assert repo.run("swallowed-errors") == 1


def test_swallowed_errors_holds_bare_except_at_an_absolute_zero(repo: Repo) -> None:
    repo.commit({"pkg/bare.py": "def f():\n    try:\n        return 1\n    except:\n        raise\n"})
    assert repo.run("swallowed-errors") == 1


def test_event_loop_blocking_fires_on_time_sleep_and_accepts_a_thread_hop(repo: Repo) -> None:
    hopped = "import asyncio\n\n\nasync def f(path):\n    def read():\n        return open(path).read()\n    return await asyncio.to_thread(read)\n"
    repo.commit({"pkg/aio.py": hopped})
    assert repo.run("event-loop-blocking") == 0
    repo.commit({"pkg/aio.py": hopped + "\n\nasync def g():\n    import time\n    time.sleep(1)\n"})
    assert repo.run("event-loop-blocking") == 1


def test_import_cycles_fires_on_an_eager_cycle_and_ignores_type_checking_imports(repo: Repo) -> None:
    repo.commit({"pkg/a.py": "from pkg import b\n", "pkg/b.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from pkg import a\n"})
    assert repo.run("import-cycles") == 0
    repo.commit({"pkg/b.py": "from pkg import a\n"})
    assert repo.run("import-cycles") == 1


def test_env_sprawl_fires_outside_the_declared_configuration_module(repo: Repo) -> None:
    allowed = PYPROJECT + '\n[tool.pipelines_hooks.env_sprawl]\nallow_files = ["pkg/config.py"]\n'
    repo.commit({"pyproject.toml": allowed, "pkg/config.py": "import os\nMODE = os.environ.get('MODE')\n"})
    assert repo.run("env-sprawl") == 0
    repo.commit({"pkg/other.py": "import os\nMODE = os.getenv('MODE')\n"})
    assert repo.run("env-sprawl") == 1


def test_stdout_writes_fires_on_print_in_the_served_surface(repo: Repo) -> None:
    served = PYPROJECT + '\n[tool.pipelines_hooks.stdout_writes]\nserved_paths = ["pkg"]\n'
    repo.commit({"pyproject.toml": served, "pkg/serve.py": "import sys\n\n\ndef log(m):\n    print(m, file=sys.stderr)\n"})
    assert repo.run("stdout-writes") == 0
    repo.commit({"pkg/serve.py": "def log(m):\n    print(m)\n"})
    assert repo.run("stdout-writes") == 1
