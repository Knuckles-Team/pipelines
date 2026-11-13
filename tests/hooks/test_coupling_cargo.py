"""PIPE-GATES-R088.2: Cargo crate layers in the coupling gate."""

POLICY = """[tool.pipelines_hooks.coupling]
[[tool.pipelines_hooks.coupling.cargo_layers]]
name = "core"
units = ["base"]
[[tool.pipelines_hooks.coupling.cargo_layers]]
name = "engine"
units = ["engine", "store"]
[[tool.pipelines_hooks.coupling.cargo_layers]]
name = "edge"
units = ["server"]
"""

WORKSPACE = '[workspace]\nmembers = ["crates/*"]\n[workspace.dependencies]\nbase-alias = { package = "server", path = "crates/server" }\n'


def _crate(name: str, body: str = "") -> str:
    return f'[package]\nname = "{name}"\nversion = "0.1.0"\n\n{body}'


def _workspace(repo, crates: dict[str, str], policy: str = POLICY) -> None:
    files = {"pyproject.toml": policy, "Cargo.toml": WORKSPACE}
    names = {"base": "", "engine": "", "store": "", "server": ""} | crates
    files |= {f"crates/{name}/Cargo.toml": _crate(name, body) for name, body in names.items()}
    repo.stage(files)


# spec: PIPE-GATES-R088.2
def test_upward_crate_dependency_is_reported(repo, capsys):
    _workspace(repo, {"server": '[dependencies]\nengine = { path = "../engine" }\nbase = { path = "../base" }\n'})
    assert repo.run("coupling") == 0
    _workspace(repo, {"base": '[dependencies]\n\nengine = { path = "../engine" }\n'})
    assert repo.run("coupling") == 1
    out = capsys.readouterr().out
    assert "crates/base/Cargo.toml:7: COUPLING-UPWARD-CRATE base (core) depends on engine (engine)" in out


# spec: PIPE-GATES-R088.2
def test_renamed_dependency_resolves_to_its_package(repo, capsys):
    _workspace(repo, {"engine": '[dependencies]\nfront = { package = "server", path = "../server" }\n'})
    assert repo.run("coupling") == 1
    assert "COUPLING-UPWARD-CRATE engine (engine) depends on server (edge)" in capsys.readouterr().out
    _workspace(repo, {"engine": "[dependencies]\nbase-alias = { workspace = true }\n"})
    assert repo.run("coupling") == 1
    assert "COUPLING-UPWARD-CRATE engine (engine) depends on server (edge)" in capsys.readouterr().out


# spec: PIPE-GATES-R088.2
def test_target_and_build_dependencies_are_read(repo, capsys):
    _workspace(repo, {"base": "[target.'cfg(unix)'.dependencies]\nstore = { path = \"../store\" }\n"})
    assert repo.run("coupling") == 1
    assert "base (core) depends on store (engine)" in capsys.readouterr().out
    _workspace(repo, {"base": '[build-dependencies]\nserver = { path = "../server" }\n'})
    assert repo.run("coupling") == 1
    assert "base (core) depends on server (edge)" in capsys.readouterr().out


# spec: PIPE-GATES-R088.2
def test_dev_dependencies_are_not_layered(repo):
    _workspace(repo, {"base": '[dev-dependencies]\nserver = { path = "../server" }\n'})
    assert repo.run("coupling") == 0


# spec: PIPE-GATES-R088.2
def test_unlayered_member_and_peer_cycle_are_reported(repo, capsys):
    _workspace(
        repo,
        {
            "extra": "",
            "engine": '[dependencies]\nstore = { path = "../store" }\n',
            "store": '[dependencies]\nengine = { path = "../engine" }\n',
        },
    )
    assert repo.run("coupling") == 1
    out = capsys.readouterr().out
    assert "crates/extra/Cargo.toml:1: COUPLING-UNLAYERED-CRATE extra" in out
    assert "COUPLING-CRATE-CYCLE among crates engine, store" in out


# spec: PIPE-GATES-R088.2
def test_cargo_layer_policy_fault_exits_two(repo):
    bad = '[tool.pipelines_hooks.coupling]\ncargo_layers = [{ name = "core", units = [] }]\n'
    _workspace(repo, {}, policy=bad)
    assert repo.run("coupling") == 2
    twice = POLICY + '[[tool.pipelines_hooks.coupling.cargo_layers]]\nname = "again"\nunits = ["base"]\n'
    _workspace(repo, {}, policy=twice)
    assert repo.run("coupling") == 2
