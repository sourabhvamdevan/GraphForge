import pytest

from app.models import Entity, Evidence, GraphData, Relationship
from app.services.answerer import answer
from app.services.graph_builder import relationship_id, to_networkx
from app.services.reasoner import detect_relations, reason

CANONICAL = "Which cloud infrastructure is associated with the company Microsoft invested in?"


def _rel(s, r, t, conf=0.5):
    ev = Evidence(document_id="d", document_name="d.txt", chunk_index=0, sentence=f"{s} {r} {t}.")
    return Relationship(id=relationship_id(s, r, t), source_id=s, target_id=t, relation=r,
                        confidence=conf, evidence=[ev])


@pytest.fixture()
def graph():
    ents = [
        Entity(id="microsoft", canonical_name="Microsoft", type="ORG"),
        Entity(id="openai", canonical_name="OpenAI", type="ORG"),
        Entity(id="azure", canonical_name="Azure", type="TECHNOLOGY"),
        Entity(id="sam-altman", canonical_name="Sam Altman", type="PERSON", aliases=["Altman"]),
        Entity(id="anthropic", canonical_name="Anthropic", type="ORG"),
        Entity(id="amazon", canonical_name="Amazon", type="ORG"),
        Entity(id="aws", canonical_name="AWS", type="TECHNOLOGY"),
        Entity(id="isolated", canonical_name="Lonely Labs", type="ORG"),
    ]
    rels = [
        _rel("microsoft", "invested_in", "openai"),
        _rel("openai", "uses_infrastructure", "azure"),
        _rel("microsoft", "developed", "azure"),
        _rel("sam-altman", "works_at", "openai", 0.8),
        _rel("amazon", "invested_in", "anthropic"),
        _rel("anthropic", "uses_infrastructure", "aws"),
        _rel("anthropic", "competes_with", "openai"),
    ]
    g = GraphData(graph_id="g", entities=ents, relationships=rels)
    return g, to_networkx(g)


def _ask(graph, q, **kw):
    g, nxg = graph
    return answer(reason(q, g, nxg, **kw))


def test_canonical_question(graph):
    resp = _ask(graph, CANONICAL)
    assert resp.answer.startswith("Azure")
    assert resp.matched_entities == ["Microsoft"]
    assert len(resp.paths) == 1 and len(resp.paths[0]) == 2
    s1, s2 = resp.paths[0]
    assert (s1.source, s1.relation, s1.target) == ("Microsoft", "invested_in", "OpenAI")
    assert (s2.source, s2.relation, s2.target) == ("OpenAI", "uses_infrastructure", "Azure")
    assert s1.evidence and s2.evidence
    assert set(resp.highlighted_node_ids) == {"microsoft", "openai", "azure"}
    assert len(resp.highlighted_edge_ids) == 2
    assert resp.confidence == "medium"  # rule-based confidence 0.5 < 0.7


def test_unknown_entity_is_low(graph):
    resp = _ask(graph, "What did Zorblax Industries acquire?")
    assert resp.confidence == "low"
    assert resp.paths == [] and resp.matched_entities == []


def test_alias_and_one_hop(graph):
    resp = _ask(graph, "Where does Altman work?")
    assert resp.matched_entities == ["Sam Altman"]
    assert resp.answer.startswith("OpenAI")
    assert resp.confidence == "high"  # 0.8 with evidence


def test_incoming_relation(graph):
    resp = _ask(graph, "Who invested in Anthropic?")
    assert resp.answer.startswith("Amazon")


def test_connection(graph):
    resp = _ask(graph, "How are Sam Altman and Amazon connected?")
    assert resp.paths
    assert len(resp.paths[0]) <= 4
    names = {s.source for s in resp.paths[0]} | {s.target for s in resp.paths[0]}
    assert {"Sam Altman", "Amazon"} <= names


def test_no_path_is_explicit(graph):
    resp = _ask(graph, "How are Lonely Labs and Microsoft connected?")
    assert resp.confidence == "low"
    assert "no path" in resp.answer.lower()
    assert resp.paths == []


def test_neighborhood_fallback_is_low(graph):
    resp = _ask(graph, "Tell me about OpenAI")
    assert resp.confidence == "low" and resp.paths


def test_detect_relations():
    assert detect_relations(CANONICAL) == ["uses_infrastructure", "invested_in"]
    assert detect_relations("Who backed OpenAI?") == ["invested_in"]
