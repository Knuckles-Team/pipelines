"""Build an isolated review artifact; never write the live explorer or Pages."""

import argparse
import lzma
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def prepare(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    source_receipt = json.loads((HERE / "theme-provenance.json").read_text())
    archive = (HERE / "snapshot.json.xz").read_bytes()
    assert hashlib.sha256(archive).hexdigest() == source_receipt["snapshotArchiveSha256"]
    with lzma.open(HERE / "snapshot.json.xz", "rt", encoding="utf-8") as stream:
        data = json.load(stream)
    assert len(data["stories"]) == 598
    assert data["stories"]["root"]["evidence"]["subtreeRows"] == 8366
    for story in data["stories"].values():
        keys = [key for group in story["families"].values() for key in group]
        assert len(keys) == len(set(keys)) == story["evidence"]["subtreeRows"]
        assert all(key in data["rowIndex"] for key in keys)
    template = (HERE / "template.html").read_text()
    page = template.replace("/*STORIES*/", json.dumps(data).replace("<", "\\u003c"))
    (output / "prototype.html").write_text(page)
    shutil.copyfile(HERE / "theme.css", output / "architecture-theme.css")
    assets = output / "assets"
    assets.mkdir(exist_ok=True)
    source = HERE.parents[1] / "scripts/architecture_explorer/assets"
    for name in ("InterVariable.woff2", "Inter-LICENSE.txt"):
        shutil.copyfile(source / name, assets / name)
    assert hashlib.sha256((assets / "InterVariable.woff2").read_bytes()).hexdigest() == source_receipt["fontSha256"]
    shutil.copyfile(HERE / "theme-provenance.json", output / "theme-provenance.json")
    receipt = {
        "kind": "Preview-only study, not canonical deployment",
        "sourceSnapshot": data["provenance"],
        "htmlSha256": hashlib.sha256(page.encode()).hexdigest(),
        "snapshotArchiveSha256": hashlib.sha256((HERE / "snapshot.json.xz").read_bytes()).hexdigest(),
        "allNodeInvariants": 598,
        "browserAcceptance": "pending separate browser receipt",
    }
    (output / "provenance.json").write_text(json.dumps(receipt, indent=2))
    (output / "README.txt").write_text(
        "Preview-only composition study. Open prototype.html with its adjacent CSS/assets.\n"
        "The capability matrix is a composition surrogate, not the live canvas.\n"
        "Spec state is not runtime health or guaranteed completion.\n"
        "No deployment is performed. Native browser zoom acceptance is separate from CSS 200% stress.\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output.resolve())
