import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, API_URL } from './api/client';
import { GraphCanvas } from './components/GraphCanvas';
import { NodeDetailPanel } from './components/NodeDetailPanel';
import { QueryPanel } from './components/QueryPanel';
import { SearchFilterBar } from './components/SearchFilterBar';
import { UploadPanel } from './components/UploadPanel';
import { ErrorNote, Spinner } from './components/Spinner';
import { ENTITY_TYPES, type Filters, type GraphResponse, type QueryResponse, type Selection } from './types';

type Tab = 'upload' | 'details' | 'ask';
const STORAGE_KEY = 'kg.lastGraph';

function loadStored(): { graphId: string; docIds: string[] } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
function store(graphId: string, docIds: string[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ graphId, docIds }));
  } catch {
    /* storage unavailable */
  }
}

export default function App() {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [docIds, setDocIds] = useState<string[]>([]);
  const [booting, setBooting] = useState(true);
  const [tab, setTab] = useState<Tab>('upload');
  const [selection, setSelection] = useState<Selection>(null);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [highlightOn, setHighlightOn] = useState(false);
  const [focus, setFocus] = useState<{ id: string; nonce: number } | null>(null);
  const [filters, setFilters] = useState<Filters>({ types: new Set(ENTITY_TYPES), relations: new Set(), minConfidence: 0 });
  const [llmEnabled, setLlmEnabled] = useState<boolean | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [sampleLoading, setSampleLoading] = useState(false);
  const [sampleError, setSampleError] = useState<string | null>(null);

  const relationsInGraph = useMemo(
    () => (graph ? [...new Set(graph.relationships.map((r) => r.relation))].sort() : []),
    [graph],
  );

  const applyGraph = useCallback((g: GraphResponse, ids: string[]) => {
    setGraph(g);
    setDocIds(ids);
    setSelection(null);
    setResult(null);
    setHighlightOn(false);
    setFilters({
      types: new Set(ENTITY_TYPES),
      relations: new Set(g.relationships.map((r) => r.relation)),
      minConfidence: 0,
    });
    store(g.graph_id, ids);
  }, []);

  useEffect(() => {
    api
      .health()
      .then((h) => setLlmEnabled(h.llm_enabled))
      .catch((e: Error) => setApiError(e.message));
    const stored = loadStored();
    if (!stored) {
      setBooting(false);
      return;
    }
    api
      .getGraph(stored.graphId)
      .then((g) => {
        applyGraph(g, stored.docIds);
        setTab('ask');
      })
      .catch(() => undefined)
      .finally(() => setBooting(false));
  }, [applyGraph]);

  const loadSample = async () => {
    setSampleLoading(true);
    setSampleError(null);
    try {
      const doc = await api.loadSample();
      const g = await api.buildGraph([doc.document_id]);
      applyGraph(g, [doc.document_id]);
      setTab('ask');
    } catch (e) {
      setSampleError((e as Error).message);
    } finally {
      setSampleLoading(false);
    }
  };

  const select = (s: Selection) => {
    setSelection(s);
    if (s) setTab('details');
  };

  const highlight = useMemo(
    () =>
      result && highlightOn
        ? { nodes: new Set(result.highlighted_node_ids), edges: new Set(result.highlighted_edge_ids) }
        : null,
    [result, highlightOn],
  );

  const tabs: { id: Tab; label: string; disabled?: boolean }[] = [
    { id: 'upload', label: 'Upload' },
    { id: 'details', label: 'Details', disabled: !graph },
    { id: 'ask', label: 'Ask', disabled: !graph },
  ];

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b-2 border-red-600 bg-white px-5 py-3">
        <div className="flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          <div>
            <h1 className="text-sm font-semibold text-slate-900">GraphForge</h1>
            <p className="text-xs text-slate-500">Documents → graph → explainable multi-hop answers</p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {graph && (
            <span className="text-slate-500">
              {graph.stats.node_count} entities · {graph.stats.edge_count} relations
            </span>
          )}
          {llmEnabled !== null && (
            <span
              className={`rounded-full px-2 py-0.5 font-medium ${
                llmEnabled ? 'bg-red-100 text-red-800' : 'bg-slate-100 text-slate-600'
              }`}
              title={llmEnabled ? 'Gemini is used for relation extraction and answer phrasing' : 'Rule-based extraction and template answers'}
            >
              {llmEnabled ? 'Gemini on' : 'Rule-based mode'}
            </span>
          )}
        </div>
      </header>

      {apiError && (
        <div className="border-b border-rose-200 bg-rose-50 px-5 py-2 text-sm text-rose-800">
          {apiError} (API: {API_URL})
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-[7] flex-col">
          {graph && (
            <SearchFilterBar
              graphId={graph.graph_id}
              filters={filters}
              relationsInGraph={relationsInGraph}
              onChange={setFilters}
              onPick={(id) => {
                setFocus({ id, nonce: Date.now() });
                select({ kind: 'node', id });
              }}
            />
          )}
          <div className="relative min-h-0 flex-1">
            {graph ? (
              <GraphCanvas
                graph={graph}
                filters={filters}
                selection={selection}
                highlight={highlight}
                focus={focus}
                onSelect={select}
                onClearHighlight={() => setHighlightOn(false)}
              />
            ) : (
              <div className="flex h-full items-center justify-center p-8">
                {booting ? (
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <Spinner /> Loading…
                  </div>
                ) : (
                  <div className="max-w-md text-center">
                    <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
                      <img src="/favicon.svg" alt="" className="h-8 w-8" />
                    </div>
                    <h2 className="text-lg font-semibold text-slate-900">No graph loaded</h2>
                    <p className="mt-1 text-sm text-slate-500">
                      Upload a PDF or text file, or load the bundled sample about the AI industry to see the graph
                      and ask multi-hop questions.
                    </p>
                    <button
                      onClick={loadSample}
                      disabled={sampleLoading}
                      className="mt-5 inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                    >
                      {sampleLoading && <Spinner />}
                      {sampleLoading ? 'Processing sample…' : 'Load sample data'}
                    </button>
                    {sampleError && (
                      <div className="mt-4 text-left">
                        <ErrorNote message={sampleError} onRetry={loadSample} />
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </main>

        <aside className="flex w-[30%] min-w-[340px] max-w-[480px] flex-col border-l border-slate-200 bg-white">
          <nav className="flex border-b border-slate-200">
            {tabs.map((t) => (
              <button
                key={t.id}
                disabled={t.disabled}
                onClick={() => setTab(t.id)}
                className={`flex-1 border-b-2 px-3 py-2.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
                  tab === t.id ? 'border-red-600 text-red-700' : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {tab === 'upload' && (
              <UploadPanel
                graph={graph}
                activeDocIds={docIds}
                onGraph={(g, ids) => {
                  applyGraph(g, ids);
                  setTab('ask');
                }}
                onLoadSample={loadSample}
                sampleLoading={sampleLoading}
              />
            )}
            {tab === 'details' && graph && (
              <NodeDetailPanel
                graph={graph}
                selection={selection}
                onSelectNode={(id) => {
                  setFocus({ id, nonce: Date.now() });
                  setSelection({ kind: 'node', id });
                }}
                onSelectEdge={(id) => setSelection({ kind: 'edge', id })}
              />
            )}
            {tab === 'ask' && graph && (
              <QueryPanel
                graph={graph}
                result={result}
                onResult={(r) => {
                  setResult(r);
                  setHighlightOn(!!r && r.highlighted_node_ids.length > 0);
                }}
              />
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
