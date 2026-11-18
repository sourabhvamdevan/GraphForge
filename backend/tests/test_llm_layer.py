"""Gemini layer validation, with the model mocked (no network, no key)."""
import json

from app.config import settings
from app.models import Entity, Evidence, GraphData, Relationship
from app.services import llm, relation_extractor
from app.services.answerer import answer
from app.services.entity_extractor import Mention
from app.services.graph_builder import relationship_id, to_networkx
from app.services.ingestion import Chunk, chunk_sentences
from app.services.reasoner import reason

CHUNK = Chunk(index=0, sentences=["Microsoft invested in OpenAI.", "OpenAI trains models with PyTorch."])
MENTIONS = [Mention("Microsoft", "ORG", 0, 9), Mention("OpenAI", "ORG", 0, 6)]


def test_llm_triples_are_validated(monkeypatch):
    payload = {
        "triples": [
            {"subject": "Microsoft Corp", "relation": "invested_in", "object": "OpenAI",
             "sentence": "Microsoft invested in OpenAI."},                      # ok (fuzzy subject)
            {"subject": "OpenAI", "relation": "uses", "object": "PyTorch",
             "sentence": "OpenAI trains models with PyTorch."},                 # ok via new entity
            {"subject": "Microsoft", "relation": "loves", "object": "OpenAI",
             "sentence": "Microsoft invested in OpenAI."},                      # bad relation
            {"subject": "Microsoft", "relation": "acquired", "object": "OpenAI",
             "sentence": "Microsoft acquired OpenAI."},                         # sentence not in chunk
            {"subject": "Google", "relation": "invested_in", "object": "OpenAI",
             "sentence": "Microsoft invested in OpenAI."},                      # unknown subject
        ],
        "new_entities": [{"name": "PyTorch", "type": "TECHNOLOGY"}, {"name": "Rust", "type": "TECHNOLOGY"}],
    }
    monkeypatch.setattr(llm, "generate", lambda *a, **k: "```json\n" + json.dumps(payload) + "\n```")
    triples, new = relation_extractor.llm_triples_for_chunk(CHUNK, MENTIONS)
    got = {(t.subject, t.relation, t.object) for t in triples}
    assert got == {("Microsoft", "invested_in", "OpenAI"), ("OpenAI", "uses", "PyTorch")}
    assert all(t.confidence == relation_extractor.LLM_CONFIDENCE for t in triples)
    assert [m.text for m in new] == ["PyTorch"]  # "Rust" is not in the chunk


def test_llm_failure_falls_back_to_rules(monkeypatch):
    calls = {"n": 0}

    def broken(*a, **k):
        calls["n"] += 1
        return "not json at all"

    monkeypatch.setattr(llm, "generate", broken)
    ext = relation_extractor.extract_document(chunk_sentences(["Microsoft invested in OpenAI."]), use_llm=True)
    assert calls["n"] == 2  # one retry
    assert {(t.subject, t.relation, t.object) for t in ext.triples} == {("Microsoft", "invested_in", "OpenAI")}
    assert ext.method == "rules"


def _graph():
    ev = lambda s: [Evidence(document_id="d", document_name="d.txt", chunk_index=0, sentence=s)]  # noqa: E731
    ents = [Entity(id="microsoft", canonical_name="Microsoft", type="ORG"),
            Entity(id="openai", canonical_name="OpenAI", type="ORG"),
            Entity(id="azure", canonical_name="Azure", type="TECHNOLOGY"),
            Entity(id="google", canonical_name="Google", type="ORG")]
    rels = [Relationship(id=relationship_id("microsoft", "invested_in", "openai"), source_id="microsoft",
                         target_id="openai", relation="invested_in", confidence=0.8,
                         evidence=ev("Microsoft invested in OpenAI.")),
            Relationship(id=relationship_id("openai", "uses_infrastructure", "azure"), source_id="openai",
                         target_id="azure", relation="uses_infrastructure", confidence=0.8,
                         evidence=ev("OpenAI uses Azure infrastructure."))]
    g = GraphData(graph_id="g", entities=ents, relationships=rels)
    return g, to_networkx(g)


Q = "Which cloud infrastructure is associated with the company Microsoft invested in?"


def test_llm_answer_used_when_grounded(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(llm, "generate", lambda *a, **k: "Azure, since Microsoft backs OpenAI, which runs on Azure.")
    g, nxg = _graph()
    resp = answer(reason(Q, g, nxg))
    assert resp.answer.startswith("Azure, since")
    assert resp.confidence == "high"


def test_llm_answer_with_foreign_entity_discarded(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(llm, "generate", lambda *a, **k: "Azure, and Google Cloud as a backup.")
    g, nxg = _graph()
    resp = answer(reason(Q, g, nxg))
    assert resp.answer == "Azure. Microsoft invested in OpenAI, which uses infrastructure from Azure."
