"""Place every spec row on the deepest architecture node it belongs to.

Order of evidence: explicit ID rules (any part of the row's repository), title
keywords, cited code paths (longest prefix), the placement of the parent row,
requirement-text keywords, title keywords across the whole repository (a row
filed under a sibling family still names its part), then the parent row's part
wherever it sits. A row that only reaches its family home node goes to that
node's "Unmapped" child when the home node has children, so nothing is lost and
nothing is guessed. External nodes (people, outside clients) never take rows.
"""

from __future__ import annotations

import re
from collections import defaultdict

PATH_RE = re.compile(
    r"((?:crates|src|arbora|agent_connector_sdk|agent_utilities|agent_terminal_ui|tests|scripts|native|"
    r"epistemic_graph|contract|clients|docker|packaging|\.github)/[A-Za-z0-9_./\-]+)"
)


class Tree:
    """Index over the architecture model."""

    def __init__(self, root: dict) -> None:
        self.root = root
        self.nodes: dict[str, dict] = {}
        self.parent: dict[str, str | None] = {}
        self.order: list[str] = []
        self._walk(root, None, 0, None, "core")
        self.pre = {nid: i for i, nid in enumerate(self.order)}

    def _walk(self, node: dict, parent: str | None, depth: int, repo: str | None, layer: str) -> None:
        node.setdefault("children", [])
        node["repo"] = node.get("repo") or repo
        node["layer"] = node.get("layer") or layer
        node["level"] = depth
        self.nodes[node["id"]] = node
        self.parent[node["id"]] = parent
        self.order.append(node["id"])
        node["_kw"] = re.compile(node["kw"], re.I) if node.get("kw") else None
        node["_ids"] = [re.compile(i if "(" in i else re.escape(i) + r"$") for i in node.get("ids", [])]
        for child in node["children"]:
            self._walk(child, node["id"], depth + 1, node["repo"], node["layer"])

    def add_child(self, parent_id: str, child: dict) -> None:
        parent = self.nodes[parent_id]
        parent["children"].append(child)
        self._walk(child, parent_id, parent["level"] + 1, parent["repo"], parent["layer"])
        self.pre = {nid: i for i, nid in enumerate(self.order)}

    def subtree(self, nid: str) -> set[str]:
        out, stack = set(), [nid]
        while stack:
            cur = stack.pop()
            out.add(cur)
            stack.extend(c["id"] for c in self.nodes[cur]["children"])
        return out


def validate_code(tree: Tree, files: dict[str, set[str]]) -> list[tuple[str, str]]:
    """Drop code paths that do not exist on the scanned commit; return what was dropped."""
    dropped = []
    for node in tree.nodes.values():
        repo_files = files.get(node["repo"] or "", set())
        keep = []
        for path in node.get("code", []):
            prefix = path.rstrip("/") + "/"
            if path in repo_files or any(f.startswith(prefix) for f in repo_files):
                keep.append(path)
            else:
                dropped.append((node["id"], path))
        node["code"] = keep
    return dropped


def _group_key(kind: str, title: str) -> str | None:
    if kind == "cqconn":
        match = re.match(r"^([a-z0-9][a-z0-9\-]*) competency rollup", title)
        if match:
            return match.group(1)
        return "Vocabulary additions" if re.search(r"additions rollup|vocabulary", title, re.I) else None
    match = re.search(r"`([a-z0-9][a-z0-9\-]+)`", title)
    return match.group(1) if match else None


def add_dynamic_groups(tree: Tree, rows: list[dict]) -> None:
    """Create one child per connector rollup for families declared with ``dyn``."""
    by_id = {r["id"]: r for r in rows}
    for nid in list(tree.order):
        node = tree.nodes[nid]
        if not node.get("dyn"):
            continue
        groups: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            if row["repo"] == node["repo"] and row["family"] in node.get("fam", []):
                root_id = row["id"].split(".")[0]
                key = _group_key(node["dyn"], by_id.get(root_id, {}).get("title", ""))
                if key:
                    groups[key].add(root_id)
        for key in sorted(groups):
            slug = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")
            child = {
                "id": f"{nid}.{slug}",
                "label": key,
                "role": f"{len(groups[key])} rollup(s)",
                "desc": f"The {key} rows for this part. Acceptance tests prove each answer.",
                "ids": [re.escape(x) + r"(\.|$)" for x in sorted(groups[key])],
            }
            tree.add_child(nid, child)


class Placer:
    """Assign each row to one node."""

    def __init__(self, tree: Tree) -> None:
        self.tree = tree
        self.home: dict[tuple[str, str], str] = {}
        self.repo_nodes: dict[str, list[str]] = defaultdict(list)
        for nid in tree.order:
            node = tree.nodes[nid]
            if node.get("external"):
                continue
            for fam in node.get("fam", []):
                self.home[(node["repo"], fam)] = nid
            if node["repo"]:
                self.repo_nodes[node["repo"]].append(nid)
        self.external = {nid for nid in tree.order if tree.nodes[nid].get("external")}
        self.sub = {nid: tree.subtree(nid) - self.external for nid in tree.nodes}
        self.placed: dict[str, str] = {}
        self.how: dict[str, str] = {}

    def _best(self, cands) -> str | None:
        nodes = self.tree.nodes
        ranked = sorted(cands, key=lambda x: (-nodes[x]["level"], not nodes[x].get("glob"), self.tree.pre[x]))
        return ranked[0] if ranked else None

    def _home(self, row: dict) -> str | None:
        return self.home.get((row["repo"], row["family"])) or self.home.get((row["repo"], "*"))

    def _code_match(self, row: dict, home: str) -> str | None:
        nodes = self.tree.nodes
        paths = {p.rstrip(".,;:)`'").split("::")[0] for p in PATH_RE.findall(row["text"])}
        best = None
        for nid in self.repo_nodes[row["repo"]]:
            if nid not in self.sub[home] and nodes[nid]["level"] < nodes[home]["level"]:
                continue
            for code in nodes[nid].get("code", []):
                if any(t == code or t.startswith(code.rstrip("/") + "/") for t in paths):
                    key = (len(code), nodes[nid]["level"], -self.tree.pre[nid], nid)
                    best = max(best, key) if best else key
        return best[3] if best and best[3] != home else None

    def _parent_match(self, row: dict, allowed: set[str] | None) -> str | None:
        """The parent row's part: inside ``allowed``, or anywhere when the parent left its family
        by repository-wide evidence (``allowed`` None means any part of the repository)."""
        pid = row["id"].rsplit(".", 1)[0] if "." in row["id"] else None
        while pid and pid not in self.placed:
            pid = pid.rsplit(".", 1)[0] if "." in pid else None
        if not pid or self.how.get(pid) == "fallback":
            return None
        if allowed is None or self.placed[pid] in allowed or self.how[pid] in ("id", "repo"):
            return self.placed[pid]
        return None

    def _repo_title(self, row: dict, home: str) -> str | None:
        """Title keywords of any part of the same repository outside the home subtree.

        Only for a home with children: a row on a leaf home is already placed.
        The longest keyword match wins, then the deepest part.
        """
        nodes = self.tree.nodes
        if len(self.sub[home]) == 1:
            return None
        hits = []
        for x in self.repo_nodes[row["repo"]]:
            match = nodes[x]["_kw"].search(row["title"]) if nodes[x]["_kw"] and x not in self.sub[home] else None
            if match and x not in self.external:
                hits.append((-len(match.group(0)), -nodes[x]["level"], self.tree.pre[x], x))
        return min(hits)[3] if hits else None

    def place(self, row: dict) -> tuple[str | None, str]:
        nodes = self.tree.nodes
        home = self._home(row)
        if home is None:
            return None, "orphan"
        repo = set(self.repo_nodes[row["repo"]]) - self.external
        glob = {x for x in self.repo_nodes[row["repo"]] if nodes[x].get("glob") and x not in self.sub[home]}
        scope = [x for x in self.sub[home] if x != home]
        steps = (
            (
                "id",
                lambda: self._best([x for x in repo if any(p.match(row["id"]) for p in nodes[x]["_ids"])]),
            ),
            (
                "title",
                lambda: self._best(
                    [x for x in [*scope, *glob] if nodes[x]["_kw"] and nodes[x]["_kw"].search(row["title"])]
                ),
            ),
            ("code", lambda: self._code_match(row, home)),
            ("parent", lambda: self._parent_match(row, self.sub[home] | glob)),
            ("body", lambda: self._best([x for x in scope if nodes[x]["_kw"] and nodes[x]["_kw"].search(row["req"])])),
            ("repo", lambda: self._repo_title(row, home)),
            ("parent", lambda: self._parent_match(row, None) if len(self.sub[home]) > 1 else None),
        )
        for how, step in steps:
            found = step()
            if found:
                return self._descend(row, found), how
        return home, "fallback"

    def _descend(self, row: dict, nid: str) -> str:
        """Refine a placement on a part with children down to the deepest child the row names.

        Evidence inside the part's subtree, in order: title keywords, the parent row's part,
        requirement-text keywords. A part with children is a container, never a leftover bucket.
        """
        nodes = self.tree.nodes
        while nodes[nid]["children"]:
            inner = self.sub[nid] - {nid}
            pid = row["id"].rsplit(".", 1)[0] if "." in row["id"] else None
            while pid and pid not in self.placed:
                pid = pid.rsplit(".", 1)[0] if "." in pid else None
            found = (
                self._best([x for x in inner if nodes[x]["_kw"] and nodes[x]["_kw"].search(row["title"])])
                or (self.placed[pid] if pid and self.placed[pid] in inner else None)
                or self._best([x for x in inner if nodes[x]["_kw"] and nodes[x]["_kw"].search(row["req"])])
            )
            if not found:
                # Stuck on a container: the parent row's part, when it is a part of the same repository.
                if pid and self.placed[pid] in self.repo_nodes[row["repo"]] and self.placed[pid] != nid:
                    return self._descend({**row, "id": pid}, self.placed[pid])
                break
            nid = found
        return nid

    def run(self, rows: list[dict]) -> dict[str, list[dict]]:
        direct: dict[str, list[dict]] = defaultdict(list)
        orphans = []
        for row in sorted(rows, key=lambda r: r["id"].count(".")):
            nid, how = self.place(row)
            if nid is None:
                orphans.append(row)
                continue
            self.placed[row["id"]], self.how[row["id"]] = nid, how
            direct[nid].append(row)
        self._split_unmapped(direct)
        if orphans:
            unm = {
                "id": "root.unmapped",
                "label": "Unmapped",
                "role": "rows with no owner part",
                "layer": "unmapped",
                "unmapped": True,
                "desc": "These rows come from spec families that no part owns.",
            }
            self.tree.add_child("root", unm)
            direct[unm["id"]] = orphans
        return direct

    def _split_unmapped(self, direct: dict[str, list[dict]]) -> None:
        for nid in list(self.tree.order):
            node = self.tree.nodes[nid]
            loose = [r for r in direct.get(nid, []) if self.how[r["id"]] == "fallback"]
            if not node["children"] or not loose:
                continue
            unm = {
                "id": nid + ".unmapped",
                "label": "Unmapped",
                "role": "rows not placed in a child",
                "layer": "unmapped",
                "unmapped": True,
                "desc": "These rows belong to this part. No rule placed them on a child part. Review them to find their child.",
            }
            self.tree.add_child(nid, unm)
            direct[unm["id"]] = loose
            direct[nid] = [r for r in direct[nid] if self.how[r["id"]] != "fallback"]


def unmapped_violations(tree: Tree, direct: dict[str, list[dict]], allow: list[str]) -> list[str]:
    """Every row on an Unmapped part, or left directly on a part with children, that the reviewed
    allowlist (``repo:ID`` entries) does not name. Every row must sit on a leaf part at any depth.

    A row on an external part is always a violation: external parts take no rows.
    """
    allowed = set(allow)
    out = []
    for nid, rows in direct.items():
        node = tree.nodes[nid]
        for row in rows:
            key = f"{row['repo']}:{row['id']}"
            leftover = node.get("unmapped") or bool(node["children"])
            if node.get("external") or (leftover and key not in allowed):
                out.append(key)
    return sorted(out)
