"""Real Git cases for evidence withdrawal, including feature-change abuse."""

import pytest

from tests.hooks.conftest import Repo
from tests.hooks.test_spec_trailers import _requirements_md

RID = "DEMO-R001"
REASON = "Refusal tests do not prove the required successful query."
SOURCE = "// spec: DEMO-R001\n#[test]\nfn refusal() { assert!(true); }\n"
REPLACEMENT = "// Partial refusal coverage for DEMO-R001; successful-operation acceptance remains open.\n"


def setup(repo: Repo) -> str:
    return repo.commit(
        {
            "specs/demo/requirements.md": _requirements_md(RID) + "| `DEMO-R002` | Other thing. | Needs a test. |\n",
            "specs/demo/plan.md": "# Plan\n",
            "specs/demo/tasks.md": "- [x] **DEMO-R001:** query\n",
            "src/query.rs": SOURCE,
        },
        "baseline\n\nSpec: DEMO-R001",
    )


def correction(
    repo: Repo,
    extra: dict[str, str] | None = None,
    reason: str = REASON,
    ids: str = RID,
) -> None:
    files = {
        "src/query.rs": SOURCE.replace("// spec: DEMO-R001\n", REPLACEMENT),
        "specs/demo/plan.md": f"# Plan\n\n{RID}: {REASON}\n",
        "specs/demo/tasks.md": "- [ ] **DEMO-R001:** query\n",
    }
    files.update(extra or {})
    repo.commit(
        files,
        f"withdraw evidence\n\nSpec: {RID}\nSpec-Withdraw: {ids}\nSpec-Withdrawal-Reason: {reason}",
    )


# spec: PIPE-CONNSPEC-R001
@pytest.mark.parametrize("replacement", [REPLACEMENT, ""])
def test_withdrawal_keeps_requirements_and_tests(repo: Repo, replacement: str) -> None:
    base = setup(repo)
    correction(repo, {"src/query.rs": SOURCE.replace("// spec: DEMO-R001\n", replacement)})
    assert repo.run("spec-trailers", "--base-ref", base) == 0
    assert repo.run("spec-status", "--write") == 0
    assert '"delivery_state": "LANDED"' in (repo.root / "specs/demo/status.json").read_text()


# spec: PIPE-CONNSPEC-R001
@pytest.mark.parametrize(
    "extra",
    [
        {"src/query.rs": SOURCE.replace("// spec: DEMO-R001\n", "").replace("true", "false")},
        {"Cargo.toml": '[package]\nname = "new-feature"\n'},
        {".github/workflows/ci.yml": "disabled: true\n"},
        {"specs/demo/requirements.md": _requirements_md(RID).replace("Verified by a test", "No tests needed")},
        {"specs/demo/plan.md": f"{RID}: {REASON}\n"},
        {"specs/demo/tasks.md": "- [ ] **DEMO-R001:** weaker requirement\n"},
        {"src/query.rs": SOURCE},
        {"src/other.rs": "// spec: DEMO-R001\n#[test]\nfn retained() {}\n"},
    ],
)
def test_withdrawal_refuses_non_evidence_changes(repo: Repo, extra: dict[str, str]) -> None:
    base = setup(repo)
    correction(repo, extra)
    assert repo.run("spec-trailers", "--base-ref", base) == 1


# spec: PIPE-CONNSPEC-R001
@pytest.mark.parametrize(
    ("ids", "reason"),
    [(RID, ""), (RID, "short"), ("", REASON), ("UNKNOWN-R002", REASON)],
)
def test_withdrawal_requires_known_ids_and_reason(repo: Repo, ids: str, reason: str) -> None:
    base = setup(repo)
    correction(repo, ids=ids, reason=reason)
    assert repo.run("spec-trailers", "--base-ref", base) == 1


def test_withdrawal_requires_plan_reason(repo: Repo) -> None:
    base = setup(repo)
    correction(repo, {"specs/demo/plan.md": "# Plan\n"})
    assert repo.run("spec-trailers", "--base-ref", base) == 1


def test_later_declaration_validates_entire_range(repo: Repo) -> None:
    base = setup(repo)
    repo.commit(
        {"src/query.rs": SOURCE.replace("// spec: DEMO-R001\n", "")},
        "correction\n\nSpec: DEMO-R001",
    )
    correction(repo)
    assert repo.run("spec-trailers", "--base-ref", base) == 0


def test_ordinary_unbound_id_still_fails(repo: Repo) -> None:
    base = setup(repo)
    correction(repo)
    repo.git("commit", "--allow-empty", "-m", "feature\n\nSpec: DEMO-R002")
    assert repo.run("spec-trailers", "--base-ref", base) == 1


def test_changed_file_mode_is_not_evidence(repo: Repo) -> None:
    base = setup(repo)
    correction(repo)
    repo.git("update-index", "--chmod=+x", "src/query.rs")
    repo.git("commit", "-m", "change mode\n\nSpec: DEMO-R001")
    assert repo.run("spec-trailers", "--base-ref", base) == 1


def test_withdrawal_cannot_claim_never_bound_id(repo: Repo) -> None:
    base = setup(repo)
    correction(repo)
    repo.git(
        "commit",
        "--allow-empty",
        "-m",
        f"claim other ID\n\nSpec: DEMO-R002\nSpec-Withdraw: DEMO-R002\nSpec-Withdrawal-Reason: {REASON}",
    )
    assert repo.run("spec-trailers", "--base-ref", base) == 1


def test_withdrawal_keeps_literal_newline_bytes(repo: Repo) -> None:
    setup(repo)
    source = repo.root / "src/query.rs"
    source.write_bytes((SOURCE + 'const S: &str = "a\r\nb";\n').encode())
    repo.git("add", "src/query.rs")
    repo.git("commit", "-m", "literal baseline")
    base = repo.git("rev-parse", "HEAD").strip()
    correction(
        repo,
        {"src/query.rs": SOURCE.replace("// spec: DEMO-R001\n", "") + 'const S: &str = "a\nb";\n'},
    )
    assert repo.run("spec-trailers", "--base-ref", base) == 1


def test_withdrawal_must_retain_spec_trailer(repo: Repo) -> None:
    base = setup(repo)
    repo.commit(
        {
            "src/query.rs": SOURCE.replace("// spec: DEMO-R001\n", ""),
            "specs/demo/plan.md": f"# Plan\n{RID}: {REASON}\n",
        },
        f"withdraw\n\nSpec: none (correction)\nSpec-Withdraw: {RID}\nSpec-Withdrawal-Reason: {REASON}",
    )
    assert repo.run("spec-trailers", "--base-ref", base) == 1


NEVER = "DEMO-R002"
NEVER_REASON = "The proving member was ejected from the batch; acceptance stays open."
NEVER_TASKS = "- [x] T001 DEMO-R001 query\n- [ ] T002 DEMO-R002 other thing\n"


def never_bound_batch(repo: Repo, proof: str = "") -> str:
    """A batch whose DEMO-R002 delivery landed but whose proving member was reverted."""
    base = setup(repo)
    repo.commit({"specs/demo/tasks.md": NEVER_TASKS}, "standard task lines\n\nSpec: DEMO-R001")
    repo.commit({"src/other.rs": "pub fn other() {}\n" + proof}, f"deliver other thing\n\nSpec: {NEVER}")
    member = repo.commit(
        {"src/other_test.rs": f"// spec: {NEVER}\n#[test]\nfn other() {{}}\n"}, f"prove other thing\n\nSpec: {NEVER}"
    )
    repo.git("revert", "--no-edit", member)
    return base


def never_bound_withdrawal(repo: Repo, extra: dict[str, str] | None = None) -> None:
    files = {"specs/demo/plan.md": f"# Plan\n\n{NEVER}: {NEVER_REASON}\n"}
    files.update(extra or {})
    repo.commit(
        files,
        f"withdraw never-bound evidence\n\nSpec: {NEVER}\nSpec-Withdraw: {NEVER}\nSpec-Withdrawal-Reason: {NEVER_REASON}",
    )


# spec: PIPE-CONNSPEC-R001.2
@pytest.mark.parametrize(
    "tasks",
    [NEVER_TASKS, NEVER_TASKS.replace("- [ ] T002", "- [x] T002")],
    ids=["already-open", "reopened"],
)
def test_never_bound_withdrawal_passes(repo: Repo, tasks: str) -> None:
    base = never_bound_batch(repo)
    if tasks != NEVER_TASKS:
        repo.commit({"specs/demo/tasks.md": tasks}, "check the task early\n\nSpec: none (task tracking)")
    never_bound_withdrawal(repo, {"specs/demo/tasks.md": NEVER_TASKS})
    assert repo.run("spec-trailers", "--base-ref", base) == 0


# spec: PIPE-CONNSPEC-R001.2
def test_plan_only_withdrawal_after_code_commits_passes(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    """Earlier batch commits change Rust code; only the declaring commit is metadata."""
    base = never_bound_batch(repo)
    repo.commit({"src/query.rs": SOURCE.replace("true", "1 == 1")}, "tighten query\n\nSpec: DEMO-R001")
    repo.commit({"src/more.rs": "pub fn more() {}\n"}, f"more of the thing\n\nSpec: {NEVER}")
    never_bound_withdrawal(repo)
    changed = repo.git("show", "--name-only", "--format=", "HEAD").split()
    assert changed == ["specs/demo/plan.md"]
    assert repo.run("spec-trailers", "--base-ref", base) == 0
    assert "spec-trailers: OK" in capsys.readouterr().out


# spec: PIPE-CONNSPEC-R001.2
def test_never_bound_withdrawal_without_declaration_still_fails(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = never_bound_batch(repo)
    assert repo.run("spec-trailers", "--base-ref", base) == 1
    assert "requirement id(s) with no bound test in the tree: DEMO-R002" in capsys.readouterr().out


# spec: PIPE-CONNSPEC-R001.2
def test_never_bound_withdrawal_refuses_id_bound_at_head(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = never_bound_batch(repo, proof=f"// spec: {NEVER}\n#[test]\nfn proven() {{}}\n")
    never_bound_withdrawal(repo)
    assert repo.run("spec-trailers", "--base-ref", base) == 1
    assert "withdrawn IDs still have acceptance bindings" in capsys.readouterr().out


# spec: PIPE-CONNSPEC-R001.2
# Bound at the merge base routes to the whole-range removal path, which refuses the batch.
def test_never_bound_withdrawal_refuses_id_bound_at_merge_base(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit({"src/old_test.rs": f"// spec: {NEVER}\n#[test]\nfn old() {{}}\n"}, "old proof")
    base = never_bound_batch(repo)
    repo.commit({"src/old_test.rs": "#[test]\nfn old() {}\n"}, f"drop old proof\n\nSpec: {NEVER}")
    never_bound_withdrawal(repo)
    assert repo.run("spec-trailers", "--base-ref", base) == 1
    assert "withdrawal requires existing regular files" in capsys.readouterr().out


# spec: PIPE-CONNSPEC-R001.2
def test_never_bound_withdrawal_requires_plan_reason(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = never_bound_batch(repo)
    never_bound_withdrawal(repo, {"specs/demo/plan.md": f"# Plan\n\n{NEVER}: withdrawn.\n"})
    assert repo.run("spec-trailers", "--base-ref", base) == 1
    assert "owning plan must retain DEMO-R002" in capsys.readouterr().out


# spec: PIPE-CONNSPEC-R001.2
@pytest.mark.parametrize(
    "tasks",
    [NEVER_TASKS.replace("- [ ] T002", "- [x] T002"), "- [x] T001 DEMO-R001 query\n"],
    ids=["checked", "missing"],
)
def test_never_bound_withdrawal_requires_open_task(repo: Repo, tasks: str, capsys: pytest.CaptureFixture[str]) -> None:
    base = never_bound_batch(repo)
    repo.commit({"specs/demo/tasks.md": tasks}, "task change\n\nSpec: none (task tracking)")
    never_bound_withdrawal(repo, {"specs/demo/tasks.md": tasks})
    assert repo.run("spec-trailers", "--base-ref", base) == 1
    assert "never-bound DEMO-R002 needs its owning task unchecked" in capsys.readouterr().out


# spec: PIPE-CONNSPEC-R001.2
@pytest.mark.parametrize(
    "extra",
    [
        {"src/other.rs": "pub fn other() { todo!() }\n"},
        {"src/query.rs": SOURCE.replace("// spec: DEMO-R001\n", REPLACEMENT)},
        {"specs/demo/requirements.md": _requirements_md(RID) + "| `DEMO-R002` | Other thing. | None. |\n"},
        {"specs/demo/tasks.md": "- [x] T001 DEMO-R001 query\n- [ ] T002 DEMO-R002 weaker thing\n"},
        {"specs/demo/plan.md": f"{NEVER}: {NEVER_REASON}\n"},
        {"Cargo.toml": '[package]\nname = "new-feature"\n'},
    ],
)
def test_never_bound_withdrawal_commit_changes_only_metadata(
    repo: Repo, extra: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    base = never_bound_batch(repo)
    repo.commit({"Cargo.toml": '[package]\nname = "demo"\n'}, "manifest\n\nSpec: DEMO-R001")
    never_bound_withdrawal(repo, extra)
    assert repo.run("spec-trailers", "--base-ref", base) == 1
    assert "never-bound withdrawal commit changes non-evidence content" in capsys.readouterr().out


# spec: PIPE-CONNSPEC-R001.2
def test_binding_removal_case_is_unchanged(repo: Repo) -> None:
    base = setup(repo)
    correction(repo)
    assert repo.run("spec-trailers", "--base-ref", base) == 0
    # Bound at the merge base, so deleting the bound file is no metadata-only
    # never-bound withdrawal: the range must still remove the comment binding.
    repo.commit({"src/query.rs": SOURCE}, f"restore\n\nSpec: {RID}")
    repo.git("rm", "-q", "src/query.rs")
    repo.git("commit", "-q", "-m", f"drop file\n\nSpec: {RID}")
    assert repo.run("spec-trailers", "--base-ref", base) == 1
