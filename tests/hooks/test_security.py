"""secret-history and security-sanitizer fire on planted credentials; markers need a reason.

Planted values are assembled at runtime so this file itself carries no credential shape.
"""

from __future__ import annotations

from pipelines_hooks.security.secret_history import check
from pipelines_hooks.security.sanitizer import scan_repository
from tests.hooks.conftest import Repo

AWS_KEY = "AKIA" + "QWERTYUIOPASDFGH"
GITHUB_TOKEN = "ghp" + "_" + "Zx9" * 12
MARK = "# sanitizer" + ":ignore"


def _assignment(name: str, value: str = GITHUB_TOKEN) -> str:
    """A planted source line assigning ``value``, assembled at runtime.

    Written literally, the line would itself be credential-shaped text in this
    repository's history, and secret-history would rightly flag it.
    """
    return name + " = " + repr(value) + "\n"


def test_secret_history_fires_on_a_planted_credential_in_the_range(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    repo.commit({"pkg/leak.py": f"KEY = '{AWS_KEY}'\n"})
    assert check(repo.root, base)[0] == 1


def test_secret_history_honours_only_a_justified_marker(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    repo.commit({"pkg/fixture.py": f"KEY = '{AWS_KEY}'  {MARK} - synthetic test fixture\n"})
    assert check(repo.root, base)[0] == 0
    repo.commit({"pkg/bare.py": f"KEY = '{AWS_KEY}'  {MARK}\n"})
    assert check(repo.root, base)[0] == 1


def test_secret_history_scans_all_history_without_a_published_base(repo: Repo) -> None:
    repo.commit({"pkg/leak.py": _assignment("TOKEN")})
    repo.commit({"pkg/leak.py": "TOKEN = None\n"})
    assert repo.run("secret-history") == 1


def _publish(repo: Repo, branch: str = "feature") -> None:
    """Push the current HEAD to a bare remote, so its commits are published."""
    remote = repo.root.parent / f"{repo.root.name}-remote.git"
    if not remote.exists():
        repo.git("init", "-q", "--bare", str(remote))
        repo.git("remote", "add", "origin", str(remote))
    repo.git("push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    repo.git("fetch", "-q", "origin")


def test_secret_history_does_not_rescan_published_commits_whose_secret_is_gone(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    repo.commit({"pkg/leak.py": _assignment("TOKEN")})
    repo.commit({"pkg/leak.py": "TOKEN = None\n"})
    assert check(repo.root, base)[0] == 1  # unpushed: the add-then-remove is caught
    _publish(repo)
    rc, result = check(repo.root, base)
    assert rc == 0
    assert result["publishedCommitsNotRescanned"] == 2 and result["unpublishedCommitsScanned"] == 0


def test_secret_history_net_diff_catches_a_secret_still_in_a_published_change(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    repo.commit({"pkg/leak.py": _assignment("TOKEN")})
    _publish(repo)
    rc, result = check(repo.root, base)
    assert rc == 1
    assert result["credentialHits"][0]["commit"] == "net-diff"


def test_secret_history_marker_on_a_net_diff_line_exempts_a_published_fixture(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    repo.commit({"pkg/fixture.py": f"KEY = '{AWS_KEY}'\n"})
    _publish(repo)
    assert check(repo.root, base)[0] == 1
    repo.commit({"pkg/fixture.py": f"KEY = '{AWS_KEY}'  {MARK} - synthetic test fixture\n"})
    _publish(repo)
    assert check(repo.root, base)[0] == 0
    repo.commit({"pkg/fixture.py": f"KEY = '{AWS_KEY}'  {MARK}\n"})
    _publish(repo)
    assert check(repo.root, base)[0] == 1  # a bare marker still exempts nothing


def test_secret_history_skips_a_documented_placeholder_uri_but_not_a_real_password() -> None:
    from pipelines_hooks.security.history_scan import scan_text_for_credentials

    example = "# ``postgresql://agent:" + "agent@localhost:5432/agent_kg`` documented example\n"
    assert scan_text_for_credentials(example) == []
    real = "DATABASE_URL = 'postgresql://svc:" + "Xk9fQ2pLr7@db.example.invalid/prod'\n"
    assert "db_url_with_password" in {hit["pattern"] for hit in scan_text_for_credentials(real)}


# spec: PIPE-GATES-R083
def test_secret_history_self_check_passes() -> None:
    from pipelines_hooks.cli import run_gate

    assert run_gate("secret-history", ["--self-check"]) == 0


def test_sanitizer_fires_on_a_secret_and_root_garbage_and_passes_placeholders(repo: Repo) -> None:
    repo.write("pkg/config.py", _assignment("token"))
    assert "(GitHub PAT)" in "\n".join(scan_repository(repo.root))
    repo.write("pkg/config.py", _assignment("token", "your_token_here_" + "placeholder"))
    assert scan_repository(repo.root) == []
    repo.write("notes.txt", "scratch\n")
    assert repo.run("security-sanitizer") == 1


def test_a_trusted_binary_extension_is_not_content_inspected(repo: Repo) -> None:
    # spec: PIPE-GATES-R104
    (repo.root / "pkg/rider.glb").write_bytes(b"glTF" + b"\x02\x00" + b"\xff\xfe" + b"\x00" * 16)
    assert repo.run("security-sanitizer") == 0
    (repo.root / "pkg/rider.blob").write_bytes(b"\xff\xfe" + b"\x00" * 16)
    assert repo.run("security-sanitizer") == 1


def test_a_gzip_tarball_is_a_trusted_binary_extension(repo: Repo) -> None:
    # spec: PIPE-GATES-R104.1
    (repo.root / "pkg/assets.tar.gz").write_bytes(b"\x1f\x8b" + b"\xff\xfe" + b"\x00" * 16)
    assert repo.run("security-sanitizer") == 0
    (repo.root / "pkg/assets.gz.blob").write_bytes(b"\xff\xfe" + b"\x00" * 16)
    assert repo.run("security-sanitizer") == 1


def _exception_entry(commit: str, path: str, line: str, **overrides: str) -> str:
    from pipelines_hooks.security.history_exceptions import line_digest

    fields = {
        "commit": commit,
        "file": path,
        "line_digest": line_digest(line),
        "reason": "shape based match on a synthetic fixture line that was never a live credential at all",
        "reviewed_on": "2026-11-26",
        **overrides,
    }
    return "[[exception]]\n" + "".join(f'{key} = "{value}"\n' for key, value in fields.items())


# spec: PIPE-GATES-R083
def test_secret_history_digest_pinned_exception_matches_only_the_pinned_occurrence(repo: Repo) -> None:
    import pytest

    from pipelines_hooks.core.errors import CannotRun
    from pipelines_hooks.security.history_exceptions import EXCEPTIONS, line_digest, load_exceptions, pin_problem

    base = repo.git("rev-parse", "HEAD").strip()
    line = f"KEY = '{AWS_KEY}'"
    pinned = repo.commit({"pkg/pinned.py": line + "\n"})
    repo.commit({"pkg/other.py": line + "\n"})  # the same line, another commit and file
    repo.commit({"pkg/pinned_too.py": line + " + 1\n"})  # a different line
    assert check(repo.root, base)[0] == 1
    repo.write(EXCEPTIONS, _exception_entry(pinned, "pkg/pinned.py", line))
    _, result = check(repo.root, base)
    leaked = {hit["file"].removeprefix("b/") for hit in result["credentialHits"]}
    assert leaked == {"pkg/other.py", "pkg/pinned_too.py"}
    assert pin_problem(repo.root, load_exceptions(repo.root)[0]) is None
    # a wrong pin (file, digest or commit) exempts nothing and fails the self-check
    for override in ({"file": "pkg/other.py"}, {"line_digest": line_digest("something else")}):
        repo.write(EXCEPTIONS, _exception_entry(pinned, "pkg/pinned.py", line, **override))
        assert {h["file"].removeprefix("b/") for h in check(repo.root, base)[1]["credentialHits"]} >= {"pkg/pinned.py"}
        assert pin_problem(repo.root, load_exceptions(repo.root)[0]) is not None
    # an abbreviated commit or a short reason is refused, not guessed
    repo.write(EXCEPTIONS, _exception_entry(pinned[:12], "pkg/pinned.py", line))
    with pytest.raises(CannotRun, match="full commit digest"):
        check(repo.root, base)
    repo.write(EXCEPTIONS, _exception_entry(pinned, "pkg/pinned.py", line, reason="too short"))
    with pytest.raises(CannotRun, match="justification"):
        check(repo.root, base)


# spec: PIPE-GATES-R083
def test_secret_history_self_check_fails_for_a_stale_repository_entry(repo: Repo, capsys) -> None:
    from pipelines_hooks.cli import run_gate
    from pipelines_hooks.security.history_exceptions import EXCEPTIONS

    line = f"KEY = '{AWS_KEY}'"
    pinned = repo.commit({"pkg/pinned.py": line + "\n"})
    repo.write(EXCEPTIONS, _exception_entry(pinned, "pkg/pinned.py", line))
    assert run_gate("secret-history", ["--self-check", "--root", str(repo.root)]) == 0
    repo.write(EXCEPTIONS, _exception_entry(pinned, "pkg/missing.py", line))
    assert run_gate("secret-history", ["--self-check", "--root", str(repo.root)]) == 1
    assert "does not add the pinned line to pkg/missing.py" in capsys.readouterr().err
