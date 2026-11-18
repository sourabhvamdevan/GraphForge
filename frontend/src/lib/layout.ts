import dagre from 'dagre';

export const NODE_HEIGHT = 44;

export function nodeWidth(label: string): number {
  return Math.max(100, Math.min(260, 52 + label.length * 7.6));
}

export type XY = { x: number; y: number };

/** Left-to-right dagre layout; returns top-left positions keyed by node id. */
export function layoutGraph(
  nodes: { id: string; label: string }[],
  edges: { source: string; target: string }[],
): Record<string, XY> {
  const g = new dagre.graphlib.Graph({ multigraph: true });
  g.setGraph({ rankdir: 'LR', nodesep: 28, ranksep: 140, marginx: 20, marginy: 20 });
  g.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((n) => g.setNode(n.id, { width: nodeWidth(n.label), height: NODE_HEIGHT }));
  edges.forEach((e, i) => {
    if (g.hasNode(e.source) && g.hasNode(e.target)) g.setEdge(e.source, e.target, {}, `e${i}`);
  });
  dagre.layout(g);
  const out: Record<string, XY> = {};
  nodes.forEach((n) => {
    const p = g.node(n.id);
    out[n.id] = { x: p.x - nodeWidth(n.label) / 2, y: p.y - NODE_HEIGHT / 2 };
  });
  return out;
}
