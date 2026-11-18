# GraphForge

Converts PDFs/text into a knowledge graph, lets users explore it visually, and answers natural-language questions via multi-hop graph traversal with the supporting path and source evidence shown.

> **Build instructions for AI coding agents:** Read this entire file before writing code. Follow the build order in §12. Do not add features, services, or dependencies not listed here. Every phase has acceptance criteria; do not start the next phase until they pass. When a decision is already made below, do not re-litigate it.

---

## 1. Goal and Non-Goals

**Goal:** a working, deployable demo that proves: unstructured text → structured graph → explainable multi-hop answers.

**In scope**
- Upload PDF/TXT, extract entities and relations, build a graph
- Interactive graph visualization with search, filter, node/edge inspection
- Question answering over the graph with visible reasoning path + source sentences

**Out of scope (do not build)**
- Auth, multi-user, accounts
- Graph databases (Neo4j etc.), vector DBs, embeddings, Docker/K8s
- Temporal modeling, contradiction resolution, distributed processing
- OCR for scanned PDFs

---

## 2. Fixed Technical Decisions

| Concern | Decision |
|---|---|
| Backend | Python 3.10+, FastAPI, Pydantic v2 |
| PDF parsing | PyMuPDF (`fitz`) |
| NER | spaCy `en_core_web_sm` |
| Relation extraction | **LLM-first (Gemini), rule-based fallback** — see §5 |
| Graph engine | NetworkX `MultiDiGraph`, held in memory per graph |
| Persistence | SQLite (via `sqlite3` or SQLModel); JSON export endpoint |
| Frontend | React 18 + TypeScript + Vite + Tailwind |
| Graph UI | React Flow (`@xyflow/react`) + `dagre` for auto layout |
| LLM | Gemini API via `google-genai`; **optional**, app must run without a key |
| Deploy | Frontend → Vercel, backend → Render |

Rationale for LLM-first relation extraction: spaCy NER is reliable for entities, but its dependency-based relation extraction is weak. LLM handles relations; spaCy handles entities and grounds/validates them.

---

## 3. Repository Structure

```text
graphforge/
├── README.md
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, router mounting
│   │   ├── config.py            # env settings (pydantic-settings)
│   │   ├── models.py            # Pydantic schemas (§4)
│   │   ├── db.py                # SQLite setup + CRUD
│   │   ├── routers/
│   │   │   ├── documents.py
│   │   │   ├── graph.py
│   │   │   └── query.py
│   │   └── services/
│   │       ├── ingestion.py     # PDF/TXT → clean text → chunks
│   │       ├── entity_extractor.py
│   │       ├── relation_extractor.py
│   │       ├── resolver.py      # entity deduplication
│   │       ├── graph_builder.py # build + validate NetworkX graph
│   │       ├── reasoner.py      # query → paths
│   │       └── answerer.py      # paths → answer text
│   ├── data/sample/             # sample docs (§11)
│   └── tests/
└── frontend/
    ├── package.json
    └── src/
        ├── api/client.ts
        ├── types.ts             # mirrors backend schemas
        ├── components/
        │   ├── UploadPanel.tsx
        │   ├── GraphCanvas.tsx
        │   ├── NodeDetailPanel.tsx
        │   ├── SearchFilterBar.tsx
        │   └── QueryPanel.tsx
        └── App.tsx
```

---

## 4. Data Models

Define these exactly in `backend/app/models.py` and mirror in `frontend/src/types.ts`.

```python
EntityType = Literal["PERSON", "ORG", "TECHNOLOGY", "PRODUCT", "LOCATION", "OTHER"]

class Entity(BaseModel):
    id: str                       # slug of canonical_name, e.g. "openai"
    canonical_name: str
    type: EntityType
    aliases: list[str] = []
    mention_count: int = 1

class Evidence(BaseModel):
    document_id: str
    document_name: str
    chunk_index: int
    sentence: str                 # exact source sentence

class Relationship(BaseModel):
    id: str
    source_id: str                # Entity.id
    target_id: str                # Entity.id
    relation: str                 # one of RELATION_TYPES
    confidence: float             # 0..1
    evidence: list[Evidence]

class GraphData(BaseModel):
    graph_id: str
    entities: list[Entity]
    relationships: list[Relationship]

class ReasoningStep(BaseModel):
    source: str                   # entity canonical_name
    relation: str
    target: str
    evidence: Evidence | None

class QueryResponse(BaseModel):
    question: str
    answer: str
    matched_entities: list[str]
    paths: list[list[ReasoningStep]]     # each path = ordered steps
    highlighted_node_ids: list[str]
    highlighted_edge_ids: list[str]
    confidence: Literal["high", "medium", "low"]
```

### Controlled relation vocabulary

Use only these relation types (LLM prompt and fallback rules must both respect this list). Normalize anything else to the closest match or discard it.

```python
RELATION_TYPES = [
    "founded", "works_at", "invested_in", "acquired", "partnered_with",
    "uses", "uses_infrastructure", "developed", "located_in",
    "competes_with", "part_of", "collaborates_with", "related_to",
]
```

`related_to` is a last resort; do not emit it if a specific type fits.

---

## 5. Processing Pipeline

### 5.1 Ingestion (`ingestion.py`)
1. PDF → text with PyMuPDF page by page; TXT → read as UTF-8.
2. Normalize: collapse whitespace, strip hyphenated line breaks, remove page numbers/headers if repeated on ≥3 pages.
3. Sentence-split with spaCy; group into chunks of ~5 sentences with 1-sentence overlap. Keep `chunk_index` and per-sentence text for evidence.
4. Reject files > 10 MB or > 50 pages with a clear 413/422 error.

### 5.2 Entity extraction (`entity_extractor.py`)
- Run spaCy NER per chunk. Map labels: `PERSON→PERSON`, `ORG→ORG`, `GPE/LOC→LOCATION`, `PRODUCT→PRODUCT`; everything else dropped.
- spaCy has no TECHNOLOGY label. Add a spaCy `EntityRuler` with a seed list of technology terms in `data/tech_terms.json` (e.g. Azure, AWS, PyTorch, Kubernetes, GPT-4) and, if Gemini is enabled, let the LLM step in 5.3 add TECHNOLOGY entities.
- Filter: drop entities < 2 chars, pure digits, or in a stoplist.

### 5.3 Relation extraction (`relation_extractor.py`)
Per chunk, produce `(subject, relation, object, sentence)` triples.

**Primary path (Gemini enabled):**
- One call per chunk. Provide the chunk text, the spaCy-detected entities, and `RELATION_TYPES`.
- Require JSON-only output:
```json
{"triples": [{"subject": "...", "relation": "invested_in", "object": "...", "sentence": "exact sentence from chunk"}]}
```
- Instructions to include in the prompt: use only listed relations; subject and object must be entities that appear in the chunk; `sentence` must be copied verbatim; return `{"triples": []}` if none; do not infer facts not stated.
- Validate: parse JSON (strip code fences), drop triples whose relation is not in the vocabulary, whose sentence is not a substring of the chunk, or whose subject/object cannot be matched to a detected entity (fuzzy match, §5.4 threshold).
- Retry once on JSON parse failure; on second failure fall back to the rule path for that chunk.
- Rate limit: process chunks with bounded concurrency (max 3) and exponential backoff on 429.

**Fallback path (no API key or LLM failure):**
- For each sentence containing ≥2 detected entities, use spaCy dependency parse: find the verb between the subject and object spans, lemmatize it, and map via a verb→relation table in `data/verb_relations.json` (e.g. `invest→invested_in`, `found→founded`, `acquire→acquired`, `partner→partnered_with`, `use→uses`, `build/develop/create→developed`).
- Unmapped verbs → skip (do not emit `related_to` from rules).
- Set confidence 0.5 for rule-based triples, 0.8 for LLM triples.

### 5.4 Entity resolution (`resolver.py`)
Deterministic, no LLM:
1. Normalize: lowercase, strip punctuation and corporate suffixes (`inc`, `corp`, `ltd`, `llc`, `co`).
2. Merge if normalized names are equal, or one is a token-subset of the other for the same type (e.g. "Sam Altman" / "Altman"), or `rapidfuzz.fuzz.token_sort_ratio ≥ 90`.
3. Canonical name = longest original surface form in the cluster; others become `aliases`.
4. Never merge across different types except `OTHER`.

### 5.5 Graph construction (`graph_builder.py`)
- Build a `networkx.MultiDiGraph`; node id = `Entity.id`; edge key = relationship id.
- Merge duplicate `(source, relation, target)` edges: union evidence, take max confidence.
- Validation: remove self-loops, edges referencing missing nodes; log counts removed.
- Graph stats returned with the graph: node count, edge count, connected components.
- Persist entities, relationships, and evidence to SQLite; rebuild the NetworkX graph from SQLite on server start or on first access.

---

## 6. Reasoning Engine (`reasoner.py`, `answerer.py`)

Implement this exact algorithm; do not substitute embeddings or vector search.

1. **Entity linking:** extract candidate entity mentions from the question (spaCy NER + n-gram match against all canonical names and aliases). Match with `rapidfuzz` (threshold ≥ 85). Return `matched_entities`.
2. **Question pattern detection (rule-based):**
   - *Relation lookup*: "Who/What did X {relation}?" → one-hop out-edges of X with that relation.
   - *Chained lookup*: "What {Y} is associated with the {company} that X {relation}?" → follow X's relation edge, then collect the second-hop edges from the result node.
   - *Connection*: "How are X and Y related/connected?" → shortest and up to 3 simple paths between X and Y over the **undirected view**, max length 4.
   - *Fallback*: if 1 entity matched → return its neighborhood (≤2 hops); if 0 matched → return a low-confidence "no matching entities" response.
   - Relation keywords map to `RELATION_TYPES` via a synonym table in `data/relation_synonyms.json` (e.g. "invested in" / "backed" → `invested_in`; "infrastructure" / "cloud" → `uses_infrastructure`).
3. **Traversal:** BFS with `max_hops = 3` default (configurable). Respect edge direction for relation-specific patterns; use undirected for connection queries. Cap total returned paths at 5, ranked by (fewer hops, higher mean confidence).
4. **Answer generation (`answerer.py`):**
   - Default: template-based answer built strictly from the paths, e.g. `"Microsoft invested in OpenAI, which uses infrastructure from Azure."`
   - If Gemini enabled: pass only the retrieved paths + evidence sentences and ask for a one- or two-sentence answer using **only** that content; if the model output mentions an entity not in the paths, discard it and use the template.
5. **Confidence:** `high` = path found where every hop has ≥1 evidence sentence and mean confidence ≥ 0.7; `medium` = path found otherwise; `low` = fallback/no path.
6. If no path exists, say so explicitly. Never fabricate an answer.

---

## 7. API Specification

Base URL `/api`. All responses JSON. Errors use `{"detail": "message"}`.

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| POST | `/documents` | Upload and process a file | multipart `file` | `{document_id, name, chunks, status}` |
| GET | `/documents` | List documents | — | `[{document_id, name, created_at}]` |
| POST | `/graph/build` | Build graph from document ids | `{document_ids: string[]}` | `GraphData` + `stats` |
| GET | `/graph/{graph_id}` | Fetch graph | — | `GraphData` + `stats` |
| GET | `/graph/{graph_id}/entity/{entity_id}` | Entity detail with neighbors and evidence | — | entity + incident relationships |
| GET | `/graph/{graph_id}/search?q=` | Entity search | — | `Entity[]` (fuzzy) |
| GET | `/graph/{graph_id}/export` | JSON export | — | `GraphData` |
| POST | `/query` | Ask a question | `{graph_id, question, max_hops?}` | `QueryResponse` |
| GET | `/health` | Health check | — | `{status: "ok", llm_enabled: bool}` |

Processing of `/documents` + `/graph/build` is synchronous for the initial version (documents capped at 50 pages). Return progress-friendly errors; no job queue.

---

## 8. Frontend Specification

Single-page app, two-pane layout: graph canvas (left, ~70%) and side panel (right) with tabs **Upload**, **Details**, **Ask**.

**GraphCanvas**
- React Flow; nodes colored by `EntityType`; edge label = relation name; arrowheads show direction.
- Auto layout with dagre on load and when a graph rebuilds; "Re-layout" button.
- Click node → select, show `NodeDetailPanel`; click edge → show relation, confidence, evidence sentences and source document.
- When a `QueryResponse` arrives: dim all nodes/edges except `highlighted_node_ids` / `highlighted_edge_ids`; "Clear highlight" button.
- For graphs > 150 nodes, show only the top 150 by degree and display a notice; search still covers all.

**SearchFilterBar:** text search (calls search endpoint, centers on match), type filter checkboxes, relation-type filter, min-confidence slider.

**NodeDetailPanel:** canonical name, aliases, type, mention count, list of incoming/outgoing relationships; clicking a neighbor selects it ("direct and indirect connections": include a toggle to show 2-hop neighborhood).

**QueryPanel:** input + submit; result shows answer, confidence badge, and expandable reasoning paths, where each step displays `source —relation→ target` and the evidence sentence beneath it. Include 3 clickable example questions generated from the loaded sample dataset.

**UX requirements:** loading and error states for every request; empty state with a "Load sample data" button that processes the bundled sample document.

---

## 9. Configuration

`backend/.env.example`
```text
GEMINI_API_KEY=            # optional; blank = rule-based fallback only
GEMINI_MODEL=gemini-2.5-flash
DATABASE_URL=sqlite:///./kg.db
ALLOWED_ORIGINS=http://localhost:5173
MAX_UPLOAD_MB=10
MAX_PAGES=50
```
`frontend/.env.example`
```text
VITE_API_URL=http://localhost:8000/api
```

`requirements.txt` (pin versions when generating): `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `python-multipart`, `pymupdf`, `spacy`, `networkx`, `rapidfuzz`, `google-genai`, `pytest`, `httpx`.
Post-install step: `python -m spacy download en_core_web_sm`.

---

## 10. Testing Requirements

Backend (`pytest`):
- `test_ingestion`: PDF and TXT produce chunks; oversized file rejected.
- `test_resolver`: "OpenAI" / "OpenAI Inc." / "Open AI" merge; "Apple" (ORG) and "apple" (OTHER) do not.
- `test_relation_fallback`: sample sentence "Microsoft invested in OpenAI." yields `(Microsoft, invested_in, OpenAI)`.
- `test_graph_builder`: duplicate edges merge evidence; self-loops removed.
- `test_reasoner`: on the fixture graph, the canonical question in §11 returns Azure with a 2-step path; a question about an unknown entity returns `confidence: low`.
- `test_api`: end-to-end upload → build → query using the sample file **with LLM disabled**.

Tests must pass without network access or API keys.

---

## 11. Sample Data and Canonical Demo

Create `backend/data/sample/tech_ecosystem.txt` (~400–600 words) containing explicit statements such as:
- Microsoft invested in OpenAI.
- OpenAI uses Azure infrastructure to train its models.
- Sam Altman is the CEO of OpenAI.
- Google DeepMind developed AlphaFold.
- Anthropic partnered with Amazon, which provides AWS.

Include at least 15 entities and 20 relationships, with one alias case (e.g. "Altman" / "Sam Altman").

**Canonical demo question:** *"Which cloud infrastructure is associated with the company Microsoft invested in?"*
Expected: **Azure**, via path `Microsoft —invested_in→ OpenAI —uses_infrastructure→ Azure`, with the evidence sentence shown for each hop.

---

## 12. Build Order (follow strictly)

**Phase 1 — Backend core.** Models, config, SQLite, ingestion, entity extractor, rule-based relation extractor, resolver, graph builder.
*Accept:* running a script on the sample file prints entities and relationships; tests for ingestion/resolver/builder pass.

**Phase 2 — API.** Documents, graph, search, export, health endpoints.
*Accept:* with `uvicorn`, curl upload → build → fetch graph returns valid `GraphData`; the OpenAPI docs load.

**Phase 3 — Reasoning.** Entity linking, patterns, traversal, templated answers, `/query`.
*Accept:* the canonical demo question returns Azure with the correct path; unknown-entity question returns `low`.

**Phase 4 — Frontend core.** Types, API client, upload, GraphCanvas with layout, node/edge inspection.
*Accept:* sample data loads from the empty state and renders a navigable graph.

**Phase 5 — Frontend reasoning + filters.** QueryPanel with path display and canvas highlighting, SearchFilterBar.
*Accept:* asking the canonical question highlights the 3-node path on the canvas.

**Phase 6 — LLM integration (optional layer).** Gemini relation extraction with validation and fallback; optional answer phrasing.
*Accept:* with a key, relation count on the sample increases or matches; with the key removed, all tests still pass.

**Phase 7 — Deploy.** Render (backend; start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`; build installs spaCy model), Vercel (frontend with `VITE_API_URL`), CORS configured.
*Accept:* deployed demo runs the canonical question end to end.

---

## 13. Local Setup

Prerequisites: Python 3.10+, Node.js 18+, npm.

```bash
git clone <repository-url>
cd graphforge

# Backend
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env
uvicorn app.main:app --reload     # http://localhost:8000/docs

# Frontend (new terminal)
cd frontend
npm install
cp .env.example .env
npm run dev                       # http://localhost:5173
```

---

## 14. Definition of Done

- [ ] Upload PDF/TXT → graph appears in the UI
- [ ] Every edge shows its source sentence and document
- [ ] Canonical demo question answers correctly with a highlighted path
- [ ] App fully functional with no Gemini key
- [ ] Backend tests pass offline
- [ ] Deployed frontend + backend reachable, sample data loads in one click
- [ ] No answer is ever returned without a supporting graph path