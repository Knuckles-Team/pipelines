"""PIPE-GATES-R091, R092, R093: the generic Rust workspace checks."""

from __future__ import annotations

import datetime as dt

from pipelines_hooks.rust import cargo_advisories

MANIFEST = '[package]\nname = "a"\nversion = "0.1.0"\nedition = "2021"\n'


# spec: PIPE-GATES-R091
def test_crates_io_only_passes_a_registry_only_tree(repo):
    repo.commit({"Cargo.toml": MANIFEST + '[dependencies]\nserde = "1"\n', "Cargo.lock": 'source = "registry+x"\n'})
    assert repo.run("crates-io-only") == 0


# spec: PIPE-GATES-R091
def test_crates_io_only_rejects_git_escaping_path_and_locked_git_source(repo):
    repo.commit({"crates/a/Cargo.toml": MANIFEST + '[dependencies]\nx = { git = "https://example.org/x" }\n'})
    assert repo.run("crates-io-only") == 1
    repo.commit({"crates/a/Cargo.toml": MANIFEST + '[dev-dependencies]\nx = { path = "../../../outside" }\n'})
    assert repo.run("crates-io-only") == 1
    repo.commit(
        {
            "crates/a/Cargo.toml": MANIFEST + '[dependencies]\nx = { path = "../b" }\n',
            "Cargo.lock": 'source = "git+https://e/x"\n',
        }
    )
    assert repo.run("crates-io-only") == 1


# spec: PIPE-GATES-R092
def test_rustfmt_scope_ignores_changes_without_rust(repo):
    repo.commit({"README.md": "x\n"})
    assert repo.run("rustfmt-scope", "README.md") == 0
    assert repo.run("rustfmt-scope") == 0


# spec: PIPE-GATES-R092
def test_rustfmt_scope_refuses_paths_outside_the_checkout(repo):
    assert repo.run("rustfmt-scope", "../x.rs") == 2
    assert repo.run("rustfmt-scope", "/abs/x.rs") == 2


# spec: PIPE-GATES-R092
def test_rustfmt_scope_requires_an_exact_pinned_channel(repo):
    repo.commit(
        {
            "Cargo.toml": MANIFEST,
            "src/lib.rs": "fn main(){}\n",
            "rust-toolchain.toml": '[toolchain]\nchannel = "stable"\n',
        }
    )
    assert repo.run("rustfmt-scope", "src/lib.rs") == 2


# spec: PIPE-GATES-R093
def test_ledger_and_ignores_must_agree(tmp_path):
    today = dt.date(2026, 11, 7)
    deny = tmp_path / "deny.toml"
    deny.write_text('[advisories]\nignore = ["RUSTSEC-2026-0001", { id = "RUSTSEC-2026-0002", reason = "r" }]\n')
    ids, problems = cargo_advisories.ignored_ids(deny)
    assert ids == {"RUSTSEC-2026-0001", "RUSTSEC-2026-0002"} and not problems
    ledger = tmp_path / "ledger.txt"
    ledger.write_text(
        "RUSTSEC-2026-0001 expires=2026-12-01 # reviewed upstream fix pending\n"
        "RUSTSEC-2026-0009 expires=2026-12-01 # reviewed upstream fix pending\n"
    )
    accepted, ledger_problems = cargo_advisories.read_ledger(ledger, today, 90)
    assert not ledger_problems
    found = cargo_advisories.cross_check(ids, accepted, deny, ledger)
    assert len(found) == 2 and any("RUSTSEC-2026-0002" in f for f in found) and any("stale" in f for f in found)


# spec: PIPE-GATES-R093
def test_ledger_rejects_expired_unjustified_and_far_horizon_lines(tmp_path):
    ledger = tmp_path / "ledger.txt"
    ledger.write_text(
        "RUSTSEC-2026-0001 expires=2026-01-01 # reviewed upstream fix pending\n"
        "RUSTSEC-2026-0002 expires=2026-12-01 # short\n"
        "RUSTSEC-2026-0003 expires=2027-12-01 # reviewed upstream fix pending\n"
    )
    accepted, problems = cargo_advisories.read_ledger(ledger, dt.date(2026, 11, 7), 90)
    assert not accepted and len(problems) == 3


# spec: PIPE-GATES-R093
def test_missing_version_pin_is_a_configuration_error(repo):
    repo.commit({"pyproject.toml": "[tool.pipelines_hooks.cargo_advisories]\n"})
    assert repo.run("cargo-advisories") == 2
