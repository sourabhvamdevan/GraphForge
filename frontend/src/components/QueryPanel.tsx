import { useMemo, useState } from 'react';
import { api } from '../api/client';
import type { GraphData, QueryResponse } from '../types';
import { exampleQuestions } from '../lib/examples';
import { CONFIDENCE_STYLES, relLabel } from '../lib/style';
import { ErrorNote, Spinner } from './Spinner';

interface Props {
  graph: GraphData;
  result: QueryResponse | null;
  onResult: (r: QueryResponse | null) => void;
}

export function QueryPanel({ graph, result, onResult }: Props) {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const examples = useMemo(() => exampleQuestions(graph), [graph]);

  const ask = async (q: string) => {
    const text = q.trim();
    if (!text) return;
    setQuestion(text);
    setLoading(true);
    setError(null);
    try {
      onResult(await api.query(graph.graph_id, text));
    } catch (e) {
      setError((e as Error).message);
      onResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5 p-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
        className="space-y-2"
      >
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              ask(question);
            }
          }}
          rows={3}
          placeholder="Ask a question about the graph…"
          className="w-full resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-red-500 focus:ring-2 focus:ring-red-100"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          {loading && <Spinner />} Ask
        </button>
      </form>

      {examples.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Try</p>
          <div className="flex flex-col gap-1.5">
            {examples.map((ex) => (
              <button
                key={ex}
                onClick={() => ask(ex)}
                disabled={loading}
                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-left text-sm text-slate-700 hover:border-red-300 hover:bg-red-50"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <ErrorNote message={error} onRetry={() => ask(question)} />}

      {result && !loading && (
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Answer</p>
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${CONFIDENCE_STYLES[result.confidence]}`}>
                {result.confidence} confidence
              </span>
            </div>
            <p className="text-sm leading-relaxed text-slate-800">{result.answer}</p>
            {result.matched_entities.length > 0 && (
              <p className="mt-3 text-xs text-slate-500">Matched: {result.matched_entities.join(', ')}</p>
            )}
          </div>

          {result.paths.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Reasoning paths ({result.paths.length})
              </p>
              <div className="space-y-2">
                {result.paths.map((path, i) => (
                  <details key={i} open={i === 0} className="group rounded-lg border border-slate-200 bg-white">
                    <summary className="cursor-pointer list-none px-3 py-2 text-sm font-medium text-slate-700">
                      <span className="mr-1 inline-block transition group-open:rotate-90">▸</span>
                      Path {i + 1} · {path.length} hop{path.length === 1 ? '' : 's'}
                    </summary>
                    <ol className="space-y-3 border-t border-slate-100 px-3 py-3">
                      {path.map((step, j) => (
                        <li key={j}>
                          <p className="text-sm">
                            <span className="font-medium">{step.source}</span>{' '}
                            <span className="rounded bg-red-50 px-1.5 py-0.5 font-mono text-xs text-red-800">
                              —{relLabel(step.relation)}→
                            </span>{' '}
                            <span className="font-medium">{step.target}</span>
                          </p>
                          {step.evidence ? (
                            <div className="mt-1 border-l-2 border-red-200 pl-3">
                              <p className="text-xs italic text-slate-600">“{step.evidence.sentence}”</p>
                              <p className="text-[11px] text-slate-400">
                                {step.evidence.document_name} · chunk {step.evidence.chunk_index}
                              </p>
                            </div>
                          ) : (
                            <p className="mt-1 text-xs text-slate-400">No source sentence</p>
                          )}
                        </li>
                      ))}
                    </ol>
                  </details>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
