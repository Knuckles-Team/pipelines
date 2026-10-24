"use strict";
// Capability search over the compact index that build.py embeds (search_index in build.py).
// Dependency free and pure: the page inlines this file, and the tests load it with node.
//
// index = { v, repos[], fams[], st[], nodes[[id,label,description,repoIdx,code[]]],
//           rows[[id,title,nodeIdx,repoIdx,familyIdx,statusIdx]], aliases{old: canonical} }
const ArchSearch = (function () {
  const LIMIT = 40;
  const words = s => String(s).toLowerCase().match(/[a-z0-9]+/g) || [];
  const idLike = /^[a-z][a-z0-9]*(?:-[a-z0-9.]+)+$/;

  // "#q=GraphQL%20client", "#node=conn.x", "#node=a&q=b" and the older "#<node>" anchor.
  function parseHash(hash) {
    const out = { node: "", q: "" };
    let h = String(hash || "").replace(/^#/, "");
    if (!h) return out;
    if (h.indexOf("=") < 0) {
      try { out.node = decodeURIComponent(h); } catch (_) { out.node = h; }
      return out;
    }
    h.split("&").forEach(part => {
      const i = part.indexOf("=");
      if (i < 0) return;
      const key = part.slice(0, i);
      let val = part.slice(i + 1).replace(/\+/g, " ");
      try { val = decodeURIComponent(val); } catch (_) { /* keep raw */ }
      if (key === "q") out.q = val; else if (key === "node") out.node = val;
    });
    return out;
  }

  function hashFor(node, q) {
    const parts = [];
    if (node && node !== "root") parts.push("node=" + encodeURIComponent(node));
    if (q) parts.push("q=" + encodeURIComponent(q));
    return parts.length ? "#" + parts.join("&") : "";
  }

  // `descOf(id)` optionally supplies each row's short description (the page already holds it, so the index does not repeat it).
  function create(index, descOf) {
    const aliases = {};
    Object.keys(index.aliases || {}).forEach(k => { aliases[k.toLowerCase()] = String(index.aliases[k]).toLowerCase(); });
    const titleCount = {};
    index.rows.forEach(r => { titleCount[r[1].toLowerCase()] = (titleCount[r[1].toLowerCase()] || 0) + 1; });
    const aliasPrefixes = Object.keys(aliases).filter(k => k.endsWith("-")).sort((a, b) => b.length - a.length);
    const nodes = index.nodes.map((n, i) => ({
      i, id: n[0], label: n[1], desc: n[2], repo: index.repos[n[3]] || "", code: n[4] || [],
      ll: n[1].toLowerCase(), lw: words(n[1]), ld: n[2].toLowerCase(), lc: (n[4] || []).join(" ").toLowerCase(),
    }));
    const rows = index.rows.map(r => ({
      id: r[0], title: r[1], node: nodes[r[2]].id, ni: r[2], repo: index.repos[r[3]], family: index.fams[r[4]],
      status: index.st[r[5]], ld: String((descOf && descOf(r[0])) || "").toLowerCase(), lid: r[0].toLowerCase(), lt: r[1].toLowerCase(), tw: words(r[1]),
    }));

    // A retired prefix or row ID resolves to its canonical form, so old names still land on the row.
    function resolve(q) {
      const s = q.trim().toLowerCase();
      if (aliases[s]) return aliases[s];
      for (const p of aliasPrefixes) if (s.startsWith(p)) return aliases[p] + s.slice(p.length);
      return s;
    }
    const rowHit = r => ({ kind: "row", id: r.id, title: r.title, node: r.node, repo: r.repo, family: r.family, status: r.status });
    const partHit = n => ({ kind: "part", id: n.id, title: n.label, node: n.id, repo: n.repo, family: "", status: "" });

    function search(query, limit) {
      const max = limit || LIMIT;
      const q = resolve(String(query || ""));
      if (q.length < 2) return [];
      if (idLike.test(q)) {
        const exact = rows.filter(r => r.lid === q);
        if (exact.length) return exact.concat(rows.filter(r => r.lid.startsWith(q + "."))).slice(0, max).map(rowHit);
        const pre = rows.filter(r => r.lid.startsWith(q)).sort((a, b) => a.lid.length - b.lid.length || (a.lid < b.lid ? -1 : 1));
        if (pre.length) return pre.slice(0, max).map(rowHit);
      }
      const toks = words(q);
      if (!toks.length) return [];
      const phrase = toks.join(" ");
      const scored = [];
      for (const r of rows) {
        const n = nodes[r.ni];
        let s = 0, ok = true;
        for (const t of toks) {
          let best = 0;
          for (const w of r.tw) { if (w === t) { best = 10; break; } if (best < 7 && w.startsWith(t)) best = 7; }
          if (best < 4 && r.lt.includes(t)) best = 4;
          if (best < 3 && (r.lid.includes(t) || r.family.toLowerCase().includes(t) || n.ld.includes(t))) best = 3;
          if (best < 2 && (n.ll.includes(t) || r.repo.toLowerCase().includes(t))) best = 2;
          if (!best && r.ld.includes(t)) best = 1; // a description-only match ranks below every title, ID, family and part match
          if (!best) { ok = false; break; }
          s += best;
        }
        if (!ok) continue;
        if (toks.length > 1 && r.lt.includes(phrase)) s += 15;
        if (titleCount[r.lt] > 1) s -= 2; // a title repeated across rows is boilerplate; the unique row is the owner
        scored.push([s, r.title.length, r.lid, rowHit(r)]);
      }
      for (const n of nodes) {
        let s = 0, ok = true;
        for (const t of toks) {
          let best = 0;
          for (const w of n.lw) { if (w === t) { best = 9; break; } if (best < 6 && w.startsWith(t)) best = 6; }
          if (best < 4 && n.ll.includes(t)) best = 4;
          if (best < 3 && (n.ld.includes(t) || n.lc.includes(t))) best = 3;
          if (!best) { ok = false; break; }
          s += best;
        }
        if (ok) scored.push([s, n.label.length, n.id, partHit(n)]);
      }
      scored.sort((a, b) => b[0] - a[0] || a[1] - b[1] || (a[2] < b[2] ? -1 : a[2] > b[2] ? 1 : 0));
      return scored.slice(0, max).map(x => x[3]);
    }
    return { search, resolve, size: { rows: rows.length, nodes: nodes.length } };
  }

  return { create, parseHash, hashFor };
})();
if (typeof module !== "undefined" && module.exports) module.exports = ArchSearch;
