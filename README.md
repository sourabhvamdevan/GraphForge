# GraphForge

[![Live Demo](https://img.shields.io/badge/Live_Demo-Vercel-black?style=for-the-badge&logo=vercel)](https://graphforge-project.vercel.app/)
[![API Status](https://img.shields.io/badge/API_Status-Online-brightgreen?style=for-the-badge&logo=render)](https://knowledge-graph-construction-and.onrender.com/api/health)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.162-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)

An end-to-end neuro-symbolic engine that transforms unstructured text and PDFs into structured knowledge graphs, visualizes complex networks interactively, and answers natural language questions through multi-hop traversal with complete evidence provenance. GraphForge uses spaCy and Gemini for extraction, NetworkX for reasoning, and React Flow for exploration.

**Live Demo:** [https://graphforge-project.vercel.app/](https://graphforge-project.vercel.app/)

---

## Table of Contents

1. [Overview](#overview)
2. [Tech Stack](#tech-stack)
3. [Architecture](#architecture)
   - [1. System Overview](#1-system-overview)
   - [2. Upload Validation Flow](#2-upload-validation-flow)
   - [3. Document Processing Sequence](#3-document-processing-sequence)
   - [4. Relation Extraction with Fallback](#4-relation-extraction-with-fallback)
   - [5. Graph Build and Entity Resolution](#5-graph-build-and-entity-resolution)
   - [6. Query and Reasoning Flow](#6-query-and-reasoning-flow)
   - [7. Multi-Hop Query Sequence](#7-multi-hop-query-sequence)
   - [8. Database Schema](#8-database-schema)
   - [9. Deployment Pipeline](#9-deployment-pipeline)
4. [Getting Started](#getting-started)
5. [Supported Question Patterns](#supported-question-patterns)
6. [REST API Reference](#rest-api-reference)
7. [Configuration Reference](#configuration-reference)
8. [Testing](#testing)
9. [Deployment](#deployment)
10. [Implementation Highlights](#implementation-highlights)
11. [Project Structure](#project-structure)
12. [License](#license)

---

## Overview

GraphForge bridges the gap between unstructured documents and queryable knowledge. Upload a PDF or text file, and the engine extracts entities and relationships, resolves duplicate names into canonical entities, builds a graph, and lets you ask questions that require chaining several facts together. Every answer shows the exact path it followed and quotes the source sentence behind each hop.

### Core Features

* **Robust Document Ingestion**: PDFs and raw text are parsed with PyMuPDF, with page-level cleaning, repeated header and footer removal, sentence splitting, and overlapping chunks.
* **Dual-Mode Relation Extraction**: Gemini 2.5 Flash extracts triples when an API key is configured, and a deterministic spaCy dependency-rule engine takes over per chunk if the model fails. With no API key, the rule engine runs alone and needs zero external services.
* **Intelligent Entity Resolution**: Normalizes corporate suffixes, merges aliases such as "Sam Altman" and "Altman", and applies token-based fuzzy matching.
* **Interactive Visualization**: React Flow with Dagre hierarchical layout, real-time node filtering, search, type badges, and degree statistics.
* **Explainable Multi-Hop Reasoning**: Directed and undirected BFS plus shortest-path search over a NetworkX multigraph. Every hop quotes its source sentence and document.
* **Safe Rejection**: If no supporting path exists, or the entities are not in the graph, the engine says so instead of guessing.
* **Graceful Degradation**: The LLM is always optional. Extraction and answer phrasing both fall back to deterministic logic.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend Framework | React 18 with TypeScript, built with Vite |
| Styling | Tailwind CSS |
| Graph Visualization | React Flow (`@xyflow/react`) with Dagre layout |
| Backend Framework | FastAPI (Python 3.11) |
| NLP | spaCy (`en_core_web_sm`) |
| Graph Engine | NetworkX (MultiDiGraph) |
| Document Parsing | PyMuPDF |
| LLM (optional) | Gemini 2.5 Flash |
| Database | SQLite with an in-memory graph cache |
| Validation | Pydantic v2 |
| Deployment | Vercel (frontend), Render (backend), Docker with Nginx |

---

## Architecture

All diagrams below are written in Mermaid and render automatically on GitHub.

### 1. System Overview

```mermaid
flowchart TB
    User(["User<br/>Browser"]):::user

    subgraph CLIENT["Client Layer - React 18 + TypeScript on Vercel"]
        direction LR
        UP["Upload Panel"]:::frontend
        GC["Graph Canvas<br/>React Flow + Dagre"]:::frontend
        QP["Query Panel"]:::frontend
        ND["Node Detail Panel"]:::frontend
    end

    subgraph API["API Layer - FastAPI on Render"]
        direction LR
        CORS["CORS Middleware<br/>ALLOWED_ORIGINS"]:::security
        RD["/api/documents"]:::backend
        RG["/api/graph"]:::backend
        RQ["/api/query"]:::backend
        CORS --> RD
        CORS --> RG
        CORS --> RQ
    end

    subgraph SVC["Service Layer"]
        direction TB
        ING["Ingestion<br/>PyMuPDF, chunking"]:::service
        EXT["Entity Extractor<br/>spaCy NER"]:::service
        REL["Relation Extractor<br/>Gemini or rules"]:::service
        RES["Entity Resolver"]:::service
        GB["Graph Builder<br/>NetworkX"]:::service
        RSN["Reasoner<br/>BFS and shortest path"]:::service
        ANS["Answerer<br/>template or Gemini"]:::service
        ING --> EXT --> REL
        RES --> GB
        RSN --> ANS
    end

    subgraph DATA["Data Layer"]
        direction TB
        DB[("SQLite<br/>documents, graphs, entities,<br/>relationships, evidence")]:::data
        CACHE["In-memory Graph Cache<br/>NetworkX MultiDiGraph"]:::data
        VOC["Controlled Vocabularies<br/>seeds, verbs, synonyms"]:::data
    end

    subgraph EXTSVC["External Services"]
        Gemini{{"Gemini 2.5 Flash<br/>optional"}}:::ai
    end

    User --> UP
    User --> GC
    User --> QP
    UP --> RD
    GC --> RG
    ND --> RG
    QP --> RQ

    RD --> ING
    REL --> DB
    RG --> RES
    GB --> DB
    GB --> CACHE
    RQ --> RSN
    RSN --> CACHE
    VOC -.-> EXT
    VOC -.-> REL
    REL -.->|"extraction"| Gemini
    ANS -.->|"phrasing"| Gemini

    classDef user fill:#fde68a,stroke:#b45309,stroke-width:2px,color:#451a03
    classDef frontend fill:#bfdbfe,stroke:#1d4ed8,stroke-width:2px,color:#172554
    classDef security fill:#fecaca,stroke:#b91c1c,stroke-width:2px,color:#450a0a
    classDef backend fill:#c7d2fe,stroke:#4338ca,stroke-width:2px,color:#1e1b4b
    classDef service fill:#bbf7d0,stroke:#15803d,stroke-width:2px,color:#052e16
    classDef data fill:#fbcfe8,stroke:#be185d,stroke-width:2px,color:#500724
    classDef ai fill:#e9d5ff,stroke:#7e22ce,stroke-width:2px,color:#3b0764

    style CLIENT fill:#eff6ff,stroke:#1d4ed8,stroke-width:2px,stroke-dasharray: 4 4
    style API fill:#eef2ff,stroke:#4338ca,stroke-width:2px,stroke-dasharray: 4 4
    style SVC fill:#f0fdf4,stroke:#15803d,stroke-width:2px,stroke-dasharray: 4 4
    style DATA fill:#fdf2f8,stroke:#be185d,stroke-width:2px,stroke-dasharray: 4 4
    style EXTSVC fill:#faf5ff,stroke:#7e22ce,stroke-width:2px,stroke-dasharray: 4 4
```

### 2. Upload Validation Flow

Every upload is validated before any NLP work starts. Each failure returns a clear HTTP error with a readable message.

```mermaid
flowchart LR
    Req(["POST /api/documents"]):::start --> Size{"Larger than<br/>MAX_UPLOAD_MB?"}:::check
    Size -->|"yes"| E1["413 File too large"]:::deny
    Size -->|"no"| Empty{"File empty?"}:::check
    Empty -->|"yes"| E2["422 File is empty"]:::deny
    Empty -->|"no"| Type{"File type?"}:::check
    Type -->|"other"| E3["422 Unsupported type"]:::deny
    Type -->|"pdf"| Pages{"Pages over<br/>MAX_PAGES?"}:::check
    Type -->|"txt"| Utf{"Valid UTF-8?"}:::check
    Pages -->|"yes"| E4["422 Page limit exceeded"]:::deny
    Pages -->|"no"| Layer{"Has a text<br/>layer?"}:::check
    Layer -->|"no"| E5["422 Scanned PDF<br/>not supported"]:::deny
    Layer -->|"yes"| Norm["Normalize text<br/>split sentences, chunk"]:::ok
    Utf -->|"no"| E6["422 Must be UTF-8"]:::deny
    Utf -->|"yes"| Norm
    Norm --> Next["Extraction and storage"]:::ok

    classDef start fill:#fde68a,stroke:#b45309,stroke-width:2px,color:#451a03
    classDef check fill:#bfdbfe,stroke:#1d4ed8,stroke-width:2px,color:#172554
    classDef deny fill:#fecaca,stroke:#b91c1c,stroke-width:2px,color:#450a0a
    classDef ok fill:#bbf7d0,stroke:#15803d,stroke-width:2px,color:#052e16
```

### 3. Document Processing Sequence

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant UI as React UI
    participant API as Documents Router
    participant ING as Ingestion
    participant EX as Relation Extractor
    participant G as Gemini 2.5 Flash
    participant DB as SQLite

    rect rgb(254, 243, 199)
    Note over U,API: Upload
    U->>UI: Choose a PDF or TXT file, or load sample data
    UI->>API: POST /api/documents as multipart form
    end

    rect rgb(219, 234, 254)
    Note over API,ING: Ingestion
    API->>ING: ingest filename and bytes
    ING->>ING: Clean pages, split sentences
    ING-->>API: Chunks of 5 sentences with 1 sentence overlap
    end

    rect rgb(243, 232, 255)
    Note over EX,G: Extraction
    API->>EX: extract_document chunks
    EX->>EX: spaCy NER for every unique sentence
    loop Each chunk
        opt API key configured
            EX->>G: Prompt with chunk text and known mentions
            G-->>EX: JSON triples
        end
        EX->>EX: Use rule triples if Gemini failed or is disabled
    end
    EX-->>API: Mentions, triples and method
    end

    rect rgb(220, 252, 231)
    Note over API,DB: Save
    API->>DB: INSERT document with chunks, mentions, triples
    API-->>UI: document_id, chunk count, status processed
    UI->>API: POST /api/graph/build with document ids
    end
```

### 4. Relation Extraction with Fallback

Extraction never depends on the LLM. Each chunk is handled independently, so one failed model call does not break the document.

```mermaid
flowchart LR
    A(["Chunks of a document"]):::start --> B["spaCy NER<br/>mentions per sentence"]:::nlp
    B --> C{"GEMINI_API_KEY<br/>configured?"}:::check
    C -->|"no"| R["Rule Engine<br/>dependency paths, verb map,<br/>relation synonyms"]:::rules
    C -->|"yes"| D["Gemini 2.5 Flash<br/>JSON mode, temperature 0"]:::ai
    D --> E{"Call succeeded<br/>and JSON valid?"}:::check
    E -->|"no"| W["Log warning<br/>retry on HTTP 429 with backoff"]:::warn
    W --> R
    E -->|"yes"| F["Grounding Check<br/>entities must match mentions,<br/>sentence must exist in chunk"]:::ai
    F --> T["LLM triples"]:::ai
    R --> U["Rule triples"]:::rules
    T --> M{"Methods used<br/>across chunks"}:::check
    U --> M
    M -->|"one method"| X["method: llm or rules"]:::ok
    M -->|"both"| Y["method: mixed"]:::ok
    X --> Z[("Saved to documents table")]:::data
    Y --> Z

    classDef start fill:#fde68a,stroke:#b45309,stroke-width:2px,color:#451a03
    classDef nlp fill:#bfdbfe,stroke:#1d4ed8,stroke-width:2px,color:#172554
    classDef check fill:#c7d2fe,stroke:#4338ca,stroke-width:2px,color:#1e1b4b
    classDef rules fill:#bbf7d0,stroke:#15803d,stroke-width:2px,color:#052e16
    classDef ai fill:#e9d5ff,stroke:#7e22ce,stroke-width:2px,color:#3b0764
    classDef warn fill:#fed7aa,stroke:#c2410c,stroke-width:2px,color:#431407
    classDef ok fill:#a7f3d0,stroke:#047857,stroke-width:2px,color:#064e3b
    classDef data fill:#fbcfe8,stroke:#be185d,stroke-width:2px,color:#500724
```

### 5. Graph Build and Entity Resolution

```mermaid
flowchart TB
    A(["POST /api/graph/build<br/>document_ids"]):::start --> B{"At least one<br/>id provided?"}:::check
    B -->|"no"| E1["422 Provide a document id"]:::deny
    B -->|"yes"| C["Load documents from SQLite"]:::process
    C --> D{"All ids<br/>found?"}:::check
    D -->|"no"| E2["404 Unknown document ids"]:::deny
    D -->|"yes"| H["graph_id = SHA-1 of sorted ids<br/>same input gives same graph"]:::process

    H --> R1

    subgraph RESOLVE["Entity Resolution - deterministic"]
        direction TB
        R1["Collect mentions<br/>from all documents"]:::resolve
        R2["Normalize names<br/>strip corporate suffixes"]:::resolve
        R3["Union-Find merge<br/>same type, alias or token match"]:::resolve
        R4["Canonical entities<br/>with alias lists and mention counts"]:::resolve
        R1 --> R2 --> R3 --> R4
    end

    R4 --> G1["Map triple surface names<br/>to entity ids"]:::process
    G1 --> G2["Attach evidence<br/>document, chunk, sentence"]:::process
    G2 --> G3["Merge duplicate edges<br/>union evidence, keep max confidence"]:::process
    G3 --> G4["Validate and compute stats<br/>drop self-loops and dangling edges"]:::process
    G4 --> S[("Persist to SQLite<br/>entities, relationships, evidence")]:::data
    S --> C2["Cache NetworkX MultiDiGraph<br/>in memory"]:::data
    C2 --> OUT(["GraphResponse to UI<br/>Dagre layout and render"]):::ok

    classDef start fill:#fde68a,stroke:#b45309,stroke-width:2px,color:#451a03
    classDef check fill:#bfdbfe,stroke:#1d4ed8,stroke-width:2px,color:#172554
    classDef deny fill:#fecaca,stroke:#b91c1c,stroke-width:2px,color:#450a0a
    classDef process fill:#c7d2fe,stroke:#4338ca,stroke-width:2px,color:#1e1b4b
    classDef resolve fill:#bbf7d0,stroke:#15803d,stroke-width:2px,color:#052e16
    classDef data fill:#fbcfe8,stroke:#be185d,stroke-width:2px,color:#500724
    classDef ok fill:#a7f3d0,stroke:#047857,stroke-width:3px,color:#064e3b

    style RESOLVE fill:#f0fdf4,stroke:#15803d,stroke-width:2px,stroke-dasharray: 4 4
```

### 6. Query and Reasoning Flow

```mermaid
flowchart TB
    Q(["POST /api/query<br/>graph_id and question"]):::start --> V{"Graph exists and<br/>question not empty?"}:::check
    V -->|"no"| E["404 or 422 error"]:::deny
    V -->|"yes"| L["Entity Linking<br/>spaCy NER + n-gram fuzzy match<br/>against names and aliases"]:::process
    L --> RD["Relation Detection<br/>synonym matching in question"]:::process
    RD --> M{"How many entities<br/>matched?"}:::check

    M -->|"none"| P0["no_entities<br/>safe rejection"]:::reject
    M -->|"two or more"| P1["connection<br/>shortest paths up to 4 hops"]:::pattern
    M -->|"one"| K{"Relations<br/>detected?"}:::check

    K -->|"two or more"| P2["chained<br/>X to Y to Z, both orders"]:::pattern
    K -->|"one"| P3["relation<br/>1-hop either direction, then<br/>directed BFS to final edge"]:::pattern
    K -->|"none or no match"| P4["neighborhood<br/>2-hop exploration"]:::pattern

    P1 --> N{"Path<br/>found?"}:::check
    N -->|"no"| P5["no_path<br/>safe rejection"]:::reject
    N -->|"yes"| EV
    P2 --> EV["Rank paths<br/>assemble evidence per hop"]:::process
    P3 --> EV
    P4 --> EV

    EV --> CF["Confidence Scoring<br/>high, medium or low"]:::process
    CF --> LLM{"Gemini enabled<br/>and paths exist?"}:::check
    LLM -->|"no"| TA["Template Answer"]:::process
    LLM -->|"yes"| GA["Gemini Phrasing<br/>only facts from the paths"]:::ai
    GA --> GC{"Grounded and<br/>call succeeded?"}:::check
    GC -->|"yes"| OUT
    GC -->|"no"| TA
    TA --> OUT
    P0 --> OUT
    P5 --> OUT
    OUT(["QueryResponse<br/>answer, matched entities, reasoning steps,<br/>highlighted nodes and edges"]):::ok

    classDef start fill:#fde68a,stroke:#b45309,stroke-width:2px,color:#451a03
    classDef check fill:#bfdbfe,stroke:#1d4ed8,stroke-width:2px,color:#172554
    classDef deny fill:#fecaca,stroke:#b91c1c,stroke-width:2px,color:#450a0a
    classDef process fill:#c7d2fe,stroke:#4338ca,stroke-width:2px,color:#1e1b4b
    classDef pattern fill:#bbf7d0,stroke:#15803d,stroke-width:2px,color:#052e16
    classDef reject fill:#e5e7eb,stroke:#6b7280,stroke-width:2px,color:#1f2937
    classDef ai fill:#e9d5ff,stroke:#7e22ce,stroke-width:2px,color:#3b0764
    classDef ok fill:#a7f3d0,stroke:#047857,stroke-width:3px,color:#064e3b
```

### 7. Multi-Hop Query Sequence

The canonical example: *"Which cloud infrastructure is associated with the company Microsoft invested in?"*

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant Q as Query Panel
    participant R as Reasoner
    participant N as NetworkX Graph
    participant A as Answerer
    participant C as Graph Canvas

    rect rgb(254, 243, 199)
    Note over U,Q: Question
    U->>Q: Ask the question
    Q->>R: POST /api/query with graph_id
    end

    rect rgb(219, 234, 254)
    Note over R: Understanding
    R->>R: Link entity Microsoft
    R->>R: Detect relations invested_in and uses_infrastructure
    R->>R: Pattern chained
    end

    rect rgb(220, 252, 231)
    Note over R,N: Traversal
    R->>N: Out-edges of Microsoft with relation invested_in
    N-->>R: Microsoft to OpenAI
    R->>N: Out-edges of OpenAI with relation uses_infrastructure
    N-->>R: OpenAI to Azure
    R-->>A: Path with two hops and answer id Azure
    end

    rect rgb(243, 232, 255)
    Note over A,C: Answer
    A->>A: Attach source sentence and document to each hop
    A->>A: Confidence high when every hop has evidence
    A-->>Q: Answer text and reasoning steps
    Q->>C: Highlight path nodes and edges
    C-->>U: Highlighted route Microsoft, OpenAI, Azure
    end
```

### 8. Database Schema

SQLite stores every document and every built graph. Graph tables are keyed by `graph_id`, so many graphs can coexist. A graph references its source documents through a JSON list of ids.

```mermaid
erDiagram
    DOCUMENTS ||--o{ GRAPHS : "source of"
    GRAPHS ||--o{ ENTITIES : contains
    GRAPHS ||--o{ RELATIONSHIPS : contains
    ENTITIES ||--o{ RELATIONSHIPS : "source of"
    ENTITIES ||--o{ RELATIONSHIPS : "target of"
    RELATIONSHIPS ||--o{ EVIDENCE : "supported by"

    DOCUMENTS {
        string id PK
        string name
        string created_at
        json chunks_json "sentences per chunk"
        json mentions_json "entity mentions with counts"
        json triples_json "extracted triples"
        string method "rules, llm or mixed"
    }
    GRAPHS {
        string id PK "g_ plus SHA-1 of document ids"
        json document_ids_json
        json stats_json
        string created_at
    }
    ENTITIES {
        string graph_id PK
        string id PK
        string canonical_name
        string type "PERSON, ORG, TECHNOLOGY, PRODUCT, LOCATION, OTHER"
        json aliases_json
        int mention_count
    }
    RELATIONSHIPS {
        string graph_id PK
        string id PK
        string source_id FK
        string target_id FK
        string relation "for example invested_in"
        float confidence
    }
    EVIDENCE {
        string graph_id FK
        string relationship_id FK
        int position
        string document_id
        string document_name
        int chunk_index
        string sentence "exact source sentence"
    }
```

### 9. Deployment Pipeline

```mermaid
flowchart LR
    Dev["Developer<br/>git push"]:::dev --> GH["GitHub<br/>main branch"]:::git

    GH -->|"root: frontend"| V["Vercel<br/>npm install, vite build"]:::deploy
    GH -->|"root: backend"| RN["Render Web Service<br/>pip install, spaCy model,<br/>uvicorn"]:::backend

    V --> Live(["Live Frontend<br/>*.vercel.app"]):::live
    RN --> Api(["Live API<br/>*.onrender.com"]):::live

    Live -->|"REST calls<br/>VITE_API_URL"| Api
    Api -->|"CORS allows<br/>ALLOWED_ORIGINS"| Live
    Api --> DB[("SQLite<br/>kg.db")]:::data
    Api -.->|"optional"| Gem{{"Gemini API"}}:::ai
    Hc["Health check<br/>/api/health"]:::check -.-> Api

    classDef dev fill:#fde68a,stroke:#b45309,stroke-width:2px,color:#451a03
    classDef git fill:#e5e7eb,stroke:#374151,stroke-width:2px,color:#111827
    classDef deploy fill:#bfdbfe,stroke:#1d4ed8,stroke-width:2px,color:#172554
    classDef backend fill:#c7d2fe,stroke:#4338ca,stroke-width:2px,color:#1e1b4b
    classDef live fill:#bbf7d0,stroke:#15803d,stroke-width:3px,color:#052e16
    classDef data fill:#fbcfe8,stroke:#be185d,stroke-width:2px,color:#500724
    classDef ai fill:#e9d5ff,stroke:#7e22ce,stroke-width:2px,color:#3b0764
    classDef check fill:#fed7aa,stroke:#c2410c,stroke-width:2px,color:#431407
```

---

## Getting Started

### Option 1: Docker Compose (Recommended)

Run the entire stack (frontend, backend, SQLite, reverse proxy) with a single command.

```bash
# 1. Clone the repository
git clone https://github.com/sourabhvamdevan/GraphForge.git
cd GraphForge

# 2. (Optional) Add a Gemini API key
cp .env.example .env      # Windows: copy .env.example .env

# 3. Build and start the containers
docker-compose up --build
```

* **Frontend**: [http://localhost:5173](http://localhost:5173)
* **API Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

### Option 2: Local Development

#### Prerequisites

* **Python 3.10+** (tested on 3.11.9)
* **Node.js 18+** and **npm**

#### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env          # Windows: copy .env.example .env
uvicorn app.main:app --reload
```

The backend runs on `http://localhost:8000`.

#### 2. Frontend (new terminal)

```bash
cd frontend
npm install
cp .env.example .env          # Windows: copy .env.example .env
npm run dev
```

The frontend runs on `http://localhost:5173`.

---

## Supported Question Patterns

| Pattern | Example Question | Resolution Method |
|---|---|---|
| **Direct Lookup** | *"Who founded OpenAI?"* | One-hop relation match in either direction, then directed BFS to an edge of that relation |
| **Chained Multi-Hop** | *"Which cloud infrastructure is associated with the company Microsoft invested in?"* | `Entity A -> r1 -> Entity B -> r2 -> Entity C`, trying both relation orders |
| **Entity Connection** | *"How are Sam Altman and Microsoft connected?"* | Shortest paths over the undirected graph, up to 4 hops |
| **Exploratory Fallback** | *"Tell me about Nvidia"* | Two-hop neighborhood exploration, always low confidence |
| **Unknown Entity** | *"What did QuantumCorp acquire?"* | Safe rejection when no entity is found in the graph |

The canonical example resolves through `Microsoft -invested_in-> OpenAI -uses_infrastructure-> Azure`, with sentence-level attribution for each hop and path highlighting on the canvas.

---

## REST API Reference

Interactive OpenAPI documentation is available at `/docs`.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/documents` | Upload and process a PDF or TXT document (multipart) |
| `POST` | `/api/documents/sample` | Load and process the bundled AI ecosystem dataset |
| `GET` | `/api/documents` | List all processed documents |
| `POST` | `/api/graph/build` | Build a knowledge graph from selected document ids |
| `GET` | `/api/graph/{graph_id}` | Retrieve the full graph (entities, relationships, statistics) |
| `GET` | `/api/graph/{graph_id}/entity/{id}` | Inspect incoming and outgoing relationships of one entity |
| `GET` | `/api/graph/{graph_id}/search?q=` | Fuzzy entity search across canonical names and aliases |
| `GET` | `/api/graph/{graph_id}/export` | Export graph data as JSON |
| `POST` | `/api/query` | Run natural language multi-hop reasoning |
| `GET` | `/api/health` | Service status and LLM configuration check |

---

## Configuration Reference

### Backend (`backend/.env`)

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(empty)* | Optional. If omitted, the engine runs in deterministic rule-based mode |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model for relation extraction and answer phrasing |
| `DATABASE_URL` | `sqlite:///./kg.db` | SQLite database path |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed CORS origins |
| `MAX_UPLOAD_MB` | `10` | Maximum upload size |
| `MAX_PAGES` | `50` | Maximum PDF page count |

### Frontend (`frontend/.env`)

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000/api` | Base URL of the backend API |

---

## Testing

The test suite runs completely offline with the LLM layer mocked.

```bash
cd backend
pytest
```

To run the sample extraction benchmark:

```bash
python -m scripts.extract_sample
```

---

## Deployment

The project deploys as two independent services.

### Backend on Render (Web Service)

| Setting | Value |
|---|---|
| Root Directory | `backend` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt && python -m spacy download en_core_web_sm` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |

Add the variables from the [Configuration Reference](#configuration-reference) plus `PYTHON_VERSION=3.11.9`. Alternatively, use the included `render.yaml` as a Render Blueprint.

### Frontend on Vercel

1. Import the repository and set **Root Directory** to `frontend`.
2. Add `VITE_API_URL` with the value `https://<your-render-service>.onrender.com/api`.
3. Deploy, then set `ALLOWED_ORIGINS` on Render to the final Vercel URL (no trailing slash) and redeploy the backend.

Notes:

* Render's free tier sleeps after inactivity, so the first request can take 30 to 60 seconds.
* The SQLite file is not persistent on the free tier and may reset on redeploy.
* `VITE_API_URL` is baked in at build time, so redeploy the frontend after changing it.

---

## Implementation Highlights

* **Two-Stage Pipeline**: Extraction runs once per document at upload and is stored, so graphs can be rebuilt from any combination of documents without re-running NLP.
* **Deterministic Graph IDs**: The graph id is a hash of the sorted document ids, so the same inputs always rebuild the same graph.
* **Per-Chunk Fallback**: A failed Gemini call affects only one chunk, which is re-extracted with rules. The document records `rules`, `llm` or `mixed`.
* **Grounded LLM Output**: Extracted entities must match known mentions, and phrased answers are checked against the reasoning paths before they are shown.
* **Evidence Provenance**: Every relationship stores the exact source sentence, chunk and document it came from.
* **Rate Limit Handling**: Gemini calls use exponential backoff with jitter on HTTP 429.
* **In-Memory Graph Cache**: NetworkX graphs are cached after build, with SQLite as the source of truth.
* **Containerization**: Docker Compose with a Python backend image and a multi-stage frontend build served by Nginx.

---

## Project Structure

```text
backend/
  app/
    routers/       FastAPI route handlers (documents, graph, query)
    services/      Ingestion, NER, relation extraction, resolver, graph builder, reasoner, answerer, LLM client
    config.py      Pydantic settings
    db.py          SQLite schema, persistence and graph cache
    main.py        FastAPI entrypoint, CORS and startup
    models.py      Data models and response schemas
  data/            Controlled vocabularies, seed entities and sample dataset
  tests/           Pytest suite
  scripts/         Sample extraction benchmark
frontend/
  src/
    api/           Typed API client
    components/    GraphCanvas, QueryPanel, UploadPanel, NodeDetailPanel, SearchFilterBar
    lib/           Dagre layout, styling helpers, example questions
    types.ts       TypeScript types mirroring backend models
    App.tsx        Main application shell
  nginx.conf       Production Nginx configuration
docker-compose.yml Multi-container orchestration
render.yaml        Render backend blueprint
plan.md            System design and implementation specification
```

---

