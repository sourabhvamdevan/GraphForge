from app.services.resolver import normalize_name, resolve


def _ids(res, *names_types):
    return [res.entity_id(n, t) for n, t in names_types]


def test_openai_variants_merge():
    res = resolve([
        {"text": "OpenAI", "type": "ORG", "count": 3},
        {"text": "OpenAI Inc.", "type": "ORG", "count": 1},
        {"text": "Open AI", "type": "ORG", "count": 1},
    ])
    assert len(res.entities) == 1
    ids = _ids(res, ("OpenAI", "ORG"), ("OpenAI Inc.", "ORG"), ("Open AI", "ORG"))
    assert len(set(ids)) == 1 and ids[0] is not None
    e = res.entities[0]
    assert e.mention_count == 5
    assert set(e.aliases) | {e.canonical_name} == {"OpenAI", "OpenAI Inc.", "Open AI"}


def test_apple_org_and_other_do_not_merge():
    res = resolve([
        {"text": "Apple", "type": "ORG", "count": 1},
        {"text": "apple", "type": "OTHER", "count": 1},
    ])
    assert len(res.entities) == 2
    assert {e.type for e in res.entities} == {"ORG", "OTHER"}
    assert len({e.id for e in res.entities}) == 2


def test_person_surname_alias():
    res = resolve([
        {"text": "Sam Altman", "type": "PERSON", "count": 1},
        {"text": "Altman", "type": "PERSON", "count": 2},
    ])
    assert len(res.entities) == 1
    e = res.entities[0]
    assert e.canonical_name == "Sam Altman" and e.aliases == ["Altman"]


def test_org_token_subset_not_merged():
    res = resolve([
        {"text": "Google", "type": "ORG", "count": 1},
        {"text": "Google DeepMind", "type": "ORG", "count": 1},
    ])
    assert len(res.entities) == 2


def test_normalize_strips_suffixes():
    assert normalize_name("Acme Corp.") == "acme"
    assert normalize_name("Widgets, Inc") == "widgets"
