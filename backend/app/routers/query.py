from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import db
from app.models import QueryRequest, QueryResponse
from app.services.answerer import answer
from app.services.reasoner import DEFAULT_MAX_HOPS, reason

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    found = db.get_graph(req.graph_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Graph '{req.graph_id}' not found.")
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="Question is empty.")
    graph, _, nxg = found
    result = reason(req.question, graph, nxg, max_hops=req.max_hops or DEFAULT_MAX_HOPS,
                    explicit_max_hops=req.max_hops is not None)
    return answer(result)
