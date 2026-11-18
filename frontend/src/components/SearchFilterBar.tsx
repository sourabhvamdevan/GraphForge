import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { ENTITY_TYPES, type Entity, type EntityType, type Filters } from '../types';
import { TYPE_COLORS, TYPE_LABELS, relLabel } from '../lib/style';
import { Spinner } from './Spinner';

interface Props {
  graphId: string;
  filters: Filters;
  relationsInGraph: string[];
  onChange: (f: Filters) => void;
  onPick: (entityId: string) => void;
}

export function SearchFilterBar({ graphId, filters, relationsInGraph, onChange, onPick }: Props) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [relOpen, setRelOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setResults([]);
      setError(null);
      return;
    }
    setLoading(true);
    const t = window.setTimeout(() => {
      api
        .search(graphId, term)
        .then((r) => {
          setResults(r);
          setError(null);
        })
        .catch((e: Error) => setError(e.message))
        .finally(() => setLoading(false));
    }, 220);
    return () => window.clearTimeout(t);
  }, [q, graphId]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as globalThis.Node)) {
        setOpen(false);
        setRelOpen(false);
      }
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const toggleType = (t: EntityType) => {
    const types = new Set(filters.types);
    if (types.has(t)) types.delete(t);
    else types.add(t);
    onChange({ ...filters, types });
  };
  const toggleRel = (r: string) => {
    const relations = new Set(filters.relations);
    if (relations.has(r)) relations.delete(r);
    else relations.add(r);
    onChange({ ...filters, relations });
  };

  return (
    <div ref={wrapRef} className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-slate-200 bg-white px-4 py-2.5">
      <div className="relative w-64">
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && results[0]) {
              onPick(results[0].id);
              setOpen(false);
            }
          }}
          placeholder="Search entities…"
          className="w-full rounded-md border border-slate-300 bg-white py-1.5 pl-3 pr-8 text-sm outline-none focus:border-red-500 focus:ring-2 focus:ring-red-100"
        />
        {loading && <Spinner className="absolute right-2.5 top-2 h-4 w-4 text-slate-400" />}
        {open && q.trim() && !loading && (
          <div className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-md border border-slate-200 bg-white py-1 shadow-lg">
            {error && <p className="px-3 py-2 text-xs text-rose-700">{error}</p>}
            {!error && results.length === 0 && <p className="px-3 py-2 text-xs text-slate-500">No matches</p>}
            {results.map((e) => (
              <button
                key={e.id}
                onClick={() => {
                  onPick(e.id);
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-slate-50"
              >
                <span className="h-2 w-2 rounded-full" style={{ background: TYPE_COLORS[e.type].fill }} />
                <span className="truncate">{e.canonical_name}</span>
                {e.aliases.length > 0 && (
                  <span className="truncate text-xs text-slate-400">aka {e.aliases.join(', ')}</span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {ENTITY_TYPES.map((t) => {
          const on = filters.types.has(t);
          return (
            <button
              key={t}
              onClick={() => toggleType(t)}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                on ? 'border-slate-300 bg-white text-slate-700' : 'border-transparent bg-slate-100 text-slate-400 line-through'
              }`}
              aria-pressed={on}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: on ? TYPE_COLORS[t].fill : '#cbd5e1' }} />
              {TYPE_LABELS[t]}
            </button>
          );
        })}
      </div>

      <div className="relative">
        <button
          onClick={() => setRelOpen((o) => !o)}
          className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          Relations ({relationsInGraph.filter((r) => filters.relations.has(r)).length}/{relationsInGraph.length}) ▾
        </button>
        {relOpen && (
          <div className="absolute z-20 mt-1 w-56 rounded-md border border-slate-200 bg-white p-2 shadow-lg">
            <div className="mb-1 flex justify-between px-1 text-xs">
              <button className="text-red-700" onClick={() => onChange({ ...filters, relations: new Set(relationsInGraph) })}>
                All
              </button>
              <button className="text-red-700" onClick={() => onChange({ ...filters, relations: new Set() })}>
                None
              </button>
            </div>
            {relationsInGraph.map((r) => (
              <label key={r} className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-sm hover:bg-slate-50">
                <input type="checkbox" checked={filters.relations.has(r)} onChange={() => toggleRel(r)} />
                {relLabel(r)}
              </label>
            ))}
          </div>
        )}
      </div>

      <label className="flex items-center gap-2 text-xs text-slate-600">
        Min confidence
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={filters.minConfidence}
          onChange={(e) => onChange({ ...filters, minConfidence: Number(e.target.value) })}
          className="w-24 accent-red-600"
        />
        <span className="w-8 tabular-nums">{filters.minConfidence.toFixed(2)}</span>
      </label>
    </div>
  );
}
