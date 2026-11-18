import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { Entity, EntityDetail, GraphData, Relationship } from '../types';
import { TYPE_COLORS, TYPE_LABELS, relLabel } from '../lib/style';
import { ErrorNote, Spinner } from './Spinner';

function TypeBadge({ entity }: { entity: Entity }) {
  const c = TYPE_COLORS[entity.type];
  return (
    <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: c.soft, color: c.text }}>
      {TYPE_LABELS[entity.type]}
    </span>
  );
}

function EntityLink({ entity, onClick }: { entity?: Entity; onClick: () => void }) {
  if (!entity) return null;
  return (
    <button onClick={onClick} className="inline-flex items-center gap-1.5 font-medium text-slate-800 hover:text-red-700">
      <span className="h-2 w-2 rounded-full" style={{ background: TYPE_COLORS[entity.type].fill }} />
      {entity.canonical_name}
    </button>
  );
}

export function EvidenceList({ rel }: { rel: Relationship }) {
  if (!rel.evidence.length) return <p className="text-xs text-slate-500">No source sentence recorded.</p>;
  return (
    <ul className="space-y-2">
      {rel.evidence.map((ev, i) => (
        <li key={i} className="rounded-md border-l-2 border-red-300 bg-slate-50 px-3 py-2">
          <p className="text-sm text-slate-700">“{ev.sentence}”</p>
          <p className="mt-1 text-xs text-slate-500">
            {ev.document_name} · chunk {ev.chunk_index}
          </p>
        </li>
      ))}
    </ul>
  );
}

interface Props {
  graph: GraphData;
  selection: { kind: 'node' | 'edge'; id: string } | null;
  onSelectNode: (id: string) => void;
  onSelectEdge: (id: string) => void;
}

export function NodeDetailPanel({ graph, selection, onSelectNode, onSelectEdge }: Props) {
  const byId = useMemo(() => new Map(graph.entities.map((e) => [e.id, e])), [graph]);

  if (!selection) {
    return (
      <div className="p-5 text-sm text-slate-500">
        Click a node to see its connections, or click an edge to see the source sentences behind it.
      </div>
    );
  }
  if (selection.kind === 'edge') {
    const rel = graph.relationships.find((r) => r.id === selection.id);
    if (!rel) return <div className="p-5 text-sm text-slate-500">Relationship not found.</div>;
    return (
      <div className="space-y-4 p-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Relationship</p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <EntityLink entity={byId.get(rel.source_id)} onClick={() => onSelectNode(rel.source_id)} />
            <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-600">
              —{relLabel(rel.relation)}→
            </span>
            <EntityLink entity={byId.get(rel.target_id)} onClick={() => onSelectNode(rel.target_id)} />
          </div>
        </div>
        <div className="flex gap-6 text-sm">
          <div>
            <p className="text-xs text-slate-400">Confidence</p>
            <p className="font-medium tabular-nums">{rel.confidence.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Evidence</p>
            <p className="font-medium">{rel.evidence.length} sentence{rel.evidence.length === 1 ? '' : 's'}</p>
          </div>
        </div>
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Source sentences</p>
          <EvidenceList rel={rel} />
        </div>
      </div>
    );
  }
  return (
    <EntityDetailView
      key={selection.id}
      graph={graph}
      entityId={selection.id}
      byId={byId}
      onSelectNode={onSelectNode}
      onSelectEdge={onSelectEdge}
    />
  );
}

function EntityDetailView({
  graph, entityId, byId, onSelectNode, onSelectEdge,
}: {
  graph: GraphData;
  entityId: string;
  byId: Map<string, Entity>;
  onSelectNode: (id: string) => void;
  onSelectEdge: (id: string) => void;
}) {
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTwoHop, setShowTwoHop] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setError(null);
    api
      .entityDetail(graph.graph_id, entityId)
      .then((d) => !cancelled && setDetail(d))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [graph.graph_id, entityId, reload]);

  const twoHop = useMemo(() => {
    const adj = new Map<string, Set<string>>();
    for (const r of graph.relationships) {
      for (const [a, b] of [[r.source_id, r.target_id], [r.target_id, r.source_id]]) {
        if (!adj.has(a)) adj.set(a, new Set());
        adj.get(a)!.add(b);
      }
    }
    const direct = adj.get(entityId) ?? new Set<string>();
    const out = new Map<string, string[]>(); // 2-hop id -> via ids
    direct.forEach((via) => {
      (adj.get(via) ?? new Set<string>()).forEach((n) => {
        if (n === entityId || direct.has(n)) return;
        if (!out.has(n)) out.set(n, []);
        out.get(n)!.push(via);
      });
    });
    return [...out.entries()];
  }, [graph, entityId]);

  if (error) return <div className="p-5"><ErrorNote message={error} onRetry={() => setReload((n) => n + 1)} /></div>;
  if (!detail) {
    return (
      <div className="flex items-center gap-2 p-5 text-sm text-slate-500">
        <Spinner /> Loading entity…
      </div>
    );
  }
  const e = detail.entity;
  const relRow = (r: Relationship, dir: 'out' | 'in') => {
    const other = byId.get(dir === 'out' ? r.target_id : r.source_id);
    return (
      <li key={r.id} className="flex items-center justify-between gap-2 py-1.5 text-sm">
        <div className="flex min-w-0 items-center gap-2">
          <button
            onClick={() => onSelectEdge(r.id)}
            className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600 hover:bg-red-100 hover:text-red-800"
            title="Show evidence"
          >
            {dir === 'out' ? `${relLabel(r.relation)} →` : `← ${relLabel(r.relation)}`}
          </button>
          <span className="truncate">
            <EntityLink entity={other} onClick={() => other && onSelectNode(other.id)} />
          </span>
        </div>
        <span className="shrink-0 text-xs tabular-nums text-slate-400">{r.confidence.toFixed(2)}</span>
      </li>
    );
  };

  return (
    <div className="space-y-5 p-5">
      <div>
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-lg font-semibold text-slate-900">{e.canonical_name}</h2>
          <TypeBadge entity={e} />
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
          <div>
            <p className="text-xs text-slate-400">Mentions</p>
            <p className="font-medium tabular-nums">{e.mention_count}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Aliases</p>
            <p className="font-medium">{e.aliases.length ? e.aliases.join(', ') : '—'}</p>
          </div>
        </div>
      </div>

      <section>
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Outgoing ({detail.outgoing.length})
        </p>
        {detail.outgoing.length ? (
          <ul className="divide-y divide-slate-100">{detail.outgoing.map((r) => relRow(r, 'out'))}</ul>
        ) : (
          <p className="text-sm text-slate-400">None</p>
        )}
      </section>
      <section>
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Incoming ({detail.incoming.length})
        </p>
        {detail.incoming.length ? (
          <ul className="divide-y divide-slate-100">{detail.incoming.map((r) => relRow(r, 'in'))}</ul>
        ) : (
          <p className="text-sm text-slate-400">None</p>
        )}
      </section>

      <section>
        <label className="flex cursor-pointer items-center gap-2 text-sm font-medium text-slate-700">
          <input type="checkbox" checked={showTwoHop} onChange={(ev) => setShowTwoHop(ev.target.checked)} />
          Show indirect connections (2 hops)
        </label>
        {showTwoHop && (
          <ul className="mt-2 space-y-1.5">
            {twoHop.length === 0 && <li className="text-sm text-slate-400">No 2-hop neighbors</li>}
            {twoHop.map(([id, via]) => (
              <li key={id} className="text-sm">
                <EntityLink entity={byId.get(id)} onClick={() => onSelectNode(id)} />
                <span className="text-xs text-slate-400">
                  {' '}via {via.map((v) => byId.get(v)?.canonical_name ?? v).join(', ')}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
