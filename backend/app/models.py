"""Pydantic schemas (plan section 4). Mirrored in frontend/src/types.ts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EntityType = Literal["PERSON", "ORG", "TECHNOLOGY", "PRODUCT", "LOCATION", "OTHER"]

RELATION_TYPES = [
    "founded", "works_at", "invested_in", "acquired", "partnered_with",
    "uses", "uses_infrastructure", "developed", "located_in",
    "competes_with", "part_of", "collaborates_with", "related_to",
]


class Entity(BaseModel):
    id: str
    canonical_name: str
    type: EntityType
    aliases: list[str] = Field(default_factory=list)
    mention_count: int = 1


class Evidence(BaseModel):
    document_id: str
    document_name: str
    chunk_index: int
    sentence: str


class Relationship(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation: str
    confidence: float
    evidence: list[Evidence]


class GraphData(BaseModel):
    graph_id: str
    entities: list[Entity]
    relationships: list[Relationship]


class ReasoningStep(BaseModel):
    source: str
    relation: str
    target: str
    evidence: Evidence | None


class QueryResponse(BaseModel):
    question: str
    answer: str
    matched_entities: list[str]
    paths: list[list[ReasoningStep]]
    highlighted_node_ids: list[str]
    highlighted_edge_ids: list[str]
    confidence: Literal["high", "medium", "low"]


# ---- API helper schemas ----

class GraphStats(BaseModel):
    node_count: int
    edge_count: int
    connected_components: int
    removed_self_loops: int = 0
    removed_dangling_edges: int = 0


class GraphResponse(GraphData):
    stats: GraphStats


class DocumentUploadResponse(BaseModel):
    document_id: str
    name: str
    chunks: int
    status: str


class DocumentSummary(BaseModel):
    document_id: str
    name: str
    created_at: str


class BuildGraphRequest(BaseModel):
    document_ids: list[str]


class EntityDetail(BaseModel):
    entity: Entity
    outgoing: list[Relationship]
    incoming: list[Relationship]
    neighbors: list[Entity]


class QueryRequest(BaseModel):
    graph_id: str
    question: str
    max_hops: int | None = Field(default=None, ge=1, le=6)


class HealthResponse(BaseModel):
    status: str
    llm_enabled: bool
