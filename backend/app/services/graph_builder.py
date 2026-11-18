"""Build and validate the NetworkX graph (plan 5.5)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import networkx as nx

from app.models import Entity, Evidence, GraphData, GraphStats, Relationship
from app.services.resolver import resolve

log = logging.getLogger(__name__)


@dataclass
class DocumentInput:
    document_id: str
    name: str
    mentions: list[dict]
    triples: list[dict]


def relationship_id(source_id: str, relation: str, target_id: str) -> str:
    return f"{source_id}--{relation}--{target_id}"


def merge_relationships(rels: list[Relationship]) -> list[Relationship]:
    """Merge duplicate (source, relation, target): union evidence, max confidence."""
    merged: dict[str, Relationship] = {}
    for r in rels:
        rid = relationship_id(r.source_id, r.relation, r.target_id)
        if rid not in merged:
            merged[rid] = Relationship(id=rid, source_id=r.source_id, target_id=r.target_id,
                                       relation=r.relation, confidence=r.confidence, evidence=[])
        m = merged[rid]
        m.confidence = max(m.confidence, r.confidence)
        seen = {(e.document_id, e.sentence) for e in m.evidence}
        for e in r.evidence:
            if (e.document_id, e.sentence) not in seen:
                m.evidence.append(e)
                seen.add((e.document_id, e.sentence))
    return list(merged.values())


def validate(entities: list[Entity], rels: list[Relationship]) -> tuple[list[Relationship], int, int]:
    """Drop self-loops and edges that reference missing nodes."""
    ids = {e.id for e in entities}
    kept, self_loops, dangling = [], 0, 0
    for r in rels:
        if r.source_id == r.target_id:
            self_loops += 1
        elif r.source_id not in ids or r.target_id not in ids:
            dangling += 1
        else:
            kept.append(r)
    if self_loops or dangling:
        log.info("graph validation removed %d self-loops and %d dangling edges", self_loops, dangling)
    return kept, self_loops, dangling


def to_networkx(graph: GraphData) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for e in graph.entities:
        g.add_node(e.id, entity=e)
    for r in graph.relationships:
        g.add_edge(r.source_id, r.target_id, key=r.id, rel=r)
    return g


def compute_stats(graph: GraphData, self_loops: int = 0, dangling: int = 0) -> GraphStats:
    g = to_networkx(graph)
    components = nx.number_weakly_connected_components(g) if g.number_of_nodes() else 0
    return GraphStats(node_count=g.number_of_nodes(), edge_count=len(graph.relationships),
                      connected_components=components, removed_self_loops=self_loops,
                      removed_dangling_edges=dangling)


def build_graph(graph_id: str, documents: list[DocumentInput]) -> tuple[GraphData, GraphStats]:
    resolution = resolve([m for d in documents for m in d.mentions])
    raw: list[Relationship] = []
    unresolved = 0
    for d in documents:
        for t in d.triples:
            s = resolution.entity_id(t["subject"], t.get("subject_type"))
            o = resolution.entity_id(t["object"], t.get("object_type"))
            if s is None or o is None:
                unresolved += 1
                s = s or f"missing:{t['subject']}"
                o = o or f"missing:{t['object']}"
            ev = Evidence(document_id=d.document_id, document_name=d.name,
                          chunk_index=t["chunk_index"], sentence=t["sentence"])
            raw.append(Relationship(id="", source_id=s, target_id=o, relation=t["relation"],
                                    confidence=t["confidence"], evidence=[ev]))
    merged = merge_relationships(raw)
    kept, self_loops, dangling = validate(resolution.entities, merged)
    kept.sort(key=lambda r: r.id)
    graph = GraphData(graph_id=graph_id, entities=resolution.entities, relationships=kept)
    return graph, compute_stats(graph, self_loops, dangling)
