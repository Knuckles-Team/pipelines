"""Shared exact-ref workflow mutation and negative CLI receipt assertions."""

import json

from pages_fleet_fixtures import declaration_file, revise
from scripts.check_five_repo_parity import main


def replace_workflow(root, declaration, old, new):
    """Commit a literal replacement in the first consumer's workflow."""
    def mutate(target):
        path = target / ".github/workflows/pages.yml"
        path.write_text(path.read_text().replace(old, new))

    return revise(root, declaration, mutate)


def assert_unverified_receipt(root, declaration, capsys):
    """Check both process status and the complete emitted machine receipt."""
    path = declaration_file(root / "declaration", declaration)
    assert main(["--declaration", str(path), "--fixtures", str(root)]) == 2
    assert json.loads(capsys.readouterr().out)["verification"]["status"] == "unverified"
