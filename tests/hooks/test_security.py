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


def test_secret_history_skips_a_documented_placeholder_uri_but_not_a_real_password() -> None:
    from pipelines_hooks.security.history_scan import scan_text_for_credentials

    example = "# ``postgresql://agent:" + "agent@localhost:5432/agent_kg`` documented example\n"
    assert scan_text_for_credentials(example) == []
    real = "DATABASE_URL = 'postgresql://svc:" + "Xk9fQ2pLr7@db.example.invalid/prod'\n"
    assert "db_url_with_password" in {hit["pattern"] for hit in scan_text_for_credentials(real)}


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
