"""Stub bundle command: writes one harness tree, and a credential when STUB_WRITE_TOKEN is set."""

import argparse
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--harness", required=True)
parser.add_argument("--out", required=True)
args = parser.parse_args()
out = Path(args.out)
out.mkdir(parents=True)
(out / "plugin.json").write_text('{"name": "stub", "harness": "%s"}\n' % args.harness)
if os.environ.get("STUB_WRITE_TOKEN"):
    (out / "settings.json").write_text('{"token": "ghp_' + "a1B2c3D4e5" * 4 + '"}\n')
