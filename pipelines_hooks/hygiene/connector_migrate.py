"""connector-ontology-map migrate: the manifest-cut codemod for one connector repo (PIPE-GATES-R016.10 to R016.15).

Deterministic and idempotent; no LLM, no per-repo judgement. Hard cutover: the connector ends fully on the
live-declaration layout, with no transitional file, alias or deprecation note.

* a. write ``<pkg>/connector_sources.py`` from the manifest, presets, ingest sources (fixed template)
* b. delete the five cut files and their package-data / MANIFEST.in entries
* c. strip ``extends`` / ``compose`` from ``<pkg>/prompts/*.json``
* d. ontology rules R1-R4 through ``fix --pack`` (run before b so manifest relations still inform R8)
* e. SDK floor ``>=0.4.0`` and a patch bump from ``.bumpversion.cfg``; ``uv lock``
* f. rewrite tests by fixed rules; anything else goes to the review list, never edited by hand

Everything a rule does not cover is a ``review`` item (``blocking`` stops the repo in the batch driver).
"""

from __future__ import annotations

import configparser
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml

SDK_FLOOR = "0.4.0"
CUT_NAMES = (
    "connector_manifest.yml",
    "mcp_source_presets.json",
    "tool_schema_fingerprints.json",
    "ingest_sources.json",
    "data_resources.json",
)
MODULE_NAME = "connector_sources"
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".tox", "dist", "build"}
_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_DIRECT = {"records_path", "id_field", "title_field", "text_field", "server"}
_CUT_WORDS = (
    "connector_manifest",
    "mcp_source_presets",
    "tool_schema_fingerprints",
    "ingest_sources.json",
    "data_resources",
    "load_manifest",
    "load_ingest_sources",
    "ConnectorManifest",
    "load_tool_presets",
    "manifest://",
)


class Review:
    """Collects review items; ``blocking`` ones fail the repo."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, step: str, detail: str, path: str = "", blocking: bool = True) -> None:
        self.items.append({"step": step, "path": path, "detail": detail, "blocking": blocking})


def walk(root: Path) -> list[Path]:
    """Every file under root, sorted, skipping tool and VCS directories."""
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).parts
        if SKIP_DIRS.intersection(rel) or not (p.is_file() or p.is_symlink()):
            continue
        out.append(p)
    return out


def package_dir(root: Path) -> Path | None:
    """The connector package named by the ``agent_connector_sdk.connector`` entry point."""
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    eps = data.get("project", {}).get("entry-points", {}).get("agent_connector_sdk.connector", {})
    for value in eps.values():
        pkg = root / str(value).split(":")[0].split(".")[0]
        if pkg.is_dir():
            return pkg
    return None


# ---------------------------------------------------------------- a. declarations
def _py(obj: Any, level: int = 0) -> str:
    """A deterministic, ruff-stable Python literal: sorted keys, one item per line, trailing commas."""
    pad = "    " * (level + 1)
    end = "    " * level
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        body = "".join(f"{pad}{json.dumps(str(k))}: {_py(obj[k], level + 1)},\n" for k in sorted(obj, key=str))
        return "{\n" + body + end + "}"
    if isinstance(obj, (list, tuple)):
        if not obj:
            return "()"
        return "(\n" + "".join(f"{pad}{_py(v, level + 1)},\n" for v in obj) + end + ")"
    if isinstance(obj, str):
        return json.dumps(obj)
    return repr(obj)


def _call(entry: dict[str, Any]) -> str:
    keys = ["tool", "source_id", "record_type", "id_field"] + sorted(
        k for k in entry if k not in ("tool", "source_id", "record_type", "id_field")
    )
    body = "".join(f"        {k}={_py(entry[k], 2)},\n" for k in keys)
    return f"    source_meta(\n{body}    ),\n"


def _norm(text: str) -> str:
    t = re.sub(r"[^a-z0-9]", "", str(text).lower())
    return t[:-3] + "y" if t.endswith("ies") else (t[:-1] if t.endswith("s") and not t.endswith("ss") else t)


def _record_type(tool: str, doc_type: str, keys: list[str]) -> str | None:
    """Fixed rule: mapping key equal to a trailing tool noun, else to doc_type; else None."""
    by_norm = {_norm(k): k for k in keys}
    tail = [_norm(w) for w in reversed(tool.split("_"))]
    for cand in [*tail, _norm(doc_type)]:
        if cand and cand in by_norm:
            return by_norm[cand]
    return None


def _load_inputs(root: Path, pkg: Path, review: Review) -> dict[str, Any]:
    found: dict[str, list[Path]] = {n: [] for n in CUT_NAMES}
    for p in walk(root):
        if p.name in found:
            found[p.name].append(p)
    manifest: dict[str, Any] = {}
    for p in found["connector_manifest.yml"]:
        if p.exists():
            manifest = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            break
    presets: dict[str, Any] = {}
    for p in found["mcp_source_presets.json"]:
        presets = json.loads(p.read_text(encoding="utf-8"))
    ingest: dict[str, Any] = {}
    for p in found["ingest_sources.json"]:
        ingest = json.loads(p.read_text(encoding="utf-8"))
    for p in found["data_resources.json"]:
        review.add(
            "declarations",
            "data_resources.json has no fixed rule; fold into the declaration by hand",
            str(p.relative_to(root)),
        )
    return {"found": found, "manifest": manifest, "presets": presets, "ingest": ingest}


def build_sources(inputs: dict[str, Any], review: Review) -> dict[str, Any] | None:
    """The module content, or None when no input file exists (already migrated)."""
    manifest, presets, ingest = inputs["manifest"], inputs["presets"], inputs["ingest"]
    if not (manifest or presets or ingest):
        return None
    mappings = {**ingest.get("schema_mappings", {}), **manifest.get("schema_mappings", {})}
    keys = sorted(mappings)
    sync_raw = {s["preset"]: s.get("raw", {}) for s in manifest.get("sync", []) if "preset" in s}
    entries: list[dict[str, Any]] = []
    ingest_by_tool = {s["tools"][0]: s for s in ingest.get("sources", []) if s.get("tools")}
    for name in sorted({k for k in presets if not k.startswith("_")} | set(sync_raw)):
        p = dict(presets.get(name) or sync_raw[name])
        if name in presets and name in sync_raw and {k: v for k, v in p.items()} != sync_raw[name]:
            review.add(
                "declarations", f"preset {name!r} differs from manifest sync raw; preset file used", blocking=False
            )
        tool = p.pop("tool", None)
        if not tool or not _SOURCE_ID.match(name) or not p.get("id_field"):
            review.add("declarations", f"preset {name!r} lacks tool, id_field or a valid source id")
            continue
        rt = (ingest_by_tool.get(tool) or {}).get("record_type") or _record_type(tool, str(p.get("doc_type", "")), keys)
        if rt is None:
            rt = str(p.get("doc_type") or name)
            review.add(
                "declarations",
                f"record_type for preset {name!r} guessed as {rt!r} (no mapping matches)",
                blocking=False,
            )
        e: dict[str, Any] = {"tool": tool, "source_id": name, "record_type": rt}
        paged = p.get("pagination") == "page"
        for k in sorted(p):
            v = p[k]
            if v is None:
                continue
            if k in _DIRECT or (paged and k in ("page_param", "page_size_param")):
                e[k] = v
            elif k == "updated_field":
                e["cursor_field"] = v
            elif k == "pagination" and v in ("none", "page"):
                e[k] = v
            else:
                e.setdefault("preset", {})[k] = v
        e.setdefault("preset", {})
        entries.append(e)
    for s in sorted(ingest.get("sources", []), key=lambda s: s["source_id"]):
        if len(s.get("tools", [])) != 1:
            review.add("declarations", f"ingest source {s['source_id']!r} must name exactly one tool")
            continue
        e = {
            k: v
            for k, v in s.items()
            if k != "tools" and v not in (None, "", {}, False) or k in ("record_type", "id_field", "source_id")
        }
        e["tool"] = s["tools"][0]
        entries.append(e)
    ids = [e["source_id"] for e in entries]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        review.add("declarations", f"source id {dup!r} is declared twice")
    resources = [
        {k: r[k] for k in ("name", "label", "id_prefix") if r.get(k)}
        for r in manifest.get("resources", ingest.get("resources", []))
    ]
    connector = (
        ingest.get("connector")
        or manifest.get("connector")
        or next((p.get("server") for p in presets.values() if isinstance(p, dict) and p.get("server")), None)
    )
    if not connector:
        review.add("declarations", "connector name not found in manifest, ingest sources or presets")
    mapped = {
        k: {"ontology_class": v.get("ontology_class"), "fields": v.get("fields", {})} for k, v in mappings.items()
    }
    return {"connector": connector or "", "entries": entries, "mappings": mapped, "resources": resources}


TEMPLATE = '''"""Data sources of this connector, declared by tool name (generated by connector-ontology-map migrate).

Served live as ``connector://resources``. Regenerate by editing the declarations, not the tools.
"""

# ruff: noqa: E501
from __future__ import annotations

from agent_connector_sdk.ingest.live_declaration import source_meta
from agent_connector_sdk.ingest.sources import IngestSourceDeclaration, IngestSourceSpec

CONNECTOR = {connector}

SOURCES = (
{sources})

SCHEMA_MAPPINGS = {mappings}

RESOURCES = {resources}


def declaration() -> IngestSourceDeclaration:
    """The declaration the server assembles from this module."""
    specs = []
    for item in SOURCES:
        for entry in item["connector_sources"]:
            body = {{k: v for k, v in entry.items() if k not in ("tool", "mapping")}}
            specs.append(IngestSourceSpec.model_validate({{**body, "tools": (entry["tool"],)}}))
    return IngestSourceDeclaration.model_validate(
        {{
            "connector": CONNECTOR,
            "sources": specs,
            "schema_mappings": SCHEMA_MAPPINGS,
            "resources": RESOURCES,
        }}
    )
'''


def render_module(content: dict[str, Any]) -> str:
    return TEMPLATE.format(
        connector=json.dumps(content["connector"]),
        sources="".join(_call(e) for e in content["entries"]),
        mappings=_py(content["mappings"]),
        resources=_py(content["resources"]),
    )


# ---------------------------------------------------------------- b. delete
def _strip_packaging(root: Path, changed: list[str]) -> None:
    pp = root / "pyproject.toml"
    text = pp.read_text(encoding="utf-8")
    names = "|".join(re.escape(n) for n in CUT_NAMES)
    new = re.sub(rf'"(?:[^"\n]*/)?(?:{names})"\s*,\s?', "", text)
    new = re.sub(rf',\s*"(?:[^"\n]*/)?(?:{names})"(?=\s*\])', "", new)
    if new != text:
        pp.write_text(new, encoding="utf-8")
        changed.append("pyproject.toml")
    mi = root / "MANIFEST.in"
    if mi.is_file():
        lines = mi.read_text(encoding="utf-8").splitlines(keepends=True)
        kept = [ln for ln in lines if not any(n in ln for n in CUT_NAMES)]
        if kept != lines:
            mi.write_text("".join(kept), encoding="utf-8")
            changed.append("MANIFEST.in")


# ---------------------------------------------------------------- c. prompts
_PROMPT_LINE = re.compile(r'^\s*"(extends|compose)"\s*:\s*"[^"\n]*"\s*,?\s*$')


def strip_prompt(text: str) -> str | None:
    """The prompt JSON without top-level extends/compose, or None when not safely strippable."""
    try:
        old = json.loads(text)
    except ValueError:
        return None
    if not isinstance(old, dict) or not ({"extends", "compose"} & set(old)):
        return text
    lines = text.splitlines(keepends=True)
    out = [ln for ln in lines if not _PROMPT_LINE.match(ln)]
    new = "".join(out)
    new = re.sub(r",(\s*\n\s*\})", r"\1", new)
    try:
        ok = json.loads(new) == {k: v for k, v in old.items() if k not in ("extends", "compose")}
    except ValueError:
        ok = False
    return new if ok else None


def strip_certification(root: Path, pkg: Path, changed: list[str], review: Review) -> None:
    """Drop the cut files from the certification artifact digests (format-preserving only)."""
    p = pkg / "ontology" / "certification.json"
    if not p.is_file():
        return
    text = p.read_text(encoding="utf-8")
    data = json.loads(text)
    if json.dumps(data, indent=2, sort_keys=True) + "\n" != text:
        if any(n in text for n in CUT_NAMES):
            review.add(
                "certification",
                "certification.json is not in canonical format; strip by hand",
                str(p.relative_to(root)),
            )
        return
    arts = data.get("artifacts", {})
    kept = {k: v for k, v in arts.items() if Path(k).name not in CUT_NAMES}
    if kept != arts:
        data["artifacts"] = kept
        p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        changed.append(str(p.relative_to(root)))


# ---------------------------------------------------------------- e. versions
def _vt(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


_SDK_SPEC = re.compile(r"(agent-connector-sdk(?:\[[^\]]*\])?\s*>=\s*)(\d+(?:\.\d+)*)")


def bump_sdk_floor(root: Path, changed: list[str]) -> bool:
    """Raise every SDK floor below 0.4.0; True when something changed."""
    hit = False
    for name in ("pyproject.toml", "requirements.txt"):
        p = root / name
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        new = _SDK_SPEC.sub(lambda m: m.group(1) + SDK_FLOOR if _vt(m.group(2)) < _vt(SDK_FLOOR) else m.group(0), text)
        if new != text:
            p.write_text(new, encoding="utf-8")
            changed.append(name)
            hit = True
    return hit


def bump_patch(root: Path, changed: list[str], review: Review) -> str | None:
    cfg_path = root / ".bumpversion.cfg"
    if not cfg_path.is_file():
        review.add("version", "no .bumpversion.cfg; version not bumped")
        return None
    cfg = configparser.RawConfigParser()
    cfg.read(cfg_path, encoding="utf-8")
    cur = cfg["bumpversion"]["current_version"]
    major, minor, patch = (_vt(cur) + (0, 0, 0))[:3]
    new = f"{major}.{minor}.{patch + 1}"
    for section in cfg.sections():
        if not section.startswith("bumpversion:file"):
            continue
        fname = re.sub(r"^file(\([^)]*\))?:", "", section.split(":", 1)[1])
        target = root / fname
        search = cfg[section].get("search", "{current_version}").replace("{current_version}", cur)
        replace = cfg[section].get("replace", "{new_version}").replace("{new_version}", new)
        if not target.is_file() or search not in target.read_text(encoding="utf-8"):
            review.add("version", f"bump target {fname} does not contain {search!r}", fname)
            continue
        target.write_text(target.read_text(encoding="utf-8").replace(search, replace), encoding="utf-8")
        changed.append(fname)
    text = cfg_path.read_text(encoding="utf-8")
    cfg_path.write_text(re.sub(r"(?m)^(current_version\s*=\s*).*$", rf"\g<1>{new}", text, count=1), encoding="utf-8")
    changed.append(".bumpversion.cfg")
    return new


def refresh_lock(root: Path, review: Review, changed: list[str]) -> None:
    r = subprocess.run(
        ["uv", "lock", "--upgrade-package", "agent-connector-sdk"], cwd=root, capture_output=True, text=True
    )
    if r.returncode:
        review.add("lock", "uv lock failed: " + (r.stderr or r.stdout)[-400:], "uv.lock")
    else:
        changed.append("uv.lock")


# ---------------------------------------------------------------- f. tests
_LOAD_CALL = re.compile(r"load_ingest_sources\((?:[^()]|\([^()]*\))*\)")
_MANIFEST_READ = re.compile(
    r"^(?P<i>[ \t]*)manifest = yaml\.safe_load\((?:[^\n]*\n)*?(?P=i)\)\n|^[ \t]*manifest = yaml\.safe_load\([^\n]*\)\n",
    re.M,
)
_DELETE_NAME = re.compile(r"test_.*(manifest|fingerprint|preset)", re.I)


def rewrite_test(text: str, name: str, pkg: str) -> tuple[str | None, str]:
    """(new text, action) with action in keep/rewrite/delete/review; new text None for delete/review."""
    if not any(w in text for w in _CUT_WORDS):
        return text, "keep"
    if _DELETE_NAME.match(name) and "load_ingest_sources" not in text:
        return None, "delete"
    new = text
    if "load_ingest_sources" not in new and _MANIFEST_READ.search(new):
        new = _MANIFEST_READ.sub(lambda m: "" if "connector_manifest.yml" in m.group(0) else m.group(0), new)
        new = new.replace('manifest["schema_mappings"]', "declared_sources().schema_mappings")
        new = re.sub(r'\bmapping\["(ontology_class|fields)"\]', r"mapping.\1", new)
        if "manifest[" not in new and "manifest." not in new:
            new = re.sub(
                r"(?m)^((?:import|from) (?!__future__))",
                lambda m: f"from {pkg}.{MODULE_NAME} import declaration as declared_sources\n" + m.group(1),
                new,
                count=1,
            )
            for ident, line in (("yaml", r"import yaml\n"), ("Path", r"from pathlib import Path\n")):
                body = re.sub(line, "", new, count=1)
                if not re.search(rf"{ident}\b", body):
                    new = body
    if "load_ingest_sources" in new:
        new = new.replace(
            "from agent_connector_sdk.ingest.sources import load_ingest_sources",
            f"from {pkg}.{MODULE_NAME} import declaration as declared_sources",
        )
        new = _LOAD_CALL.sub("declared_sources()", new)
        new = _MANIFEST_READ.sub(lambda m: "" if "connector_manifest.yml" in m.group(0) else m.group(0), new)
        new = new.replace('manifest["schema_mappings"]', "declared_sources().schema_mappings")
        for ident, line in (
            ("yaml", r"import yaml\n"),
            ("Path", r"from pathlib import Path\n"),
            (pkg, rf"import {re.escape(pkg)}\n"),
        ):
            body = re.sub(line, "", new, count=1)
            if not re.search(rf"(?<!from ){re.escape(ident)}\b(?!\.{MODULE_NAME})", body):
                new = body
    if any(w in new for w in _CUT_WORDS if w != "ingest_sources.json") or "ingest_sources.json" in new:
        return None, "review"
    return new, "rewrite"


def migrate_tests(root: Path, pkg: str, changed: list[str], deleted: list[str], review: Review) -> None:
    for p in walk(root / "tests") if (root / "tests").is_dir() else []:
        if p.suffix != ".py":
            continue
        text = p.read_text(encoding="utf-8")
        new, action = rewrite_test(text, p.name, pkg)
        rel = str(p.relative_to(root))
        if action == "delete":
            specs = sorted(set(re.findall(r'spec\("([^"]+)"\)', text)))
            p.unlink()
            deleted.append(rel)
            review.add(
                "tests", f"deleted; was bound to specs {specs}: rebind or retire those rows", rel, blocking=False
            )
        elif action == "rewrite" and new != text:
            p.write_text(new, encoding="utf-8")
            changed.append(rel)
        elif action == "review":
            hits = [i + 1 for i, ln in enumerate(text.splitlines()) if any(w in ln for w in _CUT_WORDS)]
            review.add("tests", f"no fixed rule for lines {hits[:8]}", rel)


def leftover_references(root: Path, review: Review) -> None:
    """Any file still naming a cut file after the codemod is a review item (hard cutover)."""
    skip = {"uv.lock", "CHANGELOG.md"}
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True)
    names = {n for n in tracked.stdout.split("\0") if n} if tracked.returncode == 0 else None
    for p in walk(root):
        if names is not None and str(p.relative_to(root)) not in names:
            continue
        if p.suffix in {".pyc", ".png", ".svg", ".lock"} or p.name in skip or "specs" in p.relative_to(root).parts:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits = [i + 1 for i, ln in enumerate(text.splitlines()) if any(w in ln for w in _CUT_WORDS)]
        if hits:
            review.add(
                "leftover",
                f"still references a cut file at lines {hits[:8]}",
                str(p.relative_to(root)),
                blocking=p.suffix not in {".md", ".rst"},
            )


# ---------------------------------------------------------------- driver
def migrate(root: Path, eg_repo: Path | None = None, ref: str = "origin/main", lock: bool = True) -> dict[str, Any]:
    """Run every transform on one connector checkout and return the report."""
    root = Path(root)
    review = Review()
    changed: list[str] = []
    deleted: list[str] = []
    pkg = package_dir(root)
    if pkg is None:
        review.add("discover", "no agent_connector_sdk.connector entry point resolves to a package")
        return {"changed": [], "deleted": [], "review": review.items}
    inputs = _load_inputs(root, pkg, review)
    content = build_sources(inputs, review)
    if content is not None and not any(i["blocking"] and i["step"] == "declarations" for i in review.items):
        target = pkg / f"{MODULE_NAME}.py"
        target.write_text(render_module(content), encoding="utf-8")
        changed.append(str(target.relative_to(root)))
    elif content is not None:
        return {"changed": [], "deleted": [], "review": review.items}
    if eg_repo is not None:
        from pipelines_hooks.hygiene import ontology_codemod as oc

        result, patched = oc.fix_pack(root, eg_repo, ref)
        changed += patched
        if result["review_queue"]:
            counts = {r: sum(len(v) for v in rules.values()) for r, rules in result["review_queue"].items()}
            review.add(
                "ontology", f"R5-R8 review items: {sum(counts.values())} (see ontology review queue)", blocking=False
            )
    for name in CUT_NAMES:
        for p in walk(root):
            if p.name == name and name != "data_resources.json":
                deleted.append(str(p.relative_to(root)))
                p.unlink()
    _strip_packaging(root, changed)
    strip_certification(root, pkg, changed, review)
    for p in sorted((pkg / "prompts").glob("*.json")) if (pkg / "prompts").is_dir() else []:
        text = p.read_text(encoding="utf-8")
        new = strip_prompt(text)
        if new is None:
            review.add("prompts", "extends/compose line not strippable by the fixed rule", str(p.relative_to(root)))
        elif new != text:
            p.write_text(new, encoding="utf-8")
            changed.append(str(p.relative_to(root)))
    if bump_sdk_floor(root, changed):
        bump_patch(root, changed, review)
        if lock and (root / "uv.lock").is_file():
            refresh_lock(root, review, changed)
    migrate_tests(root, pkg.name, changed, deleted, review)
    leftover_references(root, review)
    return {"changed": sorted(set(changed)), "deleted": sorted(set(deleted)), "review": review.items}


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="connector-ontology-map migrate", description=__doc__)
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument(
        "--eg-repo",
        type=Path,
        default=None,
        help="epistemic-graph checkout for the ontology rules (omit to skip step d)",
    )
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--no-lock", action="store_true", help="skip the uv.lock refresh")
    ap.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    args = ap.parse_args(argv)
    report = migrate(args.root, args.eg_repo, args.ref, not args.no_lock)
    text = json.dumps(report, indent=1, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 2 if any(i["blocking"] for i in report["review"]) else 0


if __name__ == "__main__":
    sys.exit(main())
