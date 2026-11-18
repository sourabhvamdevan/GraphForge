import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { DocumentSummary, GraphResponse } from '../types';
import { ErrorNote, Spinner } from './Spinner';

interface Props {
  graph: GraphResponse | null;
  activeDocIds: string[];
  onGraph: (g: GraphResponse, docIds: string[]) => void;
  onLoadSample: () => void;
  sampleLoading: boolean;
}

export function UploadPanel({ graph, activeDocIds, onGraph, onLoadSample, sampleLoading }: Props) {
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set(activeDocIds));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = () =>
    api
      .listDocuments()
      .then((d) => {
        setDocs(d);
        setListError(null);
      })
      .catch((e: Error) => setListError(e.message));

  useEffect(() => {
    refresh();
  }, [graph?.graph_id]);
  useEffect(() => setSelected(new Set(activeDocIds)), [activeDocIds]);

  const build = async (ids: string[]) => {
    setBusy('Building graph…');
    setError(null);
    try {
      const g = await api.buildGraph(ids);
      onGraph(g, ids);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const upload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setError(null);
    const newIds: string[] = [];
    try {
      for (const f of Array.from(files)) {
        setBusy(`Processing ${f.name}… (extracting entities and relations)`);
        const res = await api.uploadDocument(f);
        newIds.push(res.document_id);
      }
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
      if (!newIds.length) return;
    }
    const ids = [...new Set([...selected, ...newIds])];
    setSelected(new Set(ids));
    await refresh();
    await build(ids);
  };

  const toggle = (id: string) => {
    const s = new Set(selected);
    if (s.has(id)) s.delete(id);
    else s.add(id);
    setSelected(s);
  };

  return (
    <div className="space-y-5 p-5">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          upload(e.dataTransfer.files);
        }}
        onClick={() => !busy && inputRef.current?.click()}
        className={`cursor-pointer rounded-xl border-2 border-dashed px-4 py-8 text-center transition ${
          drag ? 'border-red-400 bg-red-50' : 'border-slate-300 bg-slate-50 hover:border-slate-400'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,.md,application/pdf,text/plain"
          multiple
          className="hidden"
          onChange={(e) => {
            upload(e.target.files);
            e.target.value = '';
          }}
        />
        <p className="text-sm font-medium text-slate-700">Drop PDF or TXT files here, or click to browse</p>
        <p className="mt-1 text-xs text-slate-500">Up to 10 MB and 50 pages per file. Scanned PDFs are not supported.</p>
      </div>

      {busy && (
        <div className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
          <Spinner /> {busy}
        </div>
      )}
      {error && <ErrorNote message={error} />}

      <button
        onClick={onLoadSample}
        disabled={sampleLoading || !!busy}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
      >
        {sampleLoading && <Spinner />} Load sample data (AI ecosystem)
      </button>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Documents</p>
          {graph && (
            <a href={api.exportUrl(graph.graph_id)} target="_blank" rel="noreferrer" className="text-xs text-red-700 hover:underline">
              Export graph JSON
            </a>
          )}
        </div>
        {listError && <ErrorNote message={listError} onRetry={refresh} />}
        {!docs && !listError && (
          <p className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </p>
        )}
        {docs && docs.length === 0 && <p className="text-sm text-slate-400">No documents uploaded yet.</p>}
        {docs && docs.length > 0 && (
          <>
            <ul className="max-h-64 space-y-1 overflow-auto">
              {docs.map((d) => (
                <li key={d.document_id}>
                  <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-50">
                    <input type="checkbox" checked={selected.has(d.document_id)} onChange={() => toggle(d.document_id)} />
                    <span className="truncate">{d.name}</span>
                    <span className="ml-auto shrink-0 text-xs text-slate-400">
                      {new Date(d.created_at).toLocaleDateString()}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
            <button
              onClick={() => build([...selected])}
              disabled={selected.size === 0 || !!busy}
              className="mt-3 w-full rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              Build graph from {selected.size} document{selected.size === 1 ? '' : 's'}
            </button>
          </>
        )}
      </section>

      {graph && (
        <section className="grid grid-cols-3 gap-2 text-center">
          {[
            ['Entities', graph.stats.node_count],
            ['Relations', graph.stats.edge_count],
            ['Components', graph.stats.connected_components],
          ].map(([label, n]) => (
            <div key={label} className="rounded-lg border border-slate-200 bg-white py-2">
              <p className="text-lg font-semibold tabular-nums text-slate-900">{n}</p>
              <p className="text-xs text-slate-500">{label}</p>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
