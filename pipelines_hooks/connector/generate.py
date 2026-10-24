"""connector-generate: the shared SHACL governance shapes and the certification record, generated at release.

    pipelines-connector generate [--root R] [--check]

Deterministic (the chosen option): the release workflow writes both files into the build
tree before the wheel is built, from files the connector does commit, so the wheel carries
them and the repository does not.

* ``<pkg>/ontology/shapes/connector.shacl.ttl``: one ``<Class>GovernanceShape`` per class the
  connector's ``<pkg>/ontology/<ontology_source>.ttl`` declares as ``:<Class> a owl:Class``
  (``ontology_source`` is read from ``ontology/mappings/source.yaml``), sorted by class name.
  ``[tool.pipelines.ontology] shape_classes`` replaces the derived list; ``ttl`` names the ontology file (stem) when
  it is not called ``<ontology_source>.ttl`` (the shapes keep the ``ontology_source`` domain).
* ``<pkg>/ontology/certification.json``: SHA-256 digests of the committed artifacts that exist
  (manifest, presets, fingerprints, fixtures, mappings, migrations, ontology), the generated
  shapes, fixed compatibility ranges, and ``validated_at`` from ``SOURCE_DATE_EPOCH`` or the
  last commit time (epoch 0 outside git). Same inputs give the same bytes.

``--check`` writes nothing and exits 1 when a tracked copy of either file exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipelines_hooks.connector import project
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root, run_git

SHAPE_PROPERTIES = ("sourceRecordRef", "tenantReference", "accessPolicyReference", "provenanceReference")
COMPATIBILITY = {"agent_utilities": ">=2.5.0,<3", "bundle_schema": "2", "epistemic_graph": ">=2.27.0,<3"}
CHECKS = ("declared_tool_schema", "manifest_integrity", "privacy_contract", "shacl_parse", "synthetic_fixture_contract")
CLASS_RE = re.compile(r"^:([A-Za-z0-9_]+)\s+a\s+owl:Class\b", re.M)
SOURCE_RE = re.compile(r"^ontology_source:\s*['\"]?([A-Za-z0-9_.-]+)", re.M)
ARTIFACTS = (
    "connector_manifest.yml",
    "{pkg}/connectors/mcp_source_presets.json",
    "{pkg}/connectors/tool_schema_fingerprints.json",
    "{pkg}/ontology/fixtures/records.json",
    "{pkg}/ontology/mappings/source.yaml",
    "{pkg}/ontology/{source}.ttl",
    "{pkg}/ontology/migrations/manifest.json",
    "{pkg}/ontology/shapes/connector.shacl.ttl",
)


def _domain(package: Path) -> str:
    mapping = package / "ontology" / "mappings" / "source.yaml"
    match = SOURCE_RE.search(mapping.read_text(encoding="utf-8")) if mapping.is_file() else None
    if not match:
        raise CannotRun(f"{mapping} must declare ontology_source")
    return match.group(1)


def shacl(domain: str, classes: list[str]) -> str:
    head = (
        "@prefix : <http://knuckles.team/kg#> .\n"
        f"@prefix shape: <http://knuckles.team/kg/{domain}/shape#> .\n"
        "@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
    )
    props = " ;\n".join(
        f"    sh:property [\n        sh:path :{p} ;\n        sh:minCount 1 ; sh:maxCount 1 ; sh:datatype xsd:string\n    ]"
        for p in SHAPE_PROPERTIES
    )
    shapes = "".join(
        f"\nshape:{c}GovernanceShape a sh:NodeShape ;\n    sh:targetClass :{c} ;\n    sh:closed false ;\n{props} .\n"
        for c in sorted(set(classes))
    )
    return head + shapes


def _validated_at(root: Path) -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH", "")
    if not epoch.isdigit():
        result = run_git(root, ("log", "-1", "--format=%ct"))
        epoch = result.stdout.strip() if result.returncode == 0 and result.stdout.strip().isdigit() else "0"
    return datetime.fromtimestamp(int(epoch), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def certification(root: Path, package: Path, dist: str, domain: str, ttl_stem: str = "") -> dict[str, Any]:
    names = [a.format(pkg=package.name, source=ttl_stem or domain) for a in ARTIFACTS]
    digests = {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in names if (root / n).is_file()}
    return {
        "api_version": "graphos.io/v1",
        "artifacts": dict(sorted(digests.items())),
        "checks": dict.fromkeys(CHECKS, "passed"),
        "compatibility": COMPATIBILITY,
        "connector": dist,
        "kind": "ConnectorSourceAttestation",
        "live_certified": False,
        "mode": "offline-source",
        "schema_version": "2",
        "signature": None,
        "signature_algorithm": "none",
        "signer": "UNSIGNED-PREVIEW",
        "signing_public_key": "",
        "status": "source-validated",
        "validated_at": _validated_at(root),
    }


def generate(root: Path) -> dict[Path, str]:
    """``{path: text}`` of the two generated files for the connector at ``root``."""
    pyproject = project.load(root)
    package = project.package_dir(root, pyproject)
    domain = _domain(package)
    table = pyproject.get("tool", {}).get("pipelines", {}).get("ontology", {})
    stem = str(table.get("ttl", domain))
    ttl = package / "ontology" / f"{stem}.ttl"
    if not ttl.is_file():
        raise CannotRun(f"{ttl} is missing")
    override = table.get("shape_classes")
    classes = [str(c) for c in override] if override else CLASS_RE.findall(ttl.read_text(encoding="utf-8"))
    shapes_path = package / "ontology" / "shapes" / "connector.shacl.ttl"
    shapes_path.parent.mkdir(parents=True, exist_ok=True)
    shapes_path.write_text(shacl(domain, classes), encoding="utf-8")  # digested below
    record = certification(root, package, str(pyproject["project"]["name"]), domain, stem)
    cert_path = package / "ontology" / "certification.json"
    return {shapes_path: shacl(domain, classes), cert_path: json.dumps(record, indent=2, sort_keys=True) + "\n"}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-generate", description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = repo_root(args.root) if args.check else args.root
    if args.check:
        from pipelines_hooks.connector.files import findings

        bad = [f for f in findings(root) if "connector-generate" in f]
        for line in bad:
            print(f"connector-generate: {line}")
        return 1 if bad else 0
    for path, text in generate(root).items():
        path.write_text(text, encoding="utf-8")
        print(f"connector-generate: wrote {path.relative_to(root)}")
    return 0
