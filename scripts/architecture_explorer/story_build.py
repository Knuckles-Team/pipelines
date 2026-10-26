"""Opt-in same-build source charts; strict capture precedes every public write."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.error
import urllib.request

from .activity_probe import NoRedirect
from .story_activity import timestamp
from .sources import Snapshot, family_docs, load_all, read_aliases, rows_for
from .story_chart_sources import source_chart
from .story_contract import ContractError, require

API = "https://api.github.com/repos/Knuckles-Team/"
SHA = r"[0-9a-f]{40}"
DOC = re.compile(r"specs/[^/]+/(?:[^/]+\.md|status\.json)$")


def read_family_config(path):
    """Explicit opt-in cannot turn into a legacy build through null/duplicates."""

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate source config key")
            result[key] = value
        return result

    families = json.loads(path.read_text(), object_pairs_hook=unique)
    require(isinstance(families, dict) and bool(families), "nonempty source family configuration required")
    return families


def source_transport(token: str, *, max_requests: int = 512):
    """Existing token only; bounded GETs, no redirects/retry/anonymous fallback."""
    require(bool(token), "source capture requires existing GITHUB_TOKEN")
    require(type(max_requests) is int and 1 <= max_requests <= 512, "invalid source request budget")
    opener = urllib.request.build_opener(NoRedirect())
    calls = 0

    def request(url):
        nonlocal calls
        require(
            bool(
                re.fullmatch(
                    re.escape(API)
                    + r"[A-Za-z0-9_.-]+(?:/git/(?:commits|blobs)/"
                    + SHA
                    + r"|/git/trees/"
                    + SHA
                    + r"\?recursive=1)?",
                    url,
                )
            ),
            "unexpected source endpoint",
        )
        require(calls < max_requests, "source request budget exhausted")
        calls += 1
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "User-Agent": "architecture-source-capture",
            },
        )
        try:
            with opener.open(req, timeout=30) as response:
                raw = response.read(4_000_001)
                require(len(raw) <= 4_000_000, "source response exceeds limit")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            category = "access denied" if exc.code in {401, 403, 404} else "HTTP failure"
            raise ContractError(category + "; source capture stopped without retry/fallback") from None
        except (OSError, ValueError):
            raise ContractError("source response/transport failure; stopped") from None

    return request


class CapturedReader:
    def __init__(self, capture):
        self.capture = capture

    def read(self, path):
        require(path in self.capture["documents"], "uncaptured source document: " + path)
        return self.capture["documents"][path]


def capture_repository(entry, request):
    """Capture raw documents and details at the existing scan's exact commit."""
    slug, commit = entry.get("slug", ""), entry.get("sha", "")
    require(
        bool(re.fullmatch(r"[A-Za-z0-9_.-]+", slug)) and bool(re.fullmatch(SHA, commit)), "full scan identity required"
    )
    base = API + slug
    metadata = request(base)
    require(
        metadata.get("full_name") == "Knuckles-Team/" + slug
        and isinstance(metadata.get("node_id"), str)
        and bool(metadata["node_id"].strip()),
        "canonical repository identity mismatch",
    )
    repo = {
        "id": metadata["node_id"],
        "fullName": metadata["full_name"],
        "url": "https://github.com/" + metadata["full_name"],
    }
    commit_doc = request(base + "/git/commits/" + commit)
    require(commit_doc.get("sha") == commit, "capture commit mismatch")
    tree_sha = commit_doc["tree"]["sha"]
    require(bool(re.fullmatch(SHA, tree_sha)), "invalid source tree identity")
    tree = request(base + "/git/trees/" + tree_sha + "?recursive=1")
    require(
        tree.get("sha") == tree_sha and tree.get("truncated") is False and isinstance(tree.get("tree"), list),
        "incomplete source tree",
    )
    paths, documents, blob_cache = [], {}, {}
    for item in tree["tree"]:
        if item["type"] != "blob":
            continue
        path = item["path"]
        require(
            isinstance(path, str) and path and not path.startswith("/") and ".." not in path.split("/"),
            "unsafe source path",
        )
        require(path not in paths, "duplicate source path")
        paths.append(path)
        if not (DOC.fullmatch(path) or path == ".config/spec-aliases.toml"):
            continue
        require(item["mode"] in {"100644", "100755"}, "source document must be a regular file")
        oid = item["sha"]
        require(bool(re.fullmatch(SHA, oid)), "invalid source blob identity")
        if oid not in blob_cache:
            blob = request(base + "/git/blobs/" + oid)
            require(
                blob.get("sha") == oid and blob.get("encoding") == "base64", "source blob identity/encoding mismatch"
            )
            raw = base64.b64decode("".join(blob["content"].split()), validate=True)
            require(type(blob["size"]) is int and len(raw) == blob["size"], "source blob size mismatch")
            digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            require(digest == oid, "source blob bytes do not match frozen tree")
            blob_cache[oid] = raw.decode("utf-8")
        documents[path] = blob_cache[oid]
    capture = {
        "repositoryId": repo["id"],
        "head": commit,
        "tree": {"truncated": False, "paths": paths},
        "documents": documents,
    }
    reader, files = CapturedReader(capture), set(paths)
    snap = Snapshot(repo=entry["name"], slug=slug, head=commit[:10], files=files)
    snap.rows = rows_for(reader, entry["name"], files)
    snap.docs = {family: family_docs(reader, files, family) for family in {row["family"] for row in snap.rows}}
    snap.aliases = read_aliases(reader, files)
    return snap, capture, repo


def load_build_sources(scanned, mode, workspace, families, *, token, request=None):
    """Load strict selected sources first; ordinary fleet snapshots retain their path.

    families maps exact scanned logical repository names to selected families.
    Empty lists mean capture for prerequisite closure, not selected family rows.
    """
    require(mode == "github", "same-build source capture currently requires frozen github scan")
    require(isinstance(families, dict) and 1 <= len(families) <= 8, "bounded source family config required")
    entries = {entry["name"]: entry for entry in scanned}
    require(
        len(entries) == len(scanned) and set(families) <= entries.keys(), "source configuration outside frozen scan"
    )
    require(
        all(
            isinstance(v, list)
            and len(v) == len(set(v))
            and all(isinstance(f, str) and re.fullmatch(r"[A-Za-z0-9_-]+", f) for f in v)
            for v in families.values()
        ),
        "invalid source family selection",
    )
    require(any(families.values()), "empty selected source families")
    request = request or source_transport(token)
    strict, captures, repos, selection = {}, [], [], []
    for name, wanted in families.items():
        snap, capture, repo = capture_repository(entries[name], request)
        strict[name] = snap
        captures.append(capture)
        repos.append(repo)
        selection.extend(repo["id"] + ":" + family for family in wanted)
    chart = source_chart(
        captures=captures, repositories=repos, selection=selection, score_scope="selected-family-prerequisite-closure"
    )
    # Legacy public rows and strict chart must describe exactly the same capture.
    baseline = {(snap.repo, row["id"]): row for snap in strict.values() for row in snap.rows}
    names = {repo["id"]: name for name, repo in zip(families, repos, strict=True)}
    for row in [*chart["rows"].values(), *chart["evidenceRows"].values()]:
        legacy = baseline.get((names[row["repositoryId"]], row["id"]))
        require(
            legacy is not None and all(legacy[k] == row[k] for k in ("status", "family", "title")),
            "same-build public/source row parity failure: " + row["id"],
        )
    others = load_all([entry for entry in scanned if entry["name"] not in strict], mode, workspace)
    all_snaps = {**{snap.repo: snap for snap in others}, **strict}
    require(set(all_snaps) == set(entries), "incomplete same-build snapshot scope")
    return [all_snaps[entry["name"]] for entry in scanned], chart


def canonical_chart_bytes(chart):
    """Python receipt encoding: ASCII keys, UTF-8 values, sorted and compact."""

    def check(value):
        if isinstance(value, dict):
            require(all(isinstance(key, str) and key.isascii() for key in value), "non-ASCII chart key")
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(chart)
    return json.dumps(chart, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def seal_chart(chart, *, built_at, snapshots):
    """Attach a content digest and exact capture/public-head receipt, not freshness by guess."""
    require("buildReceipt" not in chart, "source chart is already sealed")
    timestamp(built_at)
    heads = {snap.repo: snap.head for snap in snapshots}
    by_slug = {snap.slug: snap for snap in snapshots}
    require(len(heads) == len(by_slug) == len(snapshots), "duplicate public snapshot identity")
    for source in chart["scope"]["repositories"]:
        snap = by_slug.get(source["fullName"].split("/")[1])
        require(
            snap is not None and not snap.error and snap.head == source["commit"][:10],
            "public/source commit receipt mismatch",
        )
    body = canonical_chart_bytes(chart)
    chart["buildReceipt"] = {
        "builtAt": built_at,
        "canonicalEncoding": "utf8-sorted-compact-ascii-keys/1",
        "sourceChartSha256": hashlib.sha256(body).hexdigest(),
        "publicHeads": heads,
        "sameCaptureParity": True,
        "sourceScope": chart["scope"]["repositories"],
    }
    return chart


def verify_chart_receipt(chart, *, built_at, public_heads, public_slugs):
    """Python-side build verification before passing a chart to a JS consumer.

    This is integrity and same-build coupling, not an independently signed proof.
    """
    receipt = chart.get("buildReceipt")
    require(isinstance(receipt, dict), "missing same-build source receipt")
    require(
        receipt.get("canonicalEncoding") == "utf8-sorted-compact-ascii-keys/1", "unsupported source receipt encoding"
    )
    require(
        receipt.get("builtAt") == built_at
        and receipt.get("publicHeads") == public_heads
        and receipt.get("sameCaptureParity") is True,
        "source receipt/public build mismatch",
    )
    timestamp(built_at)
    require(receipt.get("sourceScope") == chart["scope"]["repositories"], "source receipt scope mismatch")
    require(
        set(public_slugs) == set(public_heads) and len(set(public_slugs.values())) == len(public_slugs),
        "ambiguous public source identities",
    )
    logical = {slug: name for name, slug in public_slugs.items()}
    for source in receipt["sourceScope"]:
        name = logical.get(source["fullName"].split("/")[1])
        require(name is not None and public_heads[name] == source["commit"][:10], "source receipt commit mismatch")
    body = canonical_chart_bytes({key: value for key, value in chart.items() if key != "buildReceipt"})
    require(receipt.get("sourceChartSha256") == hashlib.sha256(body).hexdigest(), "source chart digest mismatch")
    return chart
