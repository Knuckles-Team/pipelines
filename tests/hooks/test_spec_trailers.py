"""spec-trailers (SPEC-STATUS-LIFECYCLE.md S6.3-5): trailer presence, known IDs, bound tests."""

from __future__ import annotations

import json

import pytest

from tests.hooks.conftest import Repo


def _requirements_md(identifier: str) -> str:
    return (
        "# Demo requirements\n\n"
        "| ID | Requirement | Verification |\n"
        "|---|---|---|\n"
        f"| `{identifier}` | **Thing.** Does a thing. | Verified by a test. |\n"
    )


def _commit(repo: Repo, files: dict[str, str], message: str, *, trailer: str | None = None) -> str:
    for rel, text in files.items():
        repo.write(rel, text)
    repo.git("add", "--", *files)
    args = ["commit", "-q", "-m", message]
    if trailer is not None:
        args += ["--trailer", f"Spec: {trailer}"]
    repo.git(*args)
    return repo.git("rev-parse", "HEAD").strip()


def _synthetic_merge(repo: Repo, *, base: str, head: str, message: str = "GitHub synthetic merge") -> str:
    """Create a merge-shaped commit with a product-only first-parent diff."""
    repo.git("checkout", "-q", base)
    repo.write("pkg/synthetic.py", "synthetic = True\n")
    repo.git("add", "--", "pkg/synthetic.py")
    tree = repo.git("write-tree").strip()
    merge = repo.git("commit-tree", tree, "-p", base, "-p", head, "-m", message).strip()
    repo.git("reset", "--hard", "-q", merge)
    return merge


def _pull_request_event(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, *, number: int, base: str, head: str, merge: str
) -> None:
    payload = {
        "number": number,
        "pull_request": {
            "base": {"sha": base},
            "head": {"sha": head},
            "merge_commit_sha": merge,
        },
    }
    event = repo.write("event.json", json.dumps(payload))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_REF", f"refs/pull/{number}/merge")


def test_pass_known_id_with_a_python_mark_spec_binding(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    _commit(
        repo,
        {
            "pkg/feature.py": "def feature():\n    return 1\n",
            "specs/demo/requirements.md": _requirements_md("DEMO-R001"),
            "tests/test_feature.py": (
                '"""test"""\nimport pytest\n\n\n@pytest.mark.spec("DEMO-R001")\ndef test_feature():\n    assert True\n'
            ),
        },
        "add feature",
        trailer="DEMO-R001",
    )
    assert repo.run("spec-trailers", "--base-ref", base) == 0


def test_pr_synthetic_merge_without_a_trailer_is_ignored_when_parents_are_verified(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    repo.git("checkout", "-qb", "topic")
    head = repo.commit({"docs/topic.md": "topic\n"}, "topic docs")
    repo.git("checkout", "-q", "main")
    merge = _synthetic_merge(repo, base=base, head=head)
    _pull_request_event(repo, monkeypatch, number=42, base=base, head=head, merge=merge)
    assert repo.run("spec-trailers", "--base-ref", base) == 0


def test_real_untrailed_merge_commit_with_a_product_diff_is_rejected(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    repo.git("checkout", "-qb", "topic")
    head = repo.commit({"docs/topic.md": "topic\n"}, "topic docs")
    merge = _synthetic_merge(repo, base=base, head=head, message="real branch merge")
    assert merge != head
    assert repo.run("spec-trailers", "--base-ref", base) == 1


def test_pass_none_exemption_covers_a_product_only_change(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    _commit(repo, {"pkg/util.py": "x = 1\n"}, "tooling bump", trailer="none (ci)")
    assert repo.run("spec-trailers", "--base-ref", base) == 0


def test_pass_a_docs_only_change_needs_no_trailer_at_all(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    repo.commit({"docs/notes.md": "notes\n"}, "docs only")
    assert repo.run("spec-trailers", "--base-ref", base) == 0


def test_item3_fail_a_product_change_with_no_spec_trailer_anywhere_in_range(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    repo.commit({"pkg/util.py": "x = 2\n"}, "no trailer at all")
    assert repo.run("spec-trailers", "--base-ref", base) == 1
    out = capsys.readouterr().out
    assert "no commit in the" in out
    assert "Spec:" in out


def test_item4_fail_a_trailer_names_an_id_with_no_requirements_row(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    _commit(repo, {"pkg/util.py": "x = 3\n"}, "unknown id", trailer="NOPE-R999")
    assert repo.run("spec-trailers", "--base-ref", base) == 1
    out = capsys.readouterr().out
    assert "unknown requirement id" in out
    assert "NOPE-R999" in out


def test_item4_a_range_trailer_expands_to_each_member_id(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    _commit(
        repo,
        {"pkg/util.py": "x = 4\n"},
        "range of unknown ids",
        trailer="DEMO4-R001..R003",
    )
    assert repo.run("spec-trailers", "--base-ref", base) == 1
    out = capsys.readouterr().out
    assert "DEMO4-R001" in out
    assert "DEMO4-R002" in out
    assert "DEMO4-R003" in out


def test_item5_fail_a_known_id_with_no_bound_test_in_the_tree(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    _commit(
        repo,
        {
            "pkg/util.py": "x = 5\n",
            "specs/demo2/requirements.md": _requirements_md("DEMO2-R001"),
        },
        "known but never bound",
        trailer="DEMO2-R001",
    )
    assert repo.run("spec-trailers", "--base-ref", base) == 1
    out = capsys.readouterr().out
    assert "no bound test" in out
    assert "DEMO2-R001" in out


def test_pass_a_known_id_with_a_comment_style_binding(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    _commit(
        repo,
        {
            "pkg/widget.py": "x = 1\n",
            "specs/demo5/requirements.md": _requirements_md("DEMO5-R001"),
            "src/widget.rs": "// spec: DEMO5-R001\n#[test]\nfn test_widget() {}\n",
        },
        "rust bound",
        trailer="DEMO5-R001",
    )
    assert repo.run("spec-trailers", "--base-ref", base) == 0


def test_a_malformed_base_revision_cannot_run(repo: Repo) -> None:
    assert repo.run("spec-trailers", "--base-ref", "not-a-real-revision") == 2


def test_same_trailer_shorthand_inherits_prefix() -> None:
    from pipelines_hooks.specs.trailer_ids import _qualified

    assert _qualified(["TUI-RUNTIME-R001.1", "R001.2", "R003..R004"]) == [
        "TUI-RUNTIME-R001.1",
        "TUI-RUNTIME-R001.2",
        "TUI-RUNTIME-R003..R004",
    ]


def test_item5_a_delivery_reverted_in_range_needs_no_bound_test(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    _commit(
        repo,
        {
            "pkg/util.py": "x = 6\n",
            "specs/demo3/requirements.md": _requirements_md("DEMO3-R001"),
        },
        "deliver then withdraw",
        trailer="DEMO3-R001",
    )
    delivered = repo.git("rev-parse", "HEAD").strip()
    _commit(
        repo,
        {"pkg/util.py": "x = 5\n"},
        f"withdraw the delivery\n\nThis reverts commit {delivered}.",
        trailer="none (refactor)",
    )
    assert repo.run("spec-trailers", "--base-ref", base) == 0
