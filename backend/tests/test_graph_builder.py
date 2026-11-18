from app.models import Entity, Evidence, Relationship
from app.services.graph_builder import DocumentInput, build_graph, merge_relationships, validate


def _ev(sentence, doc="d1"):
    return Evidence(document_id=doc, document_name=f"{doc}.txt", chunk_index=0, sentence=sentence)


def test_duplicate_edges_merge_evidence_and_max_confidence():
    rels = [
        Relationship(id="", source_id="a", target_id="b", relation="uses", confidence=0.5, evidence=[_ev("s1")]),
        Relationship(id="", source_id="a", target_id="b", relation="uses", confidence=0.8, evidence=[_ev("s2")]),
        Relationship(id="", source_id="a", target_id="b", relation="uses", confidence=0.5, evidence=[_ev("s1")]),
    ]
    merged = merge_relationships(rels)
    assert len(merged) == 1
    assert merged[0].confidence == 0.8
    assert [e.sentence for e in merged[0].evidence] == ["s1", "s2"]


def test_self_loops_and_dangling_removed():
    ents = [Entity(id="a", canonical_name="A", type="ORG"), Entity(id="b", canonical_name="B", type="ORG")]
    rels = [
        Relationship(id="1", source_id="a", target_id="a", relation="uses", confidence=0.5, evidence=[]),
        Relationship(id="2", source_id="a", target_id="zzz", relation="uses", confidence=0.5, evidence=[]),
        Relationship(id="3", source_id="a", target_id="b", relation="uses", confidence=0.5, evidence=[]),
    ]
    kept, loops, dangling = validate(ents, rels)
    assert [r.id for r in kept] == ["3"] and loops == 1 and dangling == 1


def test_build_graph_end_to_end():
    mentions = [{"text": "OpenAI", "type": "ORG", "count": 2}, {"text": "Open AI", "type": "ORG", "count": 1},
                {"text": "Microsoft", "type": "ORG", "count": 2}]
    triples = [
        {"subject": "Microsoft", "subject_type": "ORG", "relation": "invested_in", "object": "OpenAI",
         "object_type": "ORG", "sentence": "Microsoft invested in OpenAI.", "chunk_index": 0, "confidence": 0.5},
        {"subject": "Microsoft", "subject_type": "ORG", "relation": "invested_in", "object": "Open AI",
         "object_type": "ORG", "sentence": "Microsoft backed Open AI.", "chunk_index": 1, "confidence": 0.8},
        {"subject": "OpenAI", "subject_type": "ORG", "relation": "uses", "object": "Open AI",
         "object_type": "ORG", "sentence": "OpenAI uses Open AI.", "chunk_index": 1, "confidence": 0.5},
    ]
    graph, stats = build_graph("g1", [DocumentInput("d1", "d1.txt", mentions, triples)])
    assert stats.node_count == 2
    assert stats.edge_count == 1
    assert stats.removed_self_loops == 1
    assert stats.connected_components == 1
    rel = graph.relationships[0]
    assert rel.confidence == 0.8 and len(rel.evidence) == 2
