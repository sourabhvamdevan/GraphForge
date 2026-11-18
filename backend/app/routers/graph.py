from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException, Query
from rapidfuzz import fuzz

from app import db
from app.models import BuildGraphRequest, Entity, EntityDetail, GraphData, GraphResponse
from app.services.graph_builder import DocumentInput, build_graph

router = APIRouter(prefix="/graph", tags=["graph"])


def _require_graph(graph_id: str):
    found = db.get_graph(graph_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Graph '{graph_id}' not found.")
    return found


@router.post("/build", response_model=GraphResponse)
def build(req: BuildGraphRequest) -> GraphResponse:
    ids = sorted(set(req.document_ids))
    if not ids:
        raise HTTPException(status_code=422, detail="Provide at least one document id.")
    docs = db.get_documents(ids)
    missing = set(ids) - {d["document_id"] for d in docs}
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown document ids: {', '.join(sorted(missing))}")
    graph_id = "g_" + hashlib.sha1(",".join(ids).encode()).hexdigest()[:12]
    graph, stats = build_graph(graph_id, [DocumentInput(**d) for d in docs])
    db.save_graph(graph, stats, ids)
    return GraphResponse(**graph.model_dump(), stats=stats)


@router.get("/{graph_id}", response_model=GraphResponse)
def get_graph(graph_id: str) -> GraphResponse:
    graph, stats, _ = _require_graph(graph_id)
    return GraphResponse(**graph.model_dump(), stats=stats)


@router.get("/{graph_id}/entity/{entity_id}", response_model=EntityDetail)
def entity_detail(graph_id: str, entity_id: str) -> EntityDetail:
    graph, _, _ = _require_graph(graph_id)
    by_id = {e.id: e for e in graph.entities}
    if entity_id not in by_id:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found.")
    outgoing = [r for r in graph.relationships if r.source_id == entity_id]
    incoming = [r for r in graph.relationships if r.target_id == entity_id]
    neighbor_ids = {r.target_id for r in outgoing} | {r.source_id for r in incoming}
    neighbors = [by_id[n] for n in sorted(neighbor_ids) if n in by_id]
    return EntityDetail(entity=by_id[entity_id], outgoing=outgoing, incoming=incoming, neighbors=neighbors)


@router.get("/{graph_id}/search", response_model=list[Entity])
def search(graph_id: str, q: str = Query(..., min_length=1), limit: int = 20) -> list[Entity]:
    graph, _, _ = _require_graph(graph_id)
    query = q.strip().lower()
    scored = []
    for e in graph.entities:
        names = [e.canonical_name] + e.aliases
        score = max(
            100 if query in n.lower() else fuzz.WRatio(query, n.lower())
            for n in names
        )
        if score >= 60:
            scored.append((score, e.mention_count, e))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [e for _, _, e in scored[:limit]]


@router.get("/{graph_id}/export", response_model=GraphData)
def export(graph_id: str) -> GraphData:
    graph, _, _ = _require_graph(graph_id)
    return graph
