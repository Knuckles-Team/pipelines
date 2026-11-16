"""A green version bump on main tags itself (PIPE-RELEASE-R018.3) with a fake HTTP layer."""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_autotag  # noqa: E402

SHA = "a" * 40
REPO = "Org/demo-mcp"


def _http_error(url: str, code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "error", {}, io.BytesIO(b"{}"))


class FakeApi:
    """Tags, index releases and the writes the script makes."""

    def __init__(self, tags: set[str], published: set[str] | None, ref_conflict: bool = False) -> None:
        self.tags, self.published, self.ref_conflict = set(tags), published, ref_conflict
        self.writes: list[tuple[str, dict]] = []

    def __call__(self, url: str, token: str | None = None, data: dict | None = None) -> bytes:
        if data is not None:
            assert token == "tok"
            self.writes.append((url, data))
            if url.endswith("/git/tags"):
                return json.dumps({"sha": "b" * 40}).encode()
            if self.ref_conflict:
                raise _http_error(url, 422)
            self.tags.add(data["ref"].removeprefix("refs/tags/"))
            return b"{}"
        if "/git/matching-refs/tags/v" in url:
            return json.dumps([{"ref": f"refs/tags/{tag}"} for tag in sorted(self.tags)]).encode()
        if url.startswith("https://pypi.org/pypi/demo-mcp/json"):
            if self.published is None:
                raise _http_error(url, 404)
            return json.dumps({"releases": {version: [] for version in self.published}}).encode()
        raise AssertionError(f"unexpected request {url}")


def _project(tmp_path: Path, version: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "demo_mcp"\nversion = "{version}"\n', encoding="utf-8")
    return tmp_path


@pytest.mark.spec("PIPE-RELEASE-R018.3")
def test_a_new_green_version_is_tagged_on_the_pushed_commit(tmp_path: Path) -> None:
    api = FakeApi({"v1.2.3", "v1.2.4"}, {"1.2.3", "1.2.4"})
    assert release_autotag.run(_project(tmp_path, "1.3.0"), REPO, SHA, "tok", api) == "v1.3.0"
    (tag_url, tag), (ref_url, ref) = api.writes
    assert tag_url == f"https://api.github.com/repos/{REPO}/git/tags"
    assert tag == {"tag": "v1.3.0", "message": "Release v1.3.0", "object": SHA, "type": "commit"}
    assert ref_url == f"https://api.github.com/repos/{REPO}/git/refs"
    assert ref == {"ref": "refs/tags/v1.3.0", "sha": "b" * 40}
    # A first release of a project the index does not know yet is tagged too.
    first = FakeApi(set(), None)
    assert release_autotag.run(_project(tmp_path, "0.1.0"), REPO, SHA, "tok", first) == "v0.1.0"


@pytest.mark.spec("PIPE-RELEASE-R018.3")
@pytest.mark.parametrize(
    ("version", "tags", "published", "reason"),
    [
        ("1.2.4", {"v1.2.4"}, {"1.2.3"}, "tag v1.2.4 already exists"),
        ("1.2.4", {"v1.2.3"}, {"1.2.3", "1.2.4"}, "already serves 1.2.4"),
        # Main lags a tag that carried a newer version: tagging would move latest back.
        ("0.3.9", {"v0.3.8", "v0.4.0"}, {"0.3.8", "0.4.0"}, "not newer than the released 0.4.0"),
        ("2.0.0rc1", set(), set(), "not MAJOR.MINOR.PATCH"),
    ],
)
def test_an_existing_tag_a_published_version_or_a_lagging_main_is_not_tagged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], version: str, tags: set[str], published: set[str], reason: str
) -> None:
    api = FakeApi(tags, published)
    assert release_autotag.run(_project(tmp_path, version), REPO, SHA, "tok", api) == ""
    assert api.writes == []
    assert reason in capsys.readouterr().out


@pytest.mark.spec("PIPE-RELEASE-R018.3")
def test_a_concurrently_created_tag_is_a_no_op(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    api = FakeApi({"v1.0.0"}, {"1.0.0"}, ref_conflict=True)
    assert release_autotag.run(_project(tmp_path, "1.0.1"), REPO, SHA, "tok", api) == ""
    assert "created concurrently" in capsys.readouterr().out


@pytest.mark.spec("PIPE-RELEASE-R018.3")
def test_the_newest_release_compares_numerically_and_ignores_other_tags() -> None:
    assert release_autotag.newest_release({"v1.9.0", "v1.10.0", "vnext", "legacy-2.0"}, {"1.2.0rc1"}) == "1.10.0"
    assert release_autotag.newest_release(set(), set()) is None


@pytest.mark.spec("PIPE-RELEASE-R018.3")
def test_main_writes_the_tag_output_and_refuses_without_a_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert release_autotag.main(["--root", str(tmp_path), "--repository", REPO, "--sha", SHA]) == 1
    monkeypatch.setenv("GH_TOKEN", "tok")
    assert release_autotag.main(["--root", str(tmp_path), "--repository", REPO, "--sha", "short"]) == 1
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\ndynamic = ["version"]\n', encoding="utf-8")
    assert release_autotag.main(["--root", str(tmp_path), "--repository", REPO, "--sha", SHA]) == 0
    assert output.read_text(encoding="utf-8") == "tag=\n"
