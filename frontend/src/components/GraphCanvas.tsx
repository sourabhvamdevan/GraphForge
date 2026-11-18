import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, ReactFlowProvider,
  useEdgesState, useNodesState, useReactFlow,
  type Edge, type Node, type NodeProps,
} from '@xyflow/react';
import type { EntityType, Filters, GraphData, Selection } from '../types';
import { NODE_HEIGHT, layoutGraph, nodeWidth, type XY } from '../lib/layout';
import { TYPE_COLORS, relLabel } from '../lib/style';

export const MAX_VISIBLE_NODES = 150;

type EntityNodeData = {
  label: string;
  entityType: EntityType;
  dimmed: boolean;
  highlighted: boolean;
};
type EntityNodeT = Node<EntityNodeData, 'entity'>;

const EntityNode = memo(function EntityNode({ data, selected }: NodeProps<EntityNodeT>) {
  const c = TYPE_COLORS[data.entityType];
  return (
    <div
      className="flex items-center gap-2 rounded-full border bg-white px-3 shadow-sm transition-opacity"
      style={{
        height: NODE_HEIGHT,
        width: nodeWidth(data.label),
        borderColor: selected || data.highlighted ? c.fill : '#e2e8f0',
        boxShadow: selected ? `0 0 0 3px ${c.soft}, 0 1px 2px rgb(0 0 0 / 0.08)` : undefined,
        opacity: data.dimmed ? 0.18 : 1,
        borderWidth: data.highlighted ? 2 : 1,
      }}
      title={`${data.label} (${data.entityType})`}
    >
      <Handle type="target" position={Position.Left} className="!h-1 !w-1 !border-0 !bg-transparent" />
      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: c.fill }} />
      <span className="truncate text-[13px] font-medium text-slate-800">{data.label}</span>
      <Handle type="source" position={Position.Right} className="!h-1 !w-1 !border-0 !bg-transparent" />
    </div>
  );
});

const nodeTypes = { entity: EntityNode };

interface Props {
  graph: GraphData;
  filters: Filters;
  selection: Selection;
  highlight: { nodes: Set<string>; edges: Set<string> } | null;
  focus: { id: string; nonce: number } | null;
  onSelect: (s: Selection) => void;
  onClearHighlight: () => void;
}

function useVisibleGraph(graph: GraphData, filters: Filters, forcedNodes: Set<string>, forcedEdges: Set<string>) {
  return useMemo(() => {
    const degree = new Map<string, number>();
    for (const r of graph.relationships) {
      degree.set(r.source_id, (degree.get(r.source_id) ?? 0) + 1);
      degree.set(r.target_id, (degree.get(r.target_id) ?? 0) + 1);
    }
    const typeOk = graph.entities.filter((e) => filters.types.has(e.type) || forcedNodes.has(e.id));
    const ranked = [...typeOk].sort(
      (a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) || b.mention_count - a.mention_count,
    );
    const truncated = ranked.length > MAX_VISIBLE_NODES;
    const keep = new Set(ranked.slice(0, MAX_VISIBLE_NODES).map((e) => e.id));
    forcedNodes.forEach((id) => keep.add(id));
    const entities = graph.entities.filter((e) => keep.has(e.id));
    const relationships = graph.relationships.filter(
      (r) =>
        keep.has(r.source_id) &&
        keep.has(r.target_id) &&
        (forcedEdges.has(r.id) || (filters.relations.has(r.relation) && r.confidence >= filters.minConfidence)),
    );
    return { entities, relationships, truncated, total: typeOk.length };
  }, [graph, filters, forcedNodes, forcedEdges]);
}

function Canvas({ graph, filters, selection, highlight, focus, onSelect, onClearHighlight }: Props) {
  const rf = useReactFlow();
  const forcedNodes = useMemo(() => {
    const s = new Set(highlight?.nodes ?? []);
    if (focus) s.add(focus.id);
    return s;
  }, [highlight, focus]);
  const forcedEdges = useMemo(() => new Set(highlight?.edges ?? []), [highlight]);
  const visible = useVisibleGraph(graph, filters, forcedNodes, forcedEdges);

  const [positions, setPositions] = useState<Record<string, XY>>({});
  const [layoutNonce, setLayoutNonce] = useState(0);
  const layoutKey = useMemo(
    () => visible.entities.map((e) => e.id).join('|') + '#' + visible.relationships.map((r) => r.id).join('|'),
    [visible],
  );
  const lastGraphId = useRef<string | null>(null);

  useEffect(() => {
    const pos = layoutGraph(
      visible.entities.map((e) => ({ id: e.id, label: e.canonical_name })),
      visible.relationships.map((r) => ({ source: r.source_id, target: r.target_id })),
    );
    setPositions(pos);
    const graphChanged = lastGraphId.current !== graph.graph_id;
    lastGraphId.current = graph.graph_id;
    if (graphChanged || layoutNonce > 0) {
      window.setTimeout(() => rf.fitView({ padding: 0.15, duration: 400 }), 30);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutKey, layoutNonce, graph.graph_id]);

  const derivedNodes: EntityNodeT[] = useMemo(
    () =>
      visible.entities.map((e) => ({
        id: e.id,
        type: 'entity' as const,
        position: positions[e.id] ?? { x: 0, y: 0 },
        selected: selection?.kind === 'node' && selection.id === e.id,
        data: {
          label: e.canonical_name,
          entityType: e.type,
          dimmed: !!highlight && !highlight.nodes.has(e.id),
          highlighted: !!highlight && highlight.nodes.has(e.id),
        },
      })),
    [visible, positions, selection, highlight],
  );

  const derivedEdges: Edge[] = useMemo(
    () =>
      visible.relationships.map((r) => {
        const isSel = selection?.kind === 'edge' && selection.id === r.id;
        const isHi = !!highlight && highlight.edges.has(r.id);
        const dim = !!highlight && !isHi;
        const color = isSel ? '#0f172a' : isHi ? '#dc2626' : '#94a3b8';
        return {
          id: r.id,
          source: r.source_id,
          target: r.target_id,
          label: relLabel(r.relation),
          animated: isHi,
          selected: isSel,
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 18, height: 18 },
          style: { stroke: color, strokeWidth: isSel || isHi ? 2.5 : 1.25, opacity: dim ? 0.12 : 1 },
          labelStyle: { fontSize: 11, fill: isHi ? '#991b1b' : '#475569', fontWeight: isHi ? 600 : 500, opacity: dim ? 0.15 : 1 },
          labelBgPadding: [4, 2] as [number, number],
          labelBgBorderRadius: 4,
          labelBgStyle: { opacity: dim ? 0.1 : 0.9 },
          zIndex: isHi || isSel ? 10 : 0,
        };
      }),
    [visible, selection, highlight],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<EntityNodeT>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  useEffect(() => setNodes(derivedNodes), [derivedNodes, setNodes]);
  useEffect(() => setEdges(derivedEdges), [derivedEdges, setEdges]);

  // fit to the reasoning path when a query result arrives
  useEffect(() => {
    if (!highlight || highlight.nodes.size === 0) return;
    const ids = [...highlight.nodes].map((id) => ({ id }));
    window.setTimeout(() => rf.fitView({ nodes: ids, padding: 0.4, duration: 500, maxZoom: 1.4 }), 80);
  }, [highlight, rf]);

  // center on a searched entity
  useEffect(() => {
    if (!focus) return;
    const p = positions[focus.id];
    const e = graph.entities.find((x) => x.id === focus.id);
    if (!p || !e) return;
    rf.setCenter(p.x + nodeWidth(e.canonical_name) / 2, p.y + NODE_HEIGHT / 2, { zoom: 1.3, duration: 500 });
  }, [focus, positions, graph.entities, rf]);

  const onNodeDragStop = useCallback((_: unknown, node: Node) => {
    setPositions((prev) => ({ ...prev, [node.id]: node.position }));
  }, []);

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={onNodeDragStop}
        onNodeClick={(_, n) => onSelect({ kind: 'node', id: n.id })}
        onEdgeClick={(_, e) => onSelect({ kind: 'edge', id: e.id })}
        onPaneClick={() => onSelect(null)}
        nodesConnectable={false}
        minZoom={0.1}
        maxZoom={2.5}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} color="#e2e8f0" />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(n) => TYPE_COLORS[(n.data as EntityNodeData).entityType].fill}
          maskColor="rgb(248 250 252 / 0.7)"
        />
      </ReactFlow>

      <div className="pointer-events-none absolute left-3 top-3 flex flex-col items-start gap-2">
        <div className="pointer-events-auto flex gap-2">
          <button
            onClick={() => setLayoutNonce((n) => n + 1)}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50"
          >
            Re-layout
          </button>
          {highlight && (
            <button
              onClick={onClearHighlight}
              className="rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-800 shadow-sm hover:bg-red-100"
            >
              Clear highlight
            </button>
          )}
        </div>
        {visible.truncated && (
          <div className="pointer-events-auto max-w-xs rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-900 shadow-sm">
            Showing the top {MAX_VISIBLE_NODES} of {visible.total} entities by degree. Search still covers all of them.
          </div>
        )}
        {visible.entities.length === 0 && (
          <div className="pointer-events-auto rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 shadow-sm">
            No entities match the current filters.
          </div>
        )}
      </div>
    </div>
  );
}

export function GraphCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  );
}
