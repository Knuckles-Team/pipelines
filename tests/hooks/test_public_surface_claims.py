"""End-to-end public-surface claim proof for PIPE-PAGES-R020.6."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.docs.claims import (
    FindingRefusal,
    LocatedFinding,
    evidence_digest_for,
    export_located_evidence,
    make_located_finding,
    source_digest,
    validate_located_evidence,
)
from tests.hooks.conftest import Repo


# spec: PIPE-PAGES-R020.6
def test_public_surface_hook_fails_on_stale_claim(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit(
        {
            "README.md": (
                "# fixture\n\n<!-- claim:path docs/missing.md -->\n\n## Installation\n\n```bash\nuv sync\n```\n"
            )
        },
        "docs",
    )
    assert repo.run("public-surface") == 1
    output = capsys.readouterr().out
    assert "README.md:3 path docs/missing.md" in output
    assert "claims: checked 1, unresolved 1" in output


# spec: PIPE-PAGES-R020.3
def test_installed_cli_checks_an_ordinary_document_claim(repo: Repo) -> None:
    repo.commit(
        {
            "README.md": "# fixture\n\n## Installation\n\n```bash\nuv sync\n```\n",
            "mkdocs.yml": "site_name: fixture\ndocs_dir: docs\n",
            "docs/guide.md": (
                "# Guide\n\n<!-- claim:path docs/asset.md -->\n<!-- claim:command scripts/bootstrap.sh -->\n"
            ),
            "docs/asset.md": "# Asset\n",
            "scripts/bootstrap.sh": "#!/bin/sh\n",
        },
        "docs",
    )
    executable = shutil.which("pipelines-hook")
    assert executable is not None
    result = subprocess.run(
        [executable, "public-surface", "--root", str(repo.root)],
        cwd=repo.root,
        env=sanitized_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "claims: checked 2, unresolved 0" in result.stdout


# spec: PIPE-PAGES-R020.3
def test_installed_cli_rejects_a_stale_unannotated_document_link(repo: Repo) -> None:
    repo.commit(
        {
            "README.md": "# fixture\n\n## Installation\n\n```bash\nuv sync\n```\n",
            "mkdocs.yml": "site_name: fixture\ndocs_dir: docs\n",
            "docs/guide.md": "# Guide\n\n[Missing guide](missing.md)\n",
        },
        "docs",
    )
    executable = shutil.which("pipelines-hook")
    assert executable is not None
    result = subprocess.run(
        [executable, "public-surface", "--root", str(repo.root)],
        cwd=repo.root,
        env=sanitized_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "docs/guide.md local link does not exist" in result.stdout


# spec: PIPE-PAGES-R020.4
@pytest.mark.parametrize(
    "comment",
    [
        "<!-- claim:path -->",
        "<!-- claim:unknown docs/guide.md -->",
        "<!-- claim:path docs/guide.md",
    ],
)
def test_installed_cli_refuses_malformed_claims(repo: Repo, comment: str) -> None:
    repo.write(
        "README.md",
        f"# fixture\n\n{comment}\n\n## Installation\n\n```bash\nuv sync\n```\n",
    )
    executable = shutil.which("pipelines-hook")
    assert executable is not None
    result = subprocess.run(
        [executable, "public-surface", "--root", str(repo.root)],
        cwd=repo.root,
        env=sanitized_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "README.md:3 claims-unchecked" in result.stderr


def _located_fixture(root: Path) -> LocatedFinding:
    path = root / "docs" / "guide.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Guide\nsecond line\n", encoding="utf-8")
    return make_located_finding(root, "docs/guide.md", 2, "guide-present", "second line", "second line")


# spec: PIPE-PAGES-R020.7
def test_located_finding_schema(tmp_path: Path) -> None:
    finding = _located_fixture(tmp_path)
    assert is_dataclass(finding)
    assert finding.source_path == "docs/guide.md"
    assert finding.line == 2
    assert finding.source_digest.startswith("sha256:")
    assert finding.evidence_digest.startswith("sha256:")
    assert finding.as_dict()["observed"] == "second line"
    with pytest.raises(FrozenInstanceError):
        finding.line = 3  # type: ignore[misc]


# spec: PIPE-PAGES-R020.8
def test_located_evidence_matches_tree(tmp_path: Path) -> None:
    finding = _located_fixture(tmp_path)
    assert validate_located_evidence(tmp_path, finding, measured="second line") is None

    (tmp_path / "docs" / "guide.md").write_text("# Changed\nsecond line\n", encoding="utf-8")
    stale = validate_located_evidence(tmp_path, finding, measured="second line")
    assert stale == FindingRefusal("docs/guide.md", 2, "source-digest-mismatch")

    current_digest = source_digest(tmp_path, "docs/guide.md")
    out_of_range = LocatedFinding(
        "docs/guide.md",
        99,
        current_digest,
        "guide-present",
        "missing",
        "present",
        evidence_digest_for("docs/guide.md", 99, current_digest, "guide-present", "missing", "present"),
    )
    assert validate_located_evidence(tmp_path, out_of_range, measured="missing") == FindingRefusal(
        "docs/guide.md", 99, "invalid-line"
    )


# spec: PIPE-PAGES-R020.9
def test_finding_validator_is_wired(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    repo.commit(
        {
            "README.md": (
                "# fixture\n\n<!-- claim:path docs/missing.md -->\n\n## Installation\n\n```bash\nuv sync\n```\n"
            )
        },
        "docs",
    )
    observed: list[LocatedFinding] = []
    original = validate_located_evidence

    def spy(root: Path, finding: LocatedFinding, *, measured: object = object()) -> FindingRefusal | None:
        observed.append(finding)
        return original(root, finding, measured=measured)

    monkeypatch.setattr("pipelines_hooks.docs.claims.validate_located_evidence", spy)
    from pipelines_hooks.docs.public_surface import validate

    evidence: list[LocatedFinding] = []
    refusals: list[FindingRefusal] = []
    findings = validate(repo.root, located_findings=evidence, refusals=refusals)
    assert findings[-1] == "README.md:3 path docs/missing.md"
    assert observed == evidence
    assert evidence[0].rule == "claim:path"
    assert refusals == []


# spec: PIPE-PAGES-R020.10
def test_unsupported_finding_refused(tmp_path: Path) -> None:
    finding = _located_fixture(tmp_path)
    assert validate_located_evidence(
        tmp_path,
        LocatedFinding(
            "/outside/guide.md",
            2,
            finding.source_digest,
            finding.rule,
            finding.observed,
            finding.expected,
            finding.evidence_digest,
        ),
    ) == FindingRefusal("/outside/guide.md", 2, "unsafe-path")
    assert validate_located_evidence(
        tmp_path,
        LocatedFinding(
            "docs/guide.md",
            2,
            finding.source_digest,
            finding.rule,
            None,
            finding.expected,
            evidence_digest_for("docs/guide.md", 2, finding.source_digest, finding.rule, None, finding.expected),
        ),
    ) == FindingRefusal("docs/guide.md", 2, "missing-measurement")
    assert validate_located_evidence(
        tmp_path,
        LocatedFinding(
            "docs/guide.md",
            0,
            finding.source_digest,
            finding.rule,
            finding.observed,
            finding.expected,
            evidence_digest_for(
                "docs/guide.md", 0, finding.source_digest, finding.rule, finding.observed, finding.expected
            ),
        ),
    ) == FindingRefusal("docs/guide.md", 0, "invalid-line")
    with pytest.raises(CannotRun, match="malformed digest"):
        validate_located_evidence(
            tmp_path,
            LocatedFinding(
                "docs/guide.md",
                2,
                "not-a-digest",
                finding.rule,
                finding.observed,
                finding.expected,
                finding.evidence_digest,
            ),
            measured=finding.observed,
        )


# spec: PIPE-PAGES-R020.11
def test_located_evidence_export(tmp_path: Path) -> None:
    finding = _located_fixture(tmp_path)
    secret = LocatedFinding(
        finding.source_path,
        finding.line,
        finding.source_digest,
        finding.rule,
        "token=super-secret-value",
        finding.expected,
        evidence_digest_for(
            finding.source_path,
            finding.line,
            finding.source_digest,
            finding.rule,
            "token=super-secret-value",
            finding.expected,
        ),
    )
    refusal = FindingRefusal("docs/guide.md", 9, "invalid-line")
    exported = export_located_evidence([secret], [refusal])
    assert exported == export_located_evidence([secret], [refusal])
    payload = json.loads(exported)
    assert payload["findings"][0]["source_path"] == "docs/guide.md"
    assert payload["refusals"] == [{"line": 9, "reason": "invalid-line", "source_path": "docs/guide.md"}]
    assert "super-secret-value" not in exported
    assert str(tmp_path) not in exported


# spec: PIPE-PAGES-R020.12
def test_public_surface_located_evidence_cli(repo: Repo) -> None:
    repo.commit(
        {
            "README.md": (
                "# fixture\n\n<!-- claim:path docs/missing.md -->\n\n## Installation\n\n```bash\nuv sync\n```\n"
            ),
            "docs/asset.md": "# Asset\n",
        },
        "docs",
    )
    executable = shutil.which("pipelines-hook")
    assert executable is not None
    command = [executable, "public-surface", "--root", str(repo.root)]
    stale = subprocess.run(command, cwd=repo.root, env=sanitized_env(), capture_output=True, text=True, check=False)
    assert stale.returncode == 1
    assert "README.md:3 path docs/missing.md" in stale.stdout
    assert '"source_path":"README.md"' in stale.stdout

    empty_evidence = repo.root.parent / "empty-located-evidence.json"
    empty_evidence.write_text(export_located_evidence([]), encoding="utf-8")
    bypass_attempt = subprocess.run(
        [*command, "--evidence", str(empty_evidence)],
        cwd=repo.root,
        env=sanitized_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert bypass_attempt.returncode == 1
    assert "README.md:3 path docs/missing.md" in bypass_attempt.stdout

    repo.write(
        "README.md",
        "# fixture\n\n<!-- claim:path docs/asset.md -->\n\n## Installation\n\n```bash\nuv sync\n```\n",
    )
    repaired = subprocess.run(command, cwd=repo.root, env=sanitized_env(), capture_output=True, text=True, check=False)
    assert repaired.returncode == 0
    assert "public surface: clean" in repaired.stdout

    repo.write(
        "README.md",
        "# fixture\n\n<!-- claim:diagram-node missing-node -->\n\n## Installation\n\n```bash\nuv sync\n```\n",
    )
    unsupported = subprocess.run(
        command, cwd=repo.root, env=sanitized_env(), capture_output=True, text=True, check=False
    )
    assert unsupported.returncode == 2
    assert "unsupported-finding" in unsupported.stderr


# spec: PIPE-PAGES-R020.12
def test_public_surface_persisted_evidence_cli_covers_refusals(repo: Repo) -> None:
    repo.commit(
        {
            "README.md": "# fixture\n\n## Installation\n\n```bash\nuv sync\n```\n",
        },
        "docs",
    )
    executable = shutil.which("pipelines-hook")
    assert executable is not None
    command = [executable, "public-surface", "--root", str(repo.root)]
    evidence_path = repo.root.parent / "located-evidence.json"

    stale = make_located_finding(repo.root, "README.md", 1, "claim:path", False, True)
    evidence_path.write_text(export_located_evidence([stale]), encoding="utf-8")
    measured_failure = subprocess.run(
        [*command, "--evidence", str(evidence_path)],
        cwd=repo.root,
        env=sanitized_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert measured_failure.returncode == 1
    assert "README.md:1 claim:path" in measured_failure.stdout

    missing_measurement = make_located_finding(repo.root, "README.md", 1, "claim:path", None, True)
    evidence_path.write_text(export_located_evidence([missing_measurement]), encoding="utf-8")
    missing = subprocess.run(
        [*command, "--evidence", str(evidence_path)],
        cwd=repo.root,
        env=sanitized_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 2
    assert "missing-measurement" in missing.stderr

    out_of_range = make_located_finding(repo.root, "README.md", 99, "claim:path", False, True)
    evidence_path.write_text(export_located_evidence([out_of_range]), encoding="utf-8")
    invalid_line = subprocess.run(
        [*command, "--evidence", str(evidence_path)],
        cwd=repo.root,
        env=sanitized_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert invalid_line.returncode == 2
    assert "invalid-line" in invalid_line.stderr

    changed_source = make_located_finding(repo.root, "README.md", 1, "claim:path", False, True)
    evidence_path.write_text(export_located_evidence([changed_source]), encoding="utf-8")
    repo.write("README.md", "# changed\n\n## Installation\n\n```bash\nuv sync\n```\n")
    changed = subprocess.run(
        [*command, "--evidence", str(evidence_path)],
        cwd=repo.root,
        env=sanitized_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert changed.returncode == 2
    assert "source-digest-mismatch" in changed.stderr

    repaired = subprocess.run(command, cwd=repo.root, env=sanitized_env(), capture_output=True, text=True, check=False)
    assert repaired.returncode == 0
    assert "public surface: clean" in repaired.stdout
