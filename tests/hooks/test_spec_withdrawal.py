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
