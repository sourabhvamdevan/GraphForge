import type {
  DocumentSummary, DocumentUploadResponse, Entity, EntityDetail, GraphData, GraphResponse,
  HealthResponse, QueryResponse,
} from '../types';

const rawUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api').trim().replace(/\/$/, '');
export const API_URL = rawUrl.endsWith('/api') ? rawUrl : `${rawUrl}/api`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new Error(`Cannot reach the API at ${API_URL}. Is the backend running?`);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<HealthResponse>('/health'),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<DocumentUploadResponse>('/documents', { method: 'POST', body: form });
  },
  loadSample: () => request<DocumentUploadResponse>('/documents/sample', { method: 'POST' }),
  listDocuments: () => request<DocumentSummary[]>('/documents'),
  buildGraph: (documentIds: string[]) => request<GraphResponse>('/graph/build', json({ document_ids: documentIds })),
  getGraph: (graphId: string) => request<GraphResponse>(`/graph/${encodeURIComponent(graphId)}`),
  entityDetail: (graphId: string, entityId: string) =>
    request<EntityDetail>(`/graph/${encodeURIComponent(graphId)}/entity/${encodeURIComponent(entityId)}`),
  search: (graphId: string, q: string) =>
    request<Entity[]>(`/graph/${encodeURIComponent(graphId)}/search?q=${encodeURIComponent(q)}`),
  exportUrl: (graphId: string) => `${API_URL}/graph/${encodeURIComponent(graphId)}/export`,
  exportGraph: (graphId: string) => request<GraphData>(`/graph/${encodeURIComponent(graphId)}/export`),
  query: (graphId: string, question: string, maxHops?: number) =>
    request<QueryResponse>('/query', json({ graph_id: graphId, question, max_hops: maxHops })),
};
