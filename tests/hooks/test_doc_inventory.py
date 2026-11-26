"""PIPE-PAGES-R020.55 to R020.60: documentation roles of the project configuration inventory."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.hygiene import config_inventory as ci
from pipelines_hooks.hygiene import config_inventory_docs as docs
from tests.hooks.conftest import Repo
from tests.hooks.docs_support import fetch, serve
from tests.hooks.test_config_inventory import DECLARATION as BASE

DECL = BASE + '\n[documentation]\ntemplate = "1"\ncontent = "pages"\nretired = ["docs"]\n'


def _repo(tmp_path: Path, declaration: str = DECL) -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.root.mkdir(parents=True)
    repo.git("init", "-q")
    repo.stage({ci.DECLARATION: declaration})
    out = tmp_path / "scratch"
    ci.render(ci.load_inventory(repo.root), out)
    repo.stage({str(p.relative_to(out)): p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file()})
    return repo


def _edit(repo: Repo, rel: str, old: str, new: str) -> None:
    repo.stage({rel: (repo.root / rel).read_text(encoding="utf-8").replace(old, new)})


def _findings(repo: Repo) -> list[str]:
    return ci.check(repo.root, ci.load_inventory(repo.root))[0]


# spec: PIPE-PAGES-R020.55
def test_doc_inventory_model(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    inventory = ci.load_inventory(repo.root)
    assert inventory.documentation == docs.DocPolicy("1", "pages", ("docs",))
    assert sorted(inventory.projects) == [".", "svc"]  # the existing project list, not a second one
    assert docs.doc_file("svc", "content-index", "pages") == "svc/pages/index.md"
    assert set(docs.ROLES) == {"readme", "agent-guide", "content-index", "changelog", "doc-config"}
    assert docs.render_role("readme", {"name": "alpha", "python": "3.12"}, "pages").startswith(
        "<!-- pipelines:managed role=readme template=1 -->"
    )
    for bad in ({"template": "2"}, {"content": "../x"}, {"retired": ["/abs"]}):
        with pytest.raises(CannotRun):
            docs.parse_policy({"template": "1", "content": "pages", "retired": []} | bad)


# spec: PIPE-PAGES-R020.56
def test_doc_inventory_behavior(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert _findings(repo) == []
    # custom content outside managed sections is preserved and unchecked, including unchanged projects
    _edit(
        repo,
        "README.md",
        "<!-- pipelines:end role=readme -->\n",
        "<!-- pipelines:end role=readme -->\n\nCustom prose.\n",
    )
    repo.stage(
        {"CHANGELOG.md": (repo.root / "CHANGELOG.md").read_text() + "\n## [1.0.0] - 2026-01-02\n\nHistorical text.\n"}
    )
    assert _findings(repo) == []
    cases = {
        "guide": lambda r: r.git("rm", "-q", "-f", "AGENTS.md"),
        "index": lambda r: r.git("rm", "-q", "-f", "svc/pages/index.md"),
        "changelog": lambda r: r.git("rm", "-q", "-f", "CHANGELOG.md"),
        "config": lambda r: _edit(r, "svc/mkdocs.yml", "docs_dir: pages", "docs_dir: docs"),
        "nav": lambda r: _edit(r, "pages/index.md", "- [Reference](reference.md)\n", ""),
        "drift": lambda r: _edit(r, "svc/README.md", "## Documentation", "## Docs"),
        "grammar": lambda r: r.stage({"CHANGELOG.md": (r.root / "CHANGELOG.md").read_text() + "\n## Version one\n"}),
        "retired": lambda r: r.stage({"docs/old.md": "moved\n"}),
    }
    for name, mutate in cases.items():
        broken = _repo(tmp_path / name)
        mutate(broken)
        assert _findings(broken), name


# spec: PIPE-PAGES-R020.57
def test_doc_inventory_wiring(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = Path(__file__).resolve().parents[2]
    assert "entry: pipelines-hook config-inventory --check" in (root / ".pre-commit-hooks.yaml").read_text()
    workflow = (root / ".github/workflows/pages_pipeline.yml").read_text()
    assert workflow.index("config_inventory") < workflow.index("Upload artifact")
    assert "pipelines_hooks/hygiene" in workflow
    repo = _repo(tmp_path)
    assert repo.run("config-inventory", "--check") == 0
    out = capsys.readouterr().out
    assert "doc-role project=svc role=content-index path=svc/pages/index.md" in out
    assert repo.run("config-inventory", "--check", "--scope", "documentation") == 0
    plain = _repo(tmp_path / "plain", BASE)  # no [documentation] table: the scope is a no-op
    assert plain.run("config-inventory", "--check", "--scope", "documentation") == 0


# spec: PIPE-PAGES-R020.58
def test_doc_inventory_refusal(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.git("rm", "-q", "-f", "AGENTS.md")
    assert repo.run("config-inventory", "--check") == 1
    assert _repo(tmp_path / "t").run("config-inventory", "--render", str(tmp_path / "scratch")) == 2  # never overwrites
    unknown = _repo(tmp_path / "u")
    unknown.stage({ci.DECLARATION: DECL.replace('template = "1"\ncontent', 'template = "9"\ncontent')})
    assert unknown.run("config-inventory", "--check") == 2
    escaping = _repo(tmp_path / "e")
    escaping.stage({ci.DECLARATION: DECL.replace('content = "pages"', 'content = "../escape"')})
    assert escaping.run("config-inventory", "--check") == 2
    ambiguous = _repo(tmp_path / "a", DECL.replace('content = "pages"\n', ""))
    ambiguous.stage({"docs/index.md": "# x\n"})
    assert ambiguous.run("config-inventory", "--check") == 2
    empty_page = _repo(tmp_path / "p")
    empty_page.stage({"pages/overview.md": ""})
    assert _findings(empty_page)  # an empty file is not a complete tree
    unreadable = _repo(tmp_path / "s")
    unreadable.git("rm", "-q", "--cached", ci.DECLARATION)
    assert unreadable.run("config-inventory", "--check") == 2
    kept = _repo(tmp_path / "k")
    _edit(kept, "README.md", "<!-- pipelines:end role=readme -->\n", "<!-- pipelines:end role=readme -->\n\nCustom.\n")
    assert "Custom." in (kept.root / "README.md").read_text() and _findings(kept) == []


# spec: PIPE-PAGES-R020.59
def test_doc_inventory_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    capsys.readouterr()
    assert repo.run("config-inventory", "--check") == 0
    out = capsys.readouterr().out
    assert len(re.findall(r"^doc-role project=", out, re.M)) == 10  # five roles for each of two projects
    assert re.search(r"doc-role project=\. role=readme path=README.md template=1 expected=(\w+) observed=\1", out)
    assert "doc-edge project=. from=README.md to=pages/index.md ok" in out
    assert "doc-edge project=svc from=svc/pages/index.md to=svc/pages/reference.md ok" in out
    assert re.search(r"doc-tree digest=\w{16} template=1", out) and "receipt project=svc role=pytest" in out
    _edit(repo, "pages/index.md", "- [Reference](reference.md)\n", "")
    assert repo.run("config-inventory", "--check") == 1
    broken = capsys.readouterr().out
    assert "doc-edge project=. from=pages/index.md to=pages/reference.md broken" in broken
    assert "pages/index.md: navigation edge to pages/reference.md is missing" in broken


# spec: PIPE-PAGES-R020.60
def test_doc_inventory_cli(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.run("config-inventory", "--check") == 0
    with serve(repo.root) as base:
        readme = fetch(f"{base}/README.md")
        assert "(pages/index.md)" in readme
        index = fetch(f"{base}/pages/index.md")
        for target in re.findall(r"\]\(([^)]+\.md)\)", index):
            assert fetch(f"{base}/pages/{target}").startswith("# ")
    mutations = {
        "guide": (
            lambda r: r.git("rm", "-q", "-f", "AGENTS.md"),
            lambda r: r.stage({"AGENTS.md": (tmp_path / "scratch/AGENTS.md").read_text()}),
        ),
        "index": (
            lambda r: r.git("rm", "-q", "-f", "pages/index.md"),
            lambda r: r.stage({"pages/index.md": (tmp_path / "scratch/pages/index.md").read_text()}),
        ),
        "changelog": (
            lambda r: r.git("rm", "-q", "-f", "CHANGELOG.md"),
            lambda r: r.stage({"CHANGELOG.md": (tmp_path / "scratch/CHANGELOG.md").read_text()}),
        ),
        "config": (
            lambda r: r.git("rm", "-q", "-f", "mkdocs.yml"),
            lambda r: r.stage({"mkdocs.yml": (tmp_path / "scratch/mkdocs.yml").read_text()}),
        ),
        "navigation": (
            lambda r: _edit(r, "pages/index.md", "(overview.md)", "(gone.md)"),
            lambda r: _edit(r, "pages/index.md", "(gone.md)", "(overview.md)"),
        ),
        "retired": (lambda r: r.stage({"docs/old.md": "x\n"}), lambda r: r.git("rm", "-q", "-f", "docs/old.md")),
    }
    for name, (break_it, repair) in mutations.items():
        break_it(repo)
        assert repo.run("config-inventory", "--check") == 1, name
        repair(repo)
        assert repo.run("config-inventory", "--check") == 0, name
