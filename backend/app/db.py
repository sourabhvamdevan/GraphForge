"""SQLite persistence plus an in-memory cache of NetworkX graphs."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

from app.config import settings
from app.models import Entity, Evidence, GraphData, GraphStats, Relationship
from app.services.graph_builder import to_networkx

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    chunks_json TEXT NOT NULL,
    mentions_json TEXT NOT NULL,
    triples_json TEXT NOT NULL,
    method TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS graphs (
    id TEXT PRIMARY KEY,
    document_ids_json TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
    graph_id TEXT NOT NULL,
    id TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    type TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    mention_count INTEGER NOT NULL,
    PRIMARY KEY (graph_id, id)
);
CREATE TABLE IF NOT EXISTS relationships (
    graph_id TEXT NOT NULL,
    id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    confidence REAL NOT NULL,
    PRIMARY KEY (graph_id, id)
);
CREATE TABLE IF NOT EXISTS evidence (
    graph_id TEXT NOT NULL,
    relationship_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    document_id TEXT NOT NULL,
    document_name TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    sentence TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_rel ON evidence (graph_id, relationship_id);
"""

_lock = threading.Lock()
_graph_cache: dict[str, tuple[GraphData, GraphStats, nx.MultiDiGraph]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    path = settings.db_path
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def clear_cache() -> None:
    _graph_cache.clear()


# ---------------------------------------------------------------- documents

def save_document(doc_id: str, name: str, chunks: list[list[str]], mentions: list[dict],
                  triples: list[dict], method: str) -> None:
    with _lock, connect() as conn:
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, name, _now(), json.dumps(chunks), json.dumps(mentions), json.dumps(triples), method),
        )


def list_documents() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT id, name, created_at FROM documents ORDER BY created_at DESC").fetchall()
    return [{"document_id": r["id"], "name": r["name"], "created_at": r["created_at"]} for r in rows]


def get_documents(ids: list[str]) -> list[dict]:
    if not ids:
        return []
    with connect() as conn:
        q = f"SELECT * FROM documents WHERE id IN ({','.join('?' * len(ids))})"
        rows = conn.execute(q, ids).fetchall()
    return [
        {"document_id": r["id"], "name": r["name"], "mentions": json.loads(r["mentions_json"]),
         "triples": json.loads(r["triples_json"])}
        for r in rows
    ]


# ---------------------------------------------------------------- graphs

def save_graph(graph: GraphData, stats: GraphStats, document_ids: list[str]) -> None:
    gid = graph.graph_id
    with _lock, connect() as conn:
        for table in ("entities", "relationships", "evidence"):
            conn.execute(f"DELETE FROM {table} WHERE graph_id = ?", (gid,))
        conn.execute("DELETE FROM graphs WHERE id = ?", (gid,))
        conn.execute("INSERT INTO graphs VALUES (?, ?, ?, ?)",
                     (gid, json.dumps(document_ids), stats.model_dump_json(), _now()))
        conn.executemany(
            "INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?)",
            [(gid, e.id, e.canonical_name, e.type, json.dumps(e.aliases), e.mention_count)
             for e in graph.entities],
        )
        conn.executemany(
            "INSERT INTO relationships VALUES (?, ?, ?, ?, ?, ?)",
            [(gid, r.id, r.source_id, r.target_id, r.relation, r.confidence) for r in graph.relationships],
        )
        conn.executemany(
            "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(gid, r.id, i, ev.document_id, ev.document_name, ev.chunk_index, ev.sentence)
             for r in graph.relationships for i, ev in enumerate(r.evidence)],
        )
    _graph_cache[gid] = (graph, stats, to_networkx(graph))


def _load_graph_from_db(graph_id: str) -> tuple[GraphData, GraphStats] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM graphs WHERE id = ?", (graph_id,)).fetchone()
        if row is None:
            return None
        ents = conn.execute("SELECT * FROM entities WHERE graph_id = ?", (graph_id,)).fetchall()
        rels = conn.execute("SELECT * FROM relationships WHERE graph_id = ? ORDER BY id", (graph_id,)).fetchall()
        evs = conn.execute("SELECT * FROM evidence WHERE graph_id = ? ORDER BY relationship_id, position",
                           (graph_id,)).fetchall()
    ev_map: dict[str, list[Evidence]] = {}
    for e in evs:
        ev_map.setdefault(e["relationship_id"], []).append(
            Evidence(document_id=e["document_id"], document_name=e["document_name"],
                     chunk_index=e["chunk_index"], sentence=e["sentence"]))
    entities = [Entity(id=e["id"], canonical_name=e["canonical_name"], type=e["type"],
                       aliases=json.loads(e["aliases_json"]), mention_count=e["mention_count"]) for e in ents]
    entities.sort(key=lambda e: (-e.mention_count, e.canonical_name))
    relationships = [Relationship(id=r["id"], source_id=r["source_id"], target_id=r["target_id"],
                                  relation=r["relation"], confidence=r["confidence"],
                                  evidence=ev_map.get(r["id"], [])) for r in rels]
    graph = GraphData(graph_id=graph_id, entities=entities, relationships=relationships)
    return graph, GraphStats.model_validate_json(row["stats_json"])


def get_graph(graph_id: str) -> tuple[GraphData, GraphStats, nx.MultiDiGraph] | None:
    """Cached graph; rebuilt from SQLite on first access after a restart."""
    if graph_id in _graph_cache:
        return _graph_cache[graph_id]
    loaded = _load_graph_from_db(graph_id)
    if loaded is None:
        return None
    graph, stats = loaded
    _graph_cache[graph_id] = (graph, stats, to_networkx(graph))
    return _graph_cache[graph_id]
