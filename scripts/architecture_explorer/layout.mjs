// Precompute every level of the architecture explorer with the layered layout
// engine (orthogonal routing, crossing minimisation, merged parallel edges).
// Reads the level list as JSON on stdin and writes the layouts as JSON on stdout.
import ELK from "elkjs/lib/elk.bundled.js";

const elk = new ELK();
const LEAF = { w: 300, h: 112 };
const UNMAPPED = { w: 250, h: 96 };

const layered = (banded) => ({
  "elk.algorithm": "layered",
  "elk.direction": "DOWN",
  "elk.edgeRouting": "ORTHOGONAL",
  "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
  "elk.layered.thoroughness": "40",
  "elk.layered.mergeEdges": "true",
  "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
  "elk.layered.spacing.nodeNodeBetweenLayers": "80",
  "elk.spacing.nodeNode": "34",
  "elk.spacing.edgeNode": "22",
  "elk.spacing.edgeEdge": "14",
  "elk.spacing.edgeLabel": "4",
  "elk.edgeLabels.placement": "CENTER",
  "elk.layered.edgeLabels.sideSelection": "SMART_DOWN",
  "elk.aspectRatio": "2.0",
  "elk.partitioning.activate": banded ? "true" : "false",
  "elk.padding": "[top=28,left=18,bottom=16,right=18]",
});
const packed = {
  "elk.algorithm": "rectpacking",
  "elk.aspectRatio": "2.0",
  "elk.spacing.nodeNode": "24",
  "elk.padding": "[top=28,left=16,bottom=16,right=16]",
};

function sizeOf(level, done) {
  if (level.size) return level.size;
  if (level.unmapped) return UNMAPPED;
  const sub = done[level.id];
  if (!sub) return LEAF;
  const aspect = sub.w / sub.h;
  const w = 350;
  return { w, h: Math.round(Math.min(230, Math.max(124, w / aspect))) };
}

function childBox(c, byId, done) {
  const base = sizeOf(byId[c.id] || c, done);
  const k = c.scale || 1;
  return { w: Math.round(base.w * k), h: Math.round(base.h * k) };
}

function elkEdges(level) {
  return level.edges.map((e, i) => ({
    id: `${level.id}#${i}`,
    sources: [e.from],
    targets: [e.to],
    labels: e.label ? [{ text: e.label, width: e.label.length * 6.4 + 10, height: 16 }] : [],
  }));
}

function bandedGraph(level, byId, done) {
  const maxBand = Math.max(0, ...level.children.map((c) => c.band ?? 0));
  const rows = {};
  for (const c of level.children) (rows[c.band ?? maxBand] ||= []).push(c);
  const keys = Object.keys(rows).map(Number).sort((a, b) => a - b);
  return {
    id: level.id,
    layoutOptions: {
      ...layered(true),
      "elk.hierarchyHandling": "INCLUDE_CHILDREN",
      "elk.json.shapeCoords": "ROOT",
      "elk.json.edgeCoords": "ROOT",
    },
    children: keys.map((b) => ({
      id: `${level.id}::band${b}`,
      layoutOptions: {
        "elk.partitioning.partition": String(b),
        "elk.direction": "RIGHT",
        "elk.padding": "[top=30,left=16,bottom=14,right=16]",
        "elk.spacing.nodeNode": "60",
        "elk.layered.spacing.nodeNodeBetweenLayers": "90",
      },
      children: rows[b].map((c) => {
        const s = childBox(c, byId, done);
        return { id: c.id, width: s.w, height: s.h };
      }),
      band: b,
    })),
    edges: elkEdges(level),
  };
}

function flatGraph(level, byId, done) {
  return {
    id: level.id,
    layoutOptions: {
      ...(level.edges.length ? layered(false) : packed),
      ...(level.direction ? { "elk.direction": level.direction } : {}),
      ...(level.aspect ? { "elk.aspectRatio": String(level.aspect) } : {}),
    },
    children: level.children.map((c) => {
      const s = childBox(c, byId, done);
      return { id: c.id, width: s.w, height: s.h };
    }),
    edges: elkEdges(level),
  };
}

function collect(node, kids, bandRects) {
  for (const c of node.children || []) {
    if (c.id.includes("::band")) {
      bandRects.push([Number(c.id.split("::band")[1]), c.x, c.y, c.width, c.height]);
      collect(c, kids, bandRects);
    } else {
      kids[c.id] = [c.x, c.y, c.width, c.height];
    }
  }
}

function edgeList(out, level) {
  const all = [];
  const walk = (n) => {
    for (const e of n.edges || []) all.push(e);
    for (const c of n.children || []) walk(c);
  };
  walk(out);
  const byId = Object.fromEntries(all.map((e) => [e.id, e]));
  return level.edges.map((src, i) => {
    const e = byId[`${level.id}#${i}`] || {};
    const pts = [];
    for (const s of e.sections || []) {
      pts.push([s.startPoint.x, s.startPoint.y]);
      for (const b of s.bendPoints || []) pts.push([b.x, b.y]);
      pts.push([s.endPoint.x, s.endPoint.y]);
    }
    const lab = (e.labels || [])[0];
    return { from: src.from, to: src.to, label: src.label || "", pts, lp: lab ? [lab.x + lab.width / 2, lab.y + lab.height / 2] : null };
  });
}

async function layoutLevel(level, done, byId) {
  const banded = level.children.some((c) => c.band !== undefined && c.band !== null);
  const graph = banded ? bandedGraph(level, byId, done) : flatGraph(level, byId, done);
  const out = await elk.layout(graph);
  const kids = {};
  const bandRects = [];
  collect(out, kids, bandRects);
  bandRects.sort((a, b) => a[2] - b[2]);
  const bands = bandRects.map(([b, , y, , h]) => [level.bands?.[b] ?? `Band ${b}`, y, y + h]);
  return { w: out.width, h: out.height, kids, edges: edgeList(out, level), bands };
}

const input = JSON.parse(await new Promise((resolve) => {
  let data = "";
  process.stdin.on("data", (c) => (data += c));
  process.stdin.on("end", () => resolve(data));
}));
const byId = Object.fromEntries(input.levels.map((l) => [l.id, l]));
const done = {};
// levels arrive deepest first, so a parent sizes each child box from the child's own layout
for (const level of input.levels) done[level.id] = await layoutLevel(level, done, byId);
process.stdout.write(JSON.stringify(done));
