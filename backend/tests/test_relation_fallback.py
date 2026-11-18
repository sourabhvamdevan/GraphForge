from app.services.ingestion import chunk_sentences
from app.services.relation_extractor import RULE_CONFIDENCE, extract_document


def _triples(*sentences):
    ext = extract_document(chunk_sentences(list(sentences)), use_llm=False)
    return {(t.subject, t.relation, t.object) for t in ext.triples}, ext


def test_invested_in():
    triples, ext = _triples("Microsoft invested in OpenAI.")
    assert ("Microsoft", "invested_in", "OpenAI") in triples
    assert all(t.confidence == RULE_CONFIDENCE for t in ext.triples)
    assert ext.triples[0].sentence == "Microsoft invested in OpenAI."


def test_more_patterns():
    triples, _ = _triples(
        "OpenAI uses Azure infrastructure to train its models.",
        "Sam Altman is the CEO of OpenAI.",
        "Anthropic partnered with Amazon, which built AWS.",
        "AlphaFold was developed by Google DeepMind.",
    )
    assert ("OpenAI", "uses_infrastructure", "Azure") in triples
    assert ("Sam Altman", "works_at", "OpenAI") in triples
    assert ("Anthropic", "partnered_with", "Amazon") in triples
    assert ("Amazon", "developed", "AWS") in triples
    assert ("Google DeepMind", "developed", "AlphaFold") in triples
    # no relation should skip over the intermediate entity
    assert not any(s == "Anthropic" and o == "AWS" for s, _, o in triples)


def test_unmapped_verb_emits_nothing():
    triples, _ = _triples("Microsoft admired OpenAI.")
    assert triples == set()
