"""pr-test-scope: an unmapped source change narrows via the import graph, not FULL."""

from __future__ import annotations

import pytest

from tests.hooks.conftest import Repo


def test_unmapped_module_selects_only_its_importers(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit(
        {
            "pkg/mod_a.py": "def helper() -> int:\n    return 1\n",
            "tests/test_importer.py": "from pkg import mod_a\n\n\ndef test_helper() -> None:\n    assert mod_a.helper() == 1\n",
            "tests/test_unrelated.py": "def test_noop() -> None:\n    assert True\n",
        },
        "baseline",
    )
    repo.commit({"pkg/mod_a.py": "def helper() -> int:\n    return 2\n"}, "change mod_a")

    assert repo.run("pr-test-scope", "--base-ref", base, "--src-root", "pkg", "--tests-root", "tests") == 0
    out = capsys.readouterr().out.splitlines()

    # pkg/mod_a.py has no mirrored tests/test_mod_a.py, so this exercises the
    # import-graph fallback: only the test that actually imports pkg.mod_a is
    # selected, not the full suite and not the unrelated test file.
    assert out == ["tests/test_importer.py"]


def test_unmapped_module_with_no_importers_selects_nothing(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit(
        {
            "pkg/orphan.py": "def helper() -> int:\n    return 1\n",
            "tests/test_unrelated.py": "def test_noop() -> None:\n    assert True\n",
        },
        "baseline",
    )
    repo.commit({"pkg/orphan.py": "def helper() -> int:\n    return 2\n"}, "change orphan")

    assert repo.run("pr-test-scope", "--base-ref", base, "--src-root", "pkg", "--tests-root", "tests") == 0
    out = capsys.readouterr().out.splitlines()

    # Nothing imports pkg.orphan: the gate trusts the graph (NONE) rather
    # than forcing FULL, since this is not an unreadable diff.
    assert out == ["NONE"]


def test_conftest_change_still_forces_full_suite(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit(
        {
            "pkg/mod_a.py": "def helper() -> int:\n    return 1\n",
            "tests/test_importer.py": "from pkg import mod_a\n\n\ndef test_helper() -> None:\n    assert mod_a.helper() == 1\n",
            "tests/conftest.py": "import pytest\n",
        },
        "baseline",
    )
    repo.commit(
        {"tests/conftest.py": "import pytest\n\n\ndef pytest_configure(config):\n    pass\n"}, "change conftest"
    )

    assert repo.run("pr-test-scope", "--base-ref", base, "--src-root", "pkg", "--tests-root", "tests") == 0
    out = capsys.readouterr().out.splitlines()

    assert out == ["FULL"]


def test_many_unmapped_modules_scan_the_tree_once(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from pipelines_hooks.ci_replica import import_graph

    names = [f"mod_{index}" for index in range(5)]
    base = repo.commit(
        {
            **{f"pkg/{name}.py": "VALUE = 1\n" for name in names},
            "tests/test_importer.py": "from pkg import mod_0\n\n\ndef test_value() -> None:\n    assert mod_0.VALUE\n",
        },
        "baseline",
    )
    repo.commit({f"pkg/{name}.py": "VALUE = 2\n" for name in names}, "change all")
    scans: list[object] = []
    real = import_graph.build_import_graph

    def counting(*args: object) -> object:
        scans.append(args)
        return real(*args)

    monkeypatch.setattr(import_graph, "build_import_graph", counting)

    assert repo.run("pr-test-scope", "--base-ref", base, "--src-root", "pkg", "--tests-root", "tests") == 0
    assert capsys.readouterr().out.splitlines() == ["tests/test_importer.py"]
    # A large diff of unmirrored modules used to rescan the tree per module.
    assert len(scans) == 1


def test_scope_never_names_non_test_modules(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit(
        {
            "pkg/mod_a.py": "def helper() -> int:\n    return 1\n",
            "tests/sub/__init__.py": "",
            "tests/sub/catalog_fixture.py": "from pkg import mod_a\n",
            "tests/sub/test_importer.py": "from pkg import mod_a\n\n\ndef test_helper() -> None:\n    assert mod_a.helper() == 1\n",
        },
        "baseline",
    )
    repo.commit({"pkg/mod_a.py": "def helper() -> int:\n    return 2\n"}, "change mod_a")

    assert repo.run("pr-test-scope", "--base-ref", base, "--src-root", "pkg", "--tests-root", "tests") == 0
    # A helper module named as a pytest argument is imported as a test module and
    # shadows its sibling conftest fixtures; only collectable test files are named.
    assert capsys.readouterr().out.splitlines() == ["tests/sub/test_importer.py"]


@pytest.mark.parametrize(
    ("language", "changed", "expected"),
    [
        (
            "rust",
            [
                "crates/a/src/lib.rs",
                "crates/a/src/extra.rs",
                "crates/b/src/lib.rs",
                "tests/test_python.py",
                "README.md",
            ],
            ["eg-transaction", "other_crate"],
        ),
        (
            "python",
            [
                "tests/test_python.py",
                "tests/other_test.py",
                "tests/helper.py",
                "tests/__init__.py",
                "crates/a/src/lib.rs",
            ],
            ["tests/other_test.py", "tests/test_python.py"],
        ),
        ("rust", [], ["NONE"]),
        ("python", [], ["NONE"]),
        ("rust", ["README.md", "tests/test_python.py"], ["NONE"]),
        ("python", ["README.md", "crates/a/src/lib.rs"], ["NONE"]),
        ("rust", ["Cargo.lock"], ["FULL"]),
        ("rust", ["unmapped.rs"], ["FULL"]),
    ],
)
def test_language_selection_preserves_names_and_ignores_unrelated_changes(
    repo: Repo,
    capsys: pytest.CaptureFixture[str],
    language: str,
    changed: list[str],
    expected: list[str],
) -> None:
    base = repo.commit(
        {
            "crates/a/Cargo.toml": '[package]\nname = "eg-transaction"\n',
            "crates/b/Cargo.toml": '[package]\nname = "other_crate"\n',
            "README.md": "baseline\n",
        },
        "workspace baseline",
    )
    if changed:
        repo.commit({path: "# changed\n" for path in changed}, "mixed changes")
    assert repo.run("pr-test-scope", "--base-ref", base, "--lang", language) == 0
    assert capsys.readouterr().out.splitlines() == expected


_ROOT_MANIFEST = '[workspace]\nmembers = ["crates/a"]\n\n[workspace.package]\nversion = "{v}"\n'
_MEMBER_MANIFEST = (
    '[package]\nname = "eg-transaction"\nversion = "{v}"\n\n'
    '[dependencies]\nother_crate = {{ path = "../b", version = "{v}" }}\nserde = "1.0.{serde}"\n'
)
_LOCK = (
    'version = 4\n\n[[package]]\nname = "eg-transaction"\nversion = "{v}"\n'
    'dependencies = [\n "serde",\n]\n\n[[package]]\nname = "serde"\nversion = "1.0.{serde}"\n'
    'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
)


def _workspace(v: str, serde: int = 200) -> dict[str, str]:
    return {
        "Cargo.toml": _ROOT_MANIFEST.format(v=v),
        "crates/a/Cargo.toml": _MEMBER_MANIFEST.format(v=v, serde=serde),
        "Cargo.lock": _LOCK.format(v=v, serde=serde),
    }


def test_a_release_version_bump_forces_no_crate_sweep(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    # spec: PIPE-RELEASE-R007.7
    base = repo.commit(_workspace("2.27.4"), "workspace baseline")
    repo.commit(_workspace("2.27.5"), "release bump")
    assert repo.run("pr-test-scope", "--base-ref", base, "--lang", "rust") == 0
    assert capsys.readouterr().out.splitlines() == ["NONE"]


def test_a_registry_dependency_bump_still_forces_the_full_sweep(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    # spec: PIPE-RELEASE-R007.7
    base = repo.commit(_workspace("2.27.4"), "workspace baseline")
    repo.commit(_workspace("2.27.4", serde=201), "dependency bump")
    assert repo.run("pr-test-scope", "--base-ref", base, "--lang", "rust") == 0
    assert capsys.readouterr().out.splitlines() == ["FULL"]


def test_a_member_manifest_change_beyond_versions_maps_to_its_crate(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    # spec: PIPE-RELEASE-R007.7
    base = repo.commit(_workspace("2.27.4"), "workspace baseline")
    manifest = _MEMBER_MANIFEST.format(v="2.27.4", serde=200) + 'anyhow = "1"\n'
    repo.commit({"crates/a/Cargo.toml": manifest}, "new dependency")
    assert repo.run("pr-test-scope", "--base-ref", base, "--lang", "rust") == 0
    assert capsys.readouterr().out.splitlines() == ["eg-transaction"]
