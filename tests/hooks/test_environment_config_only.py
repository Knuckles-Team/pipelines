"""PIPE-GATES-R089: an environment repository holds no custom code."""

import pytest

from tests.hooks.conftest import Repo

DECLARED = "[tool.pipelines_hooks.environment_config_only]\ndeclared = true\n"
THIN = '#!/bin/sh\n# render the stack\nset -eu\nexec arbora render --config ./stack.yml "$@"\n'
LOOP = '#!/bin/sh\nfor f in *.yml; do\n  arbora apply "$f"\ndone\n'


def _stage(repo: Repo, files: dict[str, str], executable: tuple[str, ...] = ()) -> None:
    repo.stage(files)
    for rel in executable:
        (repo.root / rel).chmod(0o755)
        repo.git("update-index", "--chmod=+x", "--", rel)


# spec: PIPE-GATES-R089
def test_only_behaviour_scripts_are_findings(repo, capsys):
    _stage(
        repo,
        {
            "pyproject.toml": DECLARED,
            "bin/render": THIN,
            "bin/reconcile": LOOP,
            "values.yaml": "replicas: 2\n",
        },
        executable=("bin/render", "bin/reconcile"),
    )
    assert repo.run("environment-config-only") == 1
    out = capsys.readouterr().out
    assert "bin/reconcile:" in out and "control flow at line 2" in out
    assert "bin/render" not in out and "values.yaml" not in out


# spec: PIPE-GATES-R089
@pytest.mark.parametrize(
    "script,needle",
    [
        ("#!/bin/sh\nif [ -f x ]; then arbora a; fi\n", "control flow"),
        ("#!/bin/sh\ntest -f x && arbora a\n", "control flow"),
        ("#!/bin/sh\nrun() {\n  arbora a\n}\n", "control flow"),
        ("#!/bin/sh\n" + "arbora step\n" * 13, "over the 12 line bound"),
        ("#!/usr/bin/env python3\nfor x in range(2):\n    print(x)\n", "For at line 2"),
        ("#!/usr/bin/env python3\ndef f():\n    pass\n", "FunctionDef at line 2"),
    ],
)
def test_behaviour_encoding_scripts_fail(repo, capsys, script, needle):
    _stage(repo, {"pyproject.toml": DECLARED, "tools/x": script}, executable=("tools/x",))
    assert repo.run("environment-config-only") == 1
    assert needle in capsys.readouterr().out


# spec: PIPE-GATES-R089
def test_python_thin_wrapper_and_shebang_without_bit(repo, capsys):
    thin = "#!/usr/bin/env python3\nimport subprocess\nsubprocess.run(['arbora', 'render'], check=True)\n"
    _stage(repo, {"pyproject.toml": DECLARED, "bin/thin": thin, "bin/loop": "#!/bin/bash\nwhile true; do :; done\n"})
    assert repo.run("environment-config-only") == 1
    out = capsys.readouterr().out
    assert "bin/loop:" in out and "bin/thin" not in out


# spec: PIPE-GATES-R089
def test_data_only_and_test_scripts_pass(repo):
    _stage(
        repo,
        {
            "pyproject.toml": DECLARED,
            "config/app.yaml": "a: 1\n",
            "compose.yml": "services: {}\n",
            "tests/check.sh": LOOP,
        },
        executable=("tests/check.sh",),
    )
    assert repo.run("environment-config-only") == 0


# spec: PIPE-GATES-R089
def test_non_environment_repository_is_not_checked(repo):
    _stage(repo, {"pyproject.toml": "[tool.pipelines_hooks]\n", "bin/x": LOOP}, executable=("bin/x",))
    assert repo.run("environment-config-only") == 0


# spec: PIPE-GATES-R089
def test_bad_declaration_refuses(repo):
    _stage(repo, {"pyproject.toml": '[tool.pipelines_hooks.environment_config_only]\ndeclared = "yes"\n'})
    assert repo.run("environment-config-only") == 2
