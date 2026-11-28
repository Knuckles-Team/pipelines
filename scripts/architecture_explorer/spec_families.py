"""Every spec directory has a node in the architecture model.

The explorer places each spec row by its family, the spec directory name. A family with no node
makes the source-chart build refuse the family. This check runs the same test on the working tree,
so a change that adds or renames a spec directory also changes the model.

    python -m scripts.architecture_explorer.spec_families [SPECS_DIR ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pipelines_hooks.specs.family_scope import family_dirs, is_owned, owned_families

MODEL = Path(__file__).with_name("model.json")
#: The repository whose own ``specs/`` tree this module checks; other repositories use
#: ``pipelines-hook spec-family-coverage`` (PIPE-GATES-R061.1).
REPOSITORY = "pipelines"


def model_families(model: dict, repository: str = REPOSITORY) -> set[str]:
    """Every family a node of ``repository`` lists; another repository's ``fam`` entry never counts."""
    return owned_families(model, repository)


def spec_families(specs_dir: Path) -> list[str]:
    return family_dirs(specs_dir)


def unmapped(specs_dir: Path, model: dict, repository: str = REPOSITORY) -> list[str]:
    known = model_families(model, repository)
    return [name for name in spec_families(specs_dir) if not is_owned(known, name)]


def main(argv: list[str]) -> int:
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    missing = [f"{d}/{n}" for d in (argv or ["specs"]) for n in unmapped(Path(d), model)]
    for entry in missing:
        print(f"  - {entry}: no architecture model node lists this spec directory in `fam`")
    if missing:
        print("explorer-spec-families FAILED: add a node or a `fam` entry in scripts/architecture_explorer/model.json.")
        return 1
    print("explorer-spec-families: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
