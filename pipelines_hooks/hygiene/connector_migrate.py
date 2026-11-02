"""connector-ontology-map migrate: the manifest-cut codemod for one connector repo (PIPE-GATES-R016.10 to R016.15).

Deterministic and idempotent; no LLM, no per-repo judgement. Hard cutover: the connector ends fully on the
live-declaration layout, with no transitional file, alias or deprecation note.

* a. write ``<pkg>/connector_sources.py`` from the manifest, presets, ingest sources (fixed template)
* b. delete the five cut files and their package-data / MANIFEST.in entries
* c. strip ``extends`` / ``compose`` from ``<pkg>/prompts/*.json``
* d. ontology rules R1-R4 through ``fix --pack`` (run before b so manifest relations still inform R8)
* e. SDK floor ``>=0.4.1`` and a patch bump from ``.bumpversion.cfg``; ``uv lock``
* f. rewrite tests by fixed rules; anything else goes to the review list, never edited by hand

Everything a rule does not cover is a ``review`` item (``blocking`` stops the repo in the batch driver).
"""

from __future__ import annotations

import ast
import configparser
import datetime
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tokenize
import tomllib
from pathlib import Path
from typing import Any

import yaml

from pipelines_hooks.core.distributions import SDK as SDK_ROLE
from pipelines_hooks.core.distributions import is_distribution, project_distribution, requirement_name

SDK_FLOOR = "0.4.1"
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
    "source_connector_providers",
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
    """The connector package named by the ``scion_sdk.connector`` entry point."""
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    eps = data.get("project", {}).get("entry-points", {}).get("scion_sdk.connector", {})
    for value in eps.values():
        pkg = root / str(value).split(":")[0].split(".")[0]
        if pkg.is_dir():
            return pkg
    return None


# ---------------------------------------------------------------- a. declarations
def _py(obj: Any, level: int = 0, nested: bool = False) -> str:
    """A deterministic, ruff-stable Python literal: sorted keys, one item per line, trailing commas."""
    pad = "    " * (level + 1)
    end = "    " * level
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        body = "".join(f"{pad}{json.dumps(str(k))}: {_py(obj[k], level + 1, True)},\n" for k in sorted(obj, key=str))
        return "{\n" + body + end + "}"
    if isinstance(obj, (list, tuple)):
        # a list inside a dict is a JSON value (the SDK model rejects tuples there); a top-level list stays a tuple
        o, c, empty = ("[", "]", "[]") if nested else ("(", ")", "()")
        if not obj:
            return empty
        return o + "\n" + "".join(f"{pad}{_py(v, level + 1, nested)},\n" for v in obj) + end + c
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


def action_tool_candidates(tool: str, action: str, server: str, served: set[str]) -> list[str]:
    """R016.27: served tools named <tool prefix> + action words, or <server stem> / <tool prefix> + action + the rest of the tool."""
    words = tool.split("_")
    stem = re.sub(r"[-_](mcp|agent|api)$", "", server or "").replace("-", "_")
    names: set[str] = {f"{tool}_{action}"}
    for k in range(1, len(words) + 1):
        pre = "_".join(words[:k])
        names.add(f"{pre}_{action}")
        if k < len(words):
            names.add(f"{pre}_{action}_{'_'.join(words[k:])}")
    if stem:
        names |= {f"{stem}_{action}", f"{stem}_{action}_{tool}"}
    return sorted(names & served)


def build_sources(inputs: dict[str, Any], review: Review, served: set[str] | None = None) -> dict[str, Any] | None:
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
        if tool and isinstance(p.get("action"), str) and served is not None:
            found = action_tool_candidates(tool, p["action"], str(p.get("server", "")), served)
            if len(found) == 1:
                tool = found[0]
                p.pop("action")
            else:
                review.add(
                    "declarations",
                    f"preset {name!r} calls tool {tool!r} with action {p['action']!r}: {len(found)} served tools match {found}",
                )
        elif tool and isinstance(p.get("action"), str):
            review.add(
                "declarations",
                f"preset {name!r} calls tool {tool!r} with an action; check the split tool name",
                blocking=False,
            )
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
    by_tool = {e["tool"]: e for e in entries}
    entries = []
    merged: set[str] = set()
    for src in sorted(ingest.get("sources", []), key=lambda s: s["source_id"]):
        if len(src.get("tools", [])) != 1:
            review.add("declarations", f"ingest source {src['source_id']!r} must name exactly one tool")
            continue
        own = {
            k: v
            for k, v in src.items()
            if k != "tools" and (v not in (None, "", {}, False) or k in ("record_type", "id_field", "source_id"))
        }
        tool = src["tools"][0]
        base = by_tool.get(tool)
        if base is not None and tool not in merged:
            # One source per tool: the ingest id wins, the preset id is dropped; ingest fields override preset fields.
            merged.add(tool)
            entry = {**base, **own, "tool": tool}
            entry["preset"] = base.get("preset", {})
        else:
            entry = {**own, "tool": tool}
        entries.append(entry)
    entries += [e for t, e in by_tool.items() if t not in merged]
    entries.sort(key=lambda e: e["source_id"])
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

from typing import Any

from scion_sdk.ingest.live_declaration import source_meta
from scion_sdk.ingest.sources import IngestSourceDeclaration, IngestSourceSpec

CONNECTOR: str = {connector}

SOURCES: tuple[Any, ...] = (
{sources})

SCHEMA_MAPPINGS: dict[str, Any] = {mappings}

RESOURCES: tuple[dict[str, str], ...] = {resources}


def declaration() -> IngestSourceDeclaration:
    """The declaration the server assembles from this module."""
    specs: list[IngestSourceSpec] = []
    for item in SOURCES:
        for entry in item["connector_sources"]:
            body: dict[str, Any] = {{
                k: v for k, v in entry.items() if k not in ("tool", "mapping")
            }}
            spec = {{**body, "tools": (entry["tool"],)}}
            specs.append(IngestSourceSpec.model_validate(spec))
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
    text = TEMPLATE.format(
        connector=json.dumps(content["connector"]),
        sources="".join(_call(e) for e in content["entries"]),
        mappings=_py(content["mappings"]),
        resources=_py(content["resources"]),
    )
    if not content["entries"]:  # R016.34: no source -> no unused import and the formatter's one-line empty tuple
        text = text.replace("SOURCES: tuple[Any, ...] = (\n)", "SOURCES: tuple[Any, ...] = ()")
        text = text.replace("from scion_sdk.ingest.live_declaration import source_meta\n", "")
    return text


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
    """Drop the cut files from the certification artifact digests; the file is rewritten in canonical format."""
    p = pkg / "ontology" / "certification.json"
    if not p.is_file():
        return
    data = json.loads(p.read_text(encoding="utf-8"))
    arts = data.get("artifacts", {})
    kept = {k: v for k, v in arts.items() if Path(k).name not in CUT_NAMES}
    if kept != arts:
        data["artifacts"] = kept
        p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        changed.append(str(p.relative_to(root)))


# ---------------------------------------------------------------- e. versions
def _vt(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


_SDK_NAMES = r"(?:agent-connector-sdk|scion-sdk)"
_SDK_SPEC = re.compile(
    rf"(?P<name>{_SDK_NAMES})(?P<extras>\[[^\]]*\])?(?P<operator>\s*>=\s*)(?P<version>\d+(?:\.\d+)*)"
)


def _sdk_distribution(root: Path, requested: str | None = None) -> str:
    """Select an SDK spelling, preserving the project spelling unless explicitly migrating."""
    if requested is not None:
        if not is_distribution(requested, SDK_ROLE):
            raise ValueError(f"unsupported SDK distribution: {requested}")
        return requirement_name(requested)
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get("project", {})
    except (OSError, tomllib.TOMLDecodeError):
        project = {}
    return project_distribution(project, SDK_ROLE)


def _raise_sdk_spec(match: re.Match[str], target: str | None) -> str:
    version = match.group("version")
    name = target or match.group("name")
    return f"{name}{match.group('extras') or ''}{match.group('operator')}" + (
        SDK_FLOOR if _vt(version) < _vt(SDK_FLOOR) else version
    )


def bump_sdk_floor(root: Path, changed: list[str], sdk_distribution: str | None = None) -> bool:
    """Raise SDK floors, preserving aliases unless an explicit migration target is supplied."""
    hit = False
    target = _sdk_distribution(root, sdk_distribution)
    for name in ("pyproject.toml", "requirements.txt"):
        p = root / name
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        new = _SDK_SPEC.sub(lambda m: _raise_sdk_spec(m, target if sdk_distribution else None), text)
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
            review.add("version", f"bump target {fname} skipped: it does not contain {search!r}", fname, blocking=False)
            continue
        target.write_text(target.read_text(encoding="utf-8").replace(search, replace), encoding="utf-8")
        changed.append(fname)
    text = cfg_path.read_text(encoding="utf-8")
    cfg_path.write_text(re.sub(r"(?m)^(current_version\s*=\s*).*$", rf"\g<1>{new}", text, count=1), encoding="utf-8")
    changed.append(".bumpversion.cfg")
    return new


def add_changelog(
    root: Path, version: str | None, changed: list[str], today: str | None = None, sdk_distribution: str | None = None
) -> None:
    """R016.28: a Keep-a-Changelog file gets one fixed entry for the bumped version (release tests pin it)."""
    path = root / "CHANGELOG.md"
    if version is None or not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    first = re.search(r"(?m)^## \[", text)
    if first is None or re.search(rf"(?m)^## \[{re.escape(version)}\]", text):
        return
    day = today or datetime.date.today().isoformat()
    sdk = _sdk_distribution(root, sdk_distribution)
    entry = (
        f"## [{version}] - {day}\n\n### Changed\n"
        f"- Requires `{sdk}>={SDK_FLOOR}`; data sources are declared in code (`connector_sources`).\n\n"
    )
    path.write_text(text[: first.start()] + entry + text[first.start() :], encoding="utf-8")
    changed.append("CHANGELOG.md")


def refresh_lock(root: Path, review: Review, changed: list[str], sdk_distribution: str | None = None) -> None:
    sdk = _sdk_distribution(root, sdk_distribution)
    r = subprocess.run(["uv", "lock", "--upgrade-package", sdk], cwd=root, capture_output=True, text=True)
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
_NAME_READ = re.compile(
    r"^( *)(?:manifest_path = [^\n]*\n\1if not manifest_path\.is_file\(\):\n\1 +manifest_path = [^\n]*\n\1)?"
    r'manifest = (?:\(\w+ / "connector_manifest\.yml"\)|manifest_path)\.read_text\([^)]*\)\n'
    r"\1match = re\.search\([^\n]*manifest[^\n]*\)\n"
    r"\1assert match is not None and match\.group\(1\) == (\w+)\n",
    re.M,
)
_FINGERPRINT_BLOCK = re.compile(
    r'^( *)fingerprints = [^\n]*tool_schema_fingerprints\.json"\n\1if fingerprints\.is_file\(\):\n(?:\1 +[^\n]*\n)+',
    re.M,
)
# R016.30: the declaration's mappings are models: ``schema_mappings[name]["fields"]`` reads as attributes
_MAPPING_SUBSCRIPT = re.compile(r'(declared_sources\(\)\.schema_mappings\[[^\]\n]+\])\["(ontology_class|fields)"\]')
_DELETE_NAME = re.compile(r"test_.*(manifest|fingerprint|preset)", re.I)


_PARENT_IMPORT = re.compile(
    r'^( *)imports = \{o for s, p, o in triples if p == OWL \+ "imports"\}\n'
    r'\1assert any\(i == PARENT_IRI or i\.startswith\(PARENT_IRI \+ "/"\) for i in imports\)\n',
    re.M,
)


_HUB_IMPORT_ASSERT = re.compile(r"^[ \t]*assert (?:HUB|PARENT|KG)_IRI in imports[ \t]*\n", re.M)


_PROMPT_KEY_ASSERT = re.compile(
    r"""(?m)^[ \t]*assert\s+(?:\w+\[["'](?:extends|compose)["']\]\s*(?:==|is\b).*|["'](?:extends|compose)["']\s+in\s+\w+\s*)\n"""
)


_ENTITY_ARGS = re.compile(
    r"""(?P<ind>[ \t]*)id=(?P<rec>\w+)\.get\("id"\),\n(?P=ind)node_type=(?P=rec)\.get\("node_type"\),\n"""
)
_ENTITY_COMMENT = re.compile(r"(?m)^[ \t]*# id/node_type are intentionally read with \.get\(\).*\n(?:[ \t]*#.*\n)*")
_REQUIRED_TEXT = """def _required_text(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        from scion_sdk.ingest import IngestError

        raise IngestError(f"every entity needs an id and a node_type, got {key}={value!r}")
    return value


"""


def validate_entity_args(text: str) -> str:
    """R016.36: SDK 0.4 ``Entity`` takes ``str`` ids; ``record.get("id")`` (``Any | None``) becomes a validated read (``IngestError``)."""
    m = _ENTITY_ARGS.search(text)
    if not m or "_required_text" in text or not re.search(r"(?m)^from typing import .*\bAny\b", text):
        return text
    rec, ind = m.group("rec"), m.group("ind")
    new_args = f'{ind}id=_required_text({rec}, "id"),\n{ind}node_type=_required_text({rec}, "node_type"),\n'
    out = _ENTITY_COMMENT.sub("", text[: m.start()] + new_args + text[m.end() :])
    at = out.rfind("\ndef ", 0, out.index("_required_text(")) + 1
    return out[:at] + _REQUIRED_TEXT + out[at:]


def drop_prompt_key_assertions(text: str) -> str:
    """R016.32: the prompt keeps no top-level ``extends``/``compose`` once stripped, so a test asserting them goes too."""
    return _PROMPT_KEY_ASSERT.sub("", text)


_PKG_FROM_DIRNAME = re.compile(
    r"""__import__\("pathlib"\)\s*\.Path\(__file__\)\s*\.resolve\(\)\s*\.parent\.parent\.name\.replace\(\s*["']-["'],\s*["']_["']\s*\)"""
)
_PKG_FROM_PYPROJECT = (
    '__import__("tomllib").loads(__import__("pathlib").Path(__file__).resolve().parent.parent'
    '.joinpath("pyproject.toml").read_text(encoding="utf-8"))["project"]["name"].replace("-", "_")'
)


def derive_package_from_pyproject(text: str) -> str:
    """R016.33: a startup test deriving the package from the checkout directory name breaks in a worktree dir; read pyproject."""
    return _PKG_FROM_DIRNAME.sub(lambda _m: _PKG_FROM_PYPROJECT, text)


def drop_parent_import_assertion(text: str) -> str:
    """Remove the assertion that a pack imports the EG ontology (R1 removes that import); R016.26 adds ``assert HUB_IRI in imports``."""
    return _HUB_IMPORT_ASSERT.sub("", _PARENT_IMPORT.sub("", text))


# R016.19: reference strings of the live layout (``connector:<name>#mappings/<T>`` and ``#relations/<C>/<R>``)
_REF_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r'"resources/(\w+)/relations/(\w+)"'), r'"relations/\1/\2"'),
    (re.compile(r'(endswith\(\s*f?")/?relations/(\{?\w+\}?)"'), r'\1/\2"'),
    (re.compile(r'(endswith\(\s*f?")schema_mappings/'), r"\1mappings/"),
    (re.compile(r'manifest:([^#"\s]+)#schema_mappings/'), r"connector:\1#mappings/"),
    (re.compile(r'manifest:([^#"\s]+)#resources/([^/"\s]+)/relations/'), r"connector:\1#relations/\2/"),
    (re.compile(r'rsplit\("/relations/", 1\)\[-1\]'), 'rsplit("/", 1)[-1]'),
)
_SDK_LITERAL = re.compile(rf"(?P<name>{_SDK_NAMES})(?P<extras>\[[^\]]*\])?(?P<operator>>=)(?P<version>\d+\.\d+\.\d+)")


_FLOOR_LITERAL = re.compile(r"(>=\s*)(\d+\.\d+\.\d+)")


def _raise_line_floor(line: str) -> str:
    """R016.26: a ``>=X.Y.Z`` literal on a line that names the SDK is raised to the floor when it is lower."""
    if "sdk" not in line.lower():
        return line
    return _FLOOR_LITERAL.sub(
        lambda m: m.group(1) + SDK_FLOOR if _vt(m.group(2)) < _vt(SDK_FLOOR) else m.group(0), line
    )


def rewrite_references(text: str, sdk_distribution: str | None = None) -> str:
    """Point reference-string assertions at the live layout and raise stale SDK floor literals."""
    for rx, repl in _REF_RULES:
        text = rx.sub(repl, text)
    text = "".join(_raise_line_floor(ln) for ln in text.splitlines(keepends=True))
    target = requirement_name(sdk_distribution) if sdk_distribution else None
    if target is not None and not is_distribution(target, SDK_ROLE):
        raise ValueError(f"unsupported SDK distribution: {sdk_distribution}")
    return _SDK_LITERAL.sub(
        lambda m: (
            f"{target or m.group('name')}{m.group('extras') or ''}{m.group('operator')}"
            + (SDK_FLOOR if _vt(m.group("version")) < _vt(SDK_FLOOR) else m.group("version"))
        ),
        text,
    )


# R016.20: a bare string-literal list item naming a cut file is an assertion about a cut file
_CUT_ITEM = re.compile(
    r'^[ \t]*[rf]?["\'](?:[\w./-]*/)?(?:' + "|".join(re.escape(n) for n in CUT_NAMES) + r')["\'],?[ \t]*\n',
    re.M,
)


def drop_cut_list_items(text: str) -> str:
    return _CUT_ITEM.sub("", text)


# R016.20: a test function that reads a cut file or the manifest resource is deleted whole
def delete_cut_tests(text: str, words: tuple[str, ...]) -> tuple[str, list[str], list[str]]:
    """(new text, deleted test names, spec ids they were bound to); the file is unchanged when nothing matches."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text, [], []
    lines = text.splitlines(keepends=True)
    cuts: list[tuple[int, int, str]] = []
    nodes = list(tree.body) + [m for c in tree.body if isinstance(c, ast.ClassDef) for m in c.body]
    for node in nodes:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test"):
            continue
        start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
        end = node.end_lineno or node.lineno
        if any(w in "".join(lines[start:end]) for w in words):
            cuts.append((start, end, node.name))
    if not cuts:
        return text, [], []
    specs = sorted(set(re.findall(r'spec\("([^"]+)"\)', "".join("".join(lines[a:b]) for a, b, _ in cuts))))
    for a, b, _ in sorted(cuts, reverse=True):
        del lines[a:b]
    out = re.sub(r"\n{4,}", "\n\n\n", "".join(lines))
    out = out.rstrip("\n") + "\n" if out.strip() else out  # R016.34: no blank lines at the end of file
    return out, [n for _, _, n in cuts], specs


def prune_unused_imports(path: Path) -> None:
    """Remove imports a deleted test left unused (ruff F401 would fail the commit hook); a missing ruff is skipped."""
    ruff = shutil.which("ruff")
    if ruff:
        subprocess.run([ruff, "check", "--select", "F401", "--fix", "--quiet", str(path)], capture_output=True)


def has_tests(text: str) -> bool:
    return bool(re.search(r"(?m)^\s*(?:async )?def test", text))


# R016.21: prose that names a cut file (docstrings, comments) points at the generated declaration instead
_MENTION = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in CUT_NAMES if n != "data_resources.json") + r")\b")


def _doc_comment_lines(text: str) -> set[int]:
    lines: set[int] = set()
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
                v = body[0].value
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                lines.add(tok.start[0])
    except (SyntaxError, tokenize.TokenError):
        return set()
    return lines


def rewrite_py_prose(text: str, pkg: str) -> str:
    """Docstring and comment mentions of cut files become the generated ``connector_sources`` module."""
    prose = _doc_comment_lines(text)
    out = []
    for i, ln in enumerate(text.splitlines(keepends=True), 1):
        out.append(_MENTION.sub(f"{pkg}.connector_sources", ln) if i in prose else ln)
    return "".join(out)


_FACTORY_DOC = '"""Connector package; the data sources are declared in ``{pkg}.connector_sources``."""\n'


def rewrite_connectors_init(text: str, pkg: str) -> str | None:
    """A connectors package whose __init__ is only a docstring (plus the future import) gets the fixed docstring."""
    try:
        body = ast.parse(text).body
    except SyntaxError:
        return None
    rest = [n for n in body[1:] if not (isinstance(n, ast.ImportFrom) and n.module == "__future__")]
    if not body or rest or not (isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)):
        return None
    return _FACTORY_DOC.format(pkg=pkg)


_MANIFEST_PATH_KW = re.compile(r'^[ \t]*manifest_path=[^\n]*connector_manifest\.yml"\)?,[ \t]*\n', re.M)


def drop_manifest_path_kw(text: str) -> str:
    """``ConnectorContent`` takes no manifest path in the live layout."""
    return _MANIFEST_PATH_KW.sub("", text)


_PROVIDER_TABLE = re.compile(
    r'(?:^#[^\n]*\n)*^\[project\.entry-points\."(?:scion_sdk|agent_utilities)\.source_connector_providers"\]\n(?:^(?!\[)[^\n]*\S[^\n]*\n)*\n?',
    re.M,
)
_COMMENT_BLOCK = re.compile(r"(?:^[ \t]*#[^\n]*\n)+", re.M)


def strip_pyproject_cut_refs(text: str) -> str:
    """Drop the source-provider entry point (the presets it served are cut) and comment blocks naming cut files."""
    text = _PROVIDER_TABLE.sub("", text)

    def block(m: re.Match[str]) -> str:
        return "" if any(w in m.group(0) for w in _CUT_WORDS) else m.group(0)

    return _COMMENT_BLOCK.sub(block, text)


_ALT = "|".join(re.escape(n) for n in CUT_NAMES)
_REGEX_ALT = re.compile(r"(?:[\w/]*(?:" + "|".join(re.escape(re.escape(n)) for n in CUT_NAMES) + r")\|)")


def strip_regex_alternatives(text: str) -> str:
    """Remove ``connector_manifest\\.yml|`` style alternatives from hook exclude patterns."""
    return _REGEX_ALT.sub("", text)


_CUT_SCRIPTS = ("generate_tool_schemas.py", "compute_tool_fingerprints.py")


def drop_script_hooks(text: str, scripts: list[str]) -> str:
    """Remove ``local`` pre-commit hook entries whose entry runs a deleted script."""
    if not scripts:
        return text
    parts = re.split(r"(?m)^(?=[ \t]*- (?:id|repo): )", text)
    kept = [p for p in parts if not any(s in p for s in scripts) or not p.lstrip().startswith("- id: ")]
    return "".join(kept)


def drop_bumpversion_hook(text: str) -> str:
    """R016.41: remove the repo-local ``check-bumpversion`` hook; ``pipelines-connector version`` owns the version."""
    parts = re.split(r"(?m)^(?=[ \t]*- (?:id|repo): )", text)
    kept = [p for p in parts if not re.match(r"\s*- id: check-bumpversion\b", p)]
    return "".join(kept)


_TTL_COMMENT = re.compile(r"^#.*$", re.M)


def rewrite_ttl_prose(text: str, pkg: str) -> str:
    return _TTL_COMMENT.sub(lambda m: _MENTION.sub(f"{pkg}.connector_sources", m.group(0)), text)


def rewrite_test(text: str, name: str, pkg: str) -> tuple[str | None, str]:
    """(new text, action) with action in keep/rewrite/delete/review; new text None for delete/review."""
    if not any(w in text for w in _CUT_WORDS):
        return text, "keep"
    if _DELETE_NAME.match(name) and "load_ingest_sources" not in text:
        return None, "delete"
    new = text
    if _NAME_READ.search(new):
        new = _NAME_READ.sub(lambda m: f'{m.group(1)}assert connector_name("{pkg}") == {m.group(2)}\n', new)
        new = _FINGERPRINT_BLOCK.sub("", new)
        new = re.sub(
            r"(?m)^((?:import|from) (?!__future__))",
            lambda m: "from scion_sdk.connector_identity import connector_name\n" + m.group(1),
            new,
            count=1,
        )
        for ident, line in (("re", r"import re\n"), ("json", r"import json\n")):
            body = re.sub(line, "", new, count=1)
            if not re.search(rf"\b{ident}\.", body):
                new = body
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
            "from scion_sdk.ingest.sources import load_ingest_sources",
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
    new = _MAPPING_SUBSCRIPT.sub(r"\1.\2", new)
    if any(w in new for w in _CUT_WORDS if w != "ingest_sources.json") or "ingest_sources.json" in new:
        return None, "review"
    return new, "rewrite"


def migrate_tests(
    root: Path, pkg: str, changed: list[str], deleted: list[str], review: Review, extra_words: tuple[str, ...] = ()
) -> None:
    words = (*_CUT_WORDS, *extra_words)
    for p in walk(root / "tests") if (root / "tests").is_dir() else []:
        if p.suffix != ".py":
            continue
        original = text = p.read_text(encoding="utf-8")
        rel = str(p.relative_to(root))
        text = derive_package_from_pyproject(drop_prompt_key_assertions(text))
        text = rewrite_references(drop_cut_list_items(drop_parent_import_assertion(text)))
        new, action = rewrite_test(text, p.name, pkg)
        if action == "review" or (action == "keep" and any(w in text for w in extra_words)):
            cut, names, specs = delete_cut_tests(text, words)
            if names:
                p.write_text(cut, encoding="utf-8")
                prune_unused_imports(p)
                cut = p.read_text(encoding="utf-8")
                p.write_text(original, encoding="utf-8")
            if any(e in cut for e in extra_words):
                # the module itself imports a deleted module: nothing in it can run
                specs = sorted(set(re.findall(r'spec\("([^"]+)"\)', text)))
                p.unlink()
                deleted.append(rel)
                review.add(
                    "tests",
                    f"deleted; imports a deleted module; was bound to {specs}: rebind or retire",
                    rel,
                    blocking=False,
                )
                continue
            if (
                names
                and not any(w in cut for w in words if w != "ingest_sources.json")
                and "ingest_sources.json" not in cut
            ):
                if has_tests(cut):
                    new, action = cut, "rewrite"
                    review.add(
                        "tests", f"deleted {names}; were bound to specs {specs}: rebind or retire", rel, blocking=False
                    )
                else:
                    p.unlink()
                    deleted.append(rel)
                    review.add(
                        "tests",
                        f"deleted; was bound to specs {specs}: rebind or retire those rows",
                        rel,
                        blocking=False,
                    )
                    continue
        if action == "delete":
            specs = sorted(set(re.findall(r'spec\("([^"]+)"\)', text)))
            p.unlink()
            deleted.append(rel)
            review.add(
                "tests", f"deleted; was bound to specs {specs}: rebind or retire those rows", rel, blocking=False
            )
        elif action in ("rewrite", "keep") and new is not None and new != original:
            p.write_text(new, encoding="utf-8")
            prune_unused_imports(p)
            changed.append(rel)
        elif action == "review":
            hits = [i + 1 for i, ln in enumerate(text.splitlines()) if any(w in ln for w in words)]
            review.add("tests", f"no fixed rule for lines {hits[:8]}", rel)


# ---------------------------------------------------------------- g. scripts, packaging and source prose
def drop_cut_scripts(root: Path, pkg: Path, deleted: list[str]) -> tuple[str, ...]:
    """Delete the scripts that generate cut files (and scripts that only drive them); returns names to retire elsewhere."""
    gone: list[str] = []
    scripts = root / "scripts"
    for name in _CUT_SCRIPTS:
        p = scripts / name
        if p.is_file() and any(w in p.read_text(encoding="utf-8") for w in _CUT_WORDS):
            gone.append(name)
            deleted.append(f"scripts/{name}")
            p.unlink()
    # R016.31: to a fixed point (a driver sorted before the script it drives is found on the next pass), and by module
    # stem too, because an import names `verify_generated_schemas`, not `verify_generated_schemas.py`.
    grew = True
    while grew:
        grew = False
        refs = [*gone, *(g.removesuffix(".py") for g in gone)]
        for p in sorted(scripts.glob("*.py")) if scripts.is_dir() else []:
            if any(g in p.read_text(encoding="utf-8") for g in refs):
                gone.append(p.name)
                deleted.append(f"scripts/{p.name}")
                p.unlink()
                grew = True
    adapters = pkg / "connectors" / "adapters.py"
    if adapters.is_file() and any(w in adapters.read_text(encoding="utf-8") for w in _CUT_WORDS):
        deleted.append(str(adapters.relative_to(root)))
        adapters.unlink()
        gone.append(f"{pkg.name}.connectors.adapters")
    return tuple([*gone, *(g.removesuffix(".py") for g in gone if g.endswith(".py"))])


def migrate_sources_text(root: Path, pkg: Path, scripts: tuple[str, ...], changed: list[str]) -> None:
    def edit(p: Path, fn: Any) -> None:
        text = p.read_text(encoding="utf-8")
        new = fn(text)
        if new is not None and new != text:
            p.write_text(new, encoding="utf-8")
            changed.append(str(p.relative_to(root)))

    edit(root / "pyproject.toml", strip_pyproject_cut_refs)
    pc = root / ".pre-commit-config.yaml"
    if pc.is_file():
        edit(
            pc,
            lambda t: drop_bumpversion_hook(
                drop_script_hooks(strip_regex_alternatives(t), [x for x in scripts if x.endswith(".py")])
            ),
        )
    init = pkg / "connectors" / "__init__.py"
    if init.is_file():
        edit(init, lambda t: rewrite_connectors_init(t, pkg.name) if any(w in t for w in _CUT_WORDS) else None)
    for p in walk(pkg):
        if p.suffix == ".py" and "tests" not in p.parts:
            edit(
                p,
                lambda t: (
                    rewrite_py_prose(drop_manifest_path_kw(t), pkg.name) if any(w in t for w in _CUT_WORDS) else None
                ),
            )
            edit(p, validate_entity_args)
        elif p.suffix == ".ttl":
            edit(p, lambda t: rewrite_ttl_prose(t, pkg.name))


def leftover_references(root: Path, review: Review) -> None:
    """Any file still naming a cut file after the codemod is a review item (hard cutover)."""
    skip = {"uv.lock", "CHANGELOG.md"}
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, env=env)
    names = (
        {n for n in tracked.stdout.split("\0") if n} if (root / ".git").exists() and tracked.returncode == 0 else None
    )
    for p in walk(root):
        if names is not None and str(p.relative_to(root)) not in names:
            continue
        parts = p.relative_to(root).parts
        # R016.26: ``validation/`` holds frozen, hash-pinned evidence records; they are history, not references
        if (
            p.suffix in {".pyc", ".png", ".svg", ".lock"}
            or p.name in skip
            or "specs" in parts
            or parts[0] == "validation"
        ):
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


# ---------------------------------------------------------------- docs
_NAME = r"(?:[\w./-]*/)?(?:" + "|".join(re.escape(n) for n in CUT_NAMES) + ")"
_DOC_LINE = [
    re.compile(rf"^\s*(?:[-*+]|\d+\.)?\s*[`\"']?{_NAME}[`\"']?\s*$"),
    re.compile(rf"^[\s│├└─|+`\-*]*{_NAME}\s*(?:#.*)?$"),
    re.compile(rf"^\s*\|\s*`?{_NAME}`?\s*\|.*\|\s*$"),
]


def strip_doc_mentions(text: str) -> str:
    """Remove lines and table rows that only name a cut file; any other mention stays for review."""
    kept = [ln for ln in text.splitlines(keepends=True) if not any(rx.match(ln.rstrip("\n")) for rx in _DOC_LINE)]
    return "".join(kept)


def migrate_docs(root: Path, changed: list[str]) -> None:
    for p in walk(root):
        rel = p.relative_to(root)
        if p.suffix not in {".md", ".rst"} or p.name == "CHANGELOG.md" or "specs" in rel.parts or p.is_symlink():
            continue
        text = p.read_text(encoding="utf-8")
        new = strip_doc_mentions(text)
        if new != text:
            p.write_text(new, encoding="utf-8")
            changed.append(str(rel))


# ---------------------------------------------------------------- driver
def rebump(root: Path, lock: bool = True, *, sdk_distribution: str | None = None) -> dict[str, Any]:
    """Already-migrated repo: raise the SDK floor, bump the patch version, refresh the lock. Nothing else."""
    root = Path(root)
    review = Review()
    changed: list[str] = []
    if bump_sdk_floor(root, changed, sdk_distribution):
        add_changelog(root, bump_patch(root, changed, review), changed, sdk_distribution=sdk_distribution)
        if lock and (root / "uv.lock").is_file():
            refresh_lock(root, review, changed, sdk_distribution)
        for p in walk(root / "tests") if (root / "tests").is_dir() else []:
            if p.suffix == ".py":
                text = p.read_text(encoding="utf-8")
                new = rewrite_references(text, sdk_distribution)
                if new != text:
                    p.write_text(new, encoding="utf-8")
                    changed.append(str(p.relative_to(root)))
    return {"changed": sorted(set(changed)), "deleted": [], "review": review.items}


def migrate(
    root: Path,
    eg_repo: Path | None = None,
    ref: str = "origin/main",
    lock: bool = True,
    served: set[str] | None = None,
    *,
    sdk_distribution: str | None = None,
) -> dict[str, Any]:
    """Run every transform on one connector checkout and return the report."""
    root = Path(root)
    review = Review()
    changed: list[str] = []
    deleted: list[str] = []
    pkg = package_dir(root)
    if pkg is None:
        review.add("discover", "no scion_sdk.connector entry point resolves to a package")
        return {"changed": [], "deleted": [], "review": review.items}
    inputs = _load_inputs(root, pkg, review)
    content = build_sources(inputs, review, served)
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
    dropped = drop_cut_scripts(root, pkg, deleted)
    migrate_sources_text(root, pkg, dropped, changed)
    strip_certification(root, pkg, changed, review)
    for p in sorted((pkg / "prompts").glob("*.json")) if (pkg / "prompts").is_dir() else []:
        text = p.read_text(encoding="utf-8")
        new = strip_prompt(text)
        if new is None:
            review.add("prompts", "extends/compose line not strippable by the fixed rule", str(p.relative_to(root)))
        elif new != text:
            p.write_text(new, encoding="utf-8")
            changed.append(str(p.relative_to(root)))
    if bump_sdk_floor(root, changed, sdk_distribution):
        add_changelog(root, bump_patch(root, changed, review), changed, sdk_distribution=sdk_distribution)
        if lock and (root / "uv.lock").is_file():
            refresh_lock(root, review, changed, sdk_distribution)
    migrate_tests(root, pkg.name, changed, deleted, review, dropped)
    migrate_docs(root, changed)
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
    ap.add_argument(
        "--sdk-distribution",
        choices=("agent-connector-sdk", "scion-sdk"),
        default=None,
        help="explicit SDK distribution migration target; omitted preserves the project's detected spelling",
    )
    ap.add_argument("--rebump", action="store_true", help="already-migrated repo: SDK floor, patch bump and lock only")
    ap.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    ap.add_argument("--served-tools", type=Path, default=None, help="JSON list of the tool names the server serves")
    ap.add_argument(
        "--central",
        action="store_true",
        help="the central pass: wave 1, auth, ingest and pipelines rules (PIPE-GATES-R016.50 to R016.100)",
    )
    ap.add_argument("--sdk-path", type=Path, default=None, help="--central dry run: SDK checkout installed from a path")
    ap.add_argument(
        "--pipelines-root", type=Path, default=None, help="--central: pipelines checkout (templates, defaults)"
    )
    args = ap.parse_args(argv)
    if args.central:
        from pipelines_hooks.hygiene.connector_central import migrate_central

        options = {
            "sdk_path": args.sdk_path,
            "pipelines_root": args.pipelines_root,
            "no_lock": args.no_lock,
            "sdk_distribution": args.sdk_distribution,
        }
        report = migrate_central(args.root, {k: v for k, v in options.items() if v})
        text = json.dumps(report, indent=1, sort_keys=True)
        if args.out:
            args.out.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 2 if any(i["blocking"] for i in report["review"]) else 0
    served = set(json.loads(args.served_tools.read_text())) if args.served_tools else None
    report = (
        rebump(args.root, not args.no_lock, sdk_distribution=args.sdk_distribution)
        if args.rebump
        else migrate(
            args.root, args.eg_repo, args.ref, not args.no_lock, served, sdk_distribution=args.sdk_distribution
        )
    )
    text = json.dumps(report, indent=1, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 2 if any(i["blocking"] for i in report["review"]) else 0


if __name__ == "__main__":
    sys.exit(main())
