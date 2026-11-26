"""PIPE-PAGES-R020.61 to R020.66: the shared project header of README and documentation home."""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.docs import readme_header as rh
from pipelines_hooks.docs.gate_io import sha
from tests.hooks.conftest import Repo
from tests.hooks.docs_support import browse, probe_of, serve

MARK = '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><rect width="48" height="48"/></svg>'
BADGE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="60" height="20"><rect width="60" height="20" fill="green"/></svg>'
)
LINKS = {
    "Documentation": "pages/index.md",
    "Capabilities": "pages/capabilities.md",
    "Interfaces": "pages/interfaces.md",
    "Status": "pages/status.md",
}
CONSUMER = "https://github.com/Knuckles-Team/medulla.git"


def contract_json() -> dict:
    return {
        "schema": 1,
        "readme": "README.md",
        "home": "pages/index.md",
        "title": "Medulla",
        "mark": {"path": "assets/mark-v1.svg", "version": "1", "digest": sha(MARK), "alt": "Medulla mark"},
        "description": "A graph engine for facts.",
        "links": LINKS,
        "badges": [{"id": "ci", "label": "CI", "provenance": "pinned:run-4821", "as_of": "2026-11-26"}],
    }


def build(tmp_path: Path, remote: str | None = CONSUMER, *, contract: dict | None = None) -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.root.mkdir(parents=True)
    repo.git("init", "-q")
    if remote:
        repo.git("remote", "add", "origin", remote)
    declared = contract or contract_json()
    files = {rh.DECLARATION: json.dumps(declared), "assets/mark-v1.svg": MARK}
    files.update({t: f"# {n}\n" for n, t in LINKS.items() if n != "Documentation"})
    parsed, _ = _contract(repo, files)
    files["README.md"] = rh.render_markdown(parsed) + "\n## Install\n\nRun it.\n"
    files["pages/index.md"] = rh.render_markdown(parsed, prefix="../") + "\n## Overview\n\nHome.\n"
    repo.stage(files)
    return repo


def _contract(repo: Repo, files: dict[str, str]):
    repo.stage({rh.DECLARATION: files[rh.DECLARATION]})
    return rh.load_contract(repo.root)


def edit(repo: Repo, rel: str, old: str, new: str) -> None:
    repo.stage({rel: (repo.root / rel).read_text().replace(old, new)})


# spec: PIPE-PAGES-R020.61
def test_readme_header_model(tmp_path: Path) -> None:
    repo = build(tmp_path)
    contract, digest = rh.load_contract(repo.root)
    assert (contract.title, contract.mark_version, contract.mark_alt) == ("Medulla", "1", "Medulla mark")
    assert tuple(contract.links) == rh.NAV and contract.badges[0].provenance == "pinned:run-4821" and digest
    consumers, registry_digest = rh.registry()
    assert len(consumers) == 7 and "github.com/Knuckles-Team/medulla" in consumers and registry_digest
    assert rh.PROVIDER not in consumers
    assert rh.resolve_identity(repo.root) == ("github.com/Knuckles-Team/medulla", "remote:origin")
    for url in ("git@github.com:Knuckles-Team/medulla.git", "ssh://git@github.com/Knuckles-Team/medulla"):
        repo.git("remote", "set-url", "origin", url)
        assert rh.resolve_identity(repo.root)[0] == "github.com/Knuckles-Team/medulla"
    repo.git("remote", "rename", "origin", "upstream")
    assert rh.resolve_identity(repo.root)[1] == "remote:upstream"  # a sole remote resolves
    repo.git("remote", "add", "extra", CONSUMER)
    with pytest.raises(CannotRun):
        rh.resolve_identity(repo.root)  # two remotes and no origin is ambiguous
    with pytest.raises(CannotRun):
        build(tmp_path / "order", contract=contract_json() | {"links": dict(reversed(LINKS.items()))})


# spec: PIPE-PAGES-R020.62
def test_readme_header_behavior(tmp_path: Path) -> None:
    repo = build(tmp_path)
    assert rh.check(repo.root).findings == []
    assert "scion-sdk" not in inspect.getsource(rh)  # one registry source, no second hard-coded list
    cases = {
        "order": lambda r: edit(r, "README.md", "A graph engine for facts.\n\n", ""),
        "navigation": lambda r: edit(r, "README.md", "[Status](pages/status.md)", "[Health](pages/status.md)"),
        "target": lambda r: edit(r, "pages/index.md", "../pages/interfaces.md", "../pages/nope.md"),
        "hidden-badge": lambda r: (
            edit(r, "README.md", "![CI]", "<details><summary>more</summary>![CI]")
            if False
            else r.stage(
                {
                    "README.md": (r.root / "README.md")
                    .read_text()
                    .replace("![CI]", "<details><summary>m</summary>![CI]")
                    .replace("\n## Install", "</details>\n\n## Install")
                }
            )
        ),
        "no-badge": lambda r: r.stage(
            {"pages/index.md": (r.root / "pages/index.md").read_text().replace("![CI]", "![Other]")}
        ),
        "mark": lambda r: r.stage({"assets/mark-v1.svg": MARK.replace("48", "47")}),
        "home": lambda r: edit(r, "pages/index.md", "# Medulla", "# Other"),
    }
    for name, mutate in cases.items():
        broken = build(tmp_path / name)
        mutate(broken)
        assert rh.check(broken.root).findings, name


# spec: PIPE-PAGES-R020.63
def test_readme_header_wiring(tmp_path: Path) -> None:
    import yaml

    from pipelines_hooks.cli import GATES, run_gate

    root = Path(__file__).resolve().parents[2]
    assert GATES["readme-header"] == "pipelines_hooks.docs.readme_header"
    assert "entry: pipelines-hook readme-header" in (root / ".pre-commit-hooks.yaml").read_text()
    config = yaml.safe_load((root / ".config/pre-commit.yaml").read_text())
    assert any(h["id"] == "readme-header" for r in config["repos"] if r["repo"] == "local" for h in r["hooks"])
    partial = (root / "templates/mkdocs-theme/overrides/partials/project-header.html").read_text()
    assert (
        partial.index('"Documentation"') < partial.index('"Status"')
        and "data-nav" in partial
        and "header.mark.alt" in partial
    )
    workflow = (root / ".github/workflows/pages_pipeline.yml").read_text()
    assert (
        workflow.index("docs.readme_header") < workflow.index("Upload artifact")
        and "scripts/skill_graph/model.py" in workflow
    )
    repo = build(tmp_path)
    assert run_gate("readme-header", ["--root", str(repo.root)]) == 0 == repo.run("readme-header")
    provider = build(tmp_path / "p", "https://github.com/Knuckles-Team/pipelines")
    assert provider.run("readme-header") == 0  # declared non-applicable scope, no declaration needed


# spec: PIPE-PAGES-R020.64
def test_readme_header_refusal(tmp_path: Path) -> None:
    assert build(tmp_path / "ok").run("readme-header") == 0
    broken = build(tmp_path / "broken")
    edit(broken, "README.md", "Medulla mark", "Other mark")
    assert broken.run("readme-header") == 1
    drift = build(tmp_path / "drift")
    edit(drift, "pages/index.md", "# Medulla", "# Other")
    assert drift.run("readme-header") == 1
    for name, remote in {
        "unknown": "https://github.com/Knuckles-Team/unknown-repo.git",
        "same-basename": "https://github.com/Someone-Else/medulla.git",
        "other-host": "https://git.example.invalid/Knuckles-Team/medulla.git",
        "garbage": "not a url",
    }.items():
        assert build(tmp_path / name, remote).run("readme-header") == 2, name
    assert build(tmp_path / "noremote", None).run("readme-header") == 2
    for name, patch in {
        "provenance": {"badges": [{"id": "ci", "label": "CI", "provenance": "live:https://x", "as_of": "2026-11-26"}]},
        "stale": {"badges": [{"id": "ci", "label": "CI", "provenance": "pinned:r", "as_of": "yesterday"}]},
    }.items():
        with pytest.raises(CannotRun):
            repo = build(tmp_path / name, contract=contract_json() | patch)
            rh.check(repo.root)
    unavailable = build(tmp_path / "unavailable")
    unavailable.git("rm", "-q", "--cached", rh.DECLARATION)
    assert unavailable.run("readme-header") == 2


# spec: PIPE-PAGES-R020.65
def test_readme_header_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path)
    capsys.readouterr()
    assert repo.run("readme-header") == 0
    out = capsys.readouterr().out
    assert "scope consumer=medulla identity=github.com/Knuckles-Team/medulla source=remote:origin policy=" in out
    assert f"mark path=assets/mark-v1.svg version=1 digest={sha(MARK)}" in out
    assert (
        "header doc=README.md order=title,mark,description,navigation destinations=" in out
        and "header doc=pages/index.md" in out
    )
    assert "badge doc=README.md id=ci visible=yes provenance=pinned:run-4821 as-of=2026-11-26" in out
    provider = build(tmp_path / "p", "https://github.com/Knuckles-Team/pipelines")
    assert provider.run("readme-header") == 0
    skip = capsys.readouterr().out
    assert (
        "readme-header skip reason=provider-not-consumer identity=github.com/Knuckles-Team/pipelines source=remote:origin registry="
        in skip
    )
    assert "consumer-checks=0" in skip and "grade" not in skip and "coverage" not in skip


# spec: PIPE-PAGES-R020.66
def test_readme_header_cli(tmp_path: Path) -> None:
    repo = build(tmp_path)
    site = tmp_path / "site"
    (site / "assets").mkdir(parents=True)
    (site / "badges").mkdir()
    (site / "assets/mark-v1.svg").write_text(MARK)
    (site / "badges/ci.svg").write_text(BADGE)

    def page(*, order=rh.NAV, collapsed=False, mark="assets/mark-v1.svg") -> str:
        nav = "".join(f'<a data-nav="{n}" href="pages/{n.lower()}.html">{n}</a>' for n in order)
        badge = '<img src="badges/ci.svg" alt="CI">'
        badge = f"<details><summary>more</summary>{badge}</details>" if collapsed else badge
        probe = (
            "<script>window.addEventListener('load',()=>{const v=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&!e.closest('details:not([open])')};"
            "const m=document.querySelector('header img');"
            "document.body.setAttribute('data-probe',JSON.stringify({nav:[...document.querySelectorAll('[data-nav]')].map(a=>a.dataset.nav),"
            "mark:{alt:m.alt,loaded:m.complete&&m.naturalWidth>0},badges:[...document.querySelectorAll('.b img')].map(x=>({alt:x.alt,visible:v(x),loaded:x.complete&&x.naturalWidth>0}))}))});</script>"
        )
        return f'<!doctype html><html><body><header><h1>Medulla</h1><img src="{mark}" alt="Medulla mark"><p>A graph engine for facts.</p><nav>{nav}</nav><p class="b">{badge}</p></header>{probe}</body></html>'

    def served() -> dict:
        with serve(site) as base:
            return probe_of(browse(f"{base}/index.html"))

    (site / "index.html").write_text(page())
    probe = served()
    assert probe["nav"] == list(rh.NAV) and probe["mark"] == {"alt": "Medulla mark", "loaded": True}
    assert probe["badges"] == [{"alt": "CI", "visible": True, "loaded": True}]
    assert repo.run("readme-header", "--site", str(site)) == 0
    (site / "index.html").write_text(page(order=("Documentation", "Status", "Interfaces", "Capabilities")))
    assert served()["nav"] != list(rh.NAV) and repo.run("readme-header", "--site", str(site)) == 1
    (site / "index.html").write_text(page(collapsed=True))
    assert served()["badges"][0]["visible"] is False and repo.run("readme-header", "--site", str(site)) == 1
    (site / "index.html").write_text(page(mark="assets/other-mark.svg"))
    assert served()["mark"]["loaded"] is False and repo.run("readme-header", "--site", str(site)) == 1

    def cli(fixture: Repo, *args: str) -> int:
        done = subprocess.run(
            [sys.executable, "-m", "pipelines_hooks", "readme-header", "--root", str(fixture.root), *args],
            capture_output=True,
            text=True,
        )
        return done.returncode

    provider = build(tmp_path / "provider", "https://github.com/Knuckles-Team/pipelines")
    done = subprocess.run(
        [sys.executable, "-m", "pipelines_hooks", "readme-header", "--root", str(provider.root)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0 and "provider-not-consumer" in done.stdout and "consumer-checks=0" in done.stdout
    assert cli(build(tmp_path / "unknown", "https://github.com/Knuckles-Team/unknown-repo")) == 2
    assert cli(build(tmp_path / "namespace", "https://github.com/Someone-Else/medulla")) == 2
    known = build(tmp_path / "known")
    edit(known, "README.md", "(pages/status.md)", "(pages/gone.md)")
    assert cli(known) == 1 and cli(known, "--provider") == 1  # a caller flag never skips
