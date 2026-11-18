"""Question -> entity linking -> pattern -> graph traversal (plan section 6)."""
from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import islice

import networkx as nx
from rapidfuzz import fuzz, process

from app.config import DATA_DIR
from app.models import Entity, GraphData, Relationship
from app.services.entity_extractor import clean_entity_text, get_nlp

DEFAULT_MAX_HOPS = 3
CONNECTION_MAX_LEN = 4
NEIGHBORHOOD_HOPS = 2
MAX_PATHS = 5
LINK_THRESHOLD = 85
CONNECTION_WORDS = re.compile(r"\b(relat\w*|connect\w*|link\w*|between|associat\w*|path)\b", re.I)


@dataclass
class ReasoningResult:
    question: str
    pattern: str  # relation | chained | connection | neighborhood | no_entities | no_path
    matched: list[Entity]
    paths: list[list[Relationship]]
    entities: dict[str, Entity]
    relations: list[str] = field(default_factory=list)
    answer_ids: list[str] = field(default_factory=list)
    note: str = ""
    max_len: int = DEFAULT_MAX_HOPS


# ------------------------------------------------------------------ question parsing

@lru_cache(maxsize=1)
def _synonyms() -> list[tuple[str, str]]:
    data = json.loads((DATA_DIR / "relation_synonyms.json").read_text(encoding="utf-8"))
    pairs = [(phrase.lower(), rel) for rel, phrases in data.items() for phrase in phrases]
    return sorted(pairs, key=lambda p: -len(p[0]))


def detect_relations(question: str) -> list[str]:
    """Relation types mentioned in the question, in order of appearance."""
    q = re.sub(r"[^\w\s-]", " ", question.lower())
    taken = [False] * len(q)
    found: list[tuple[int, str]] = []
    for phrase, rel in _synonyms():
        for m in re.finditer(rf"\b{re.escape(phrase)}\b", q):
            if any(taken[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            found.append((m.start(), rel))
    ordered: list[str] = []
    for _, rel in sorted(found):
        if rel not in ordered:
            ordered.append(rel)
    return ordered


def link_entities(question: str, graph: GraphData) -> list[Entity]:
    """spaCy NER + n-gram fuzzy matching against canonical names and aliases."""
    by_id = {e.id: e for e in graph.entities}
    names: dict[str, str] = {}
    for e in graph.entities:
        for n in [e.canonical_name, *e.aliases]:
            names.setdefault(n.lower(), e.id)
    if not names:
        return []
    choices = list(names.keys())
    doc = get_nlp()(question)

    spans: set[tuple[int, int]] = {(ent.start, ent.end) for ent in doc.ents}
    for n in range(1, 6):
        for i in range(len(doc) - n + 1):
            span = doc[i:i + n]
            if span[0].is_stop or span[0].is_punct or span[-1].is_stop or span[-1].is_punct:
                continue
            spans.add((i, i + n))

    matches = []
    for s, e in spans:
        text = clean_entity_text(doc[s:e].text).lower()
        if len(text) < 2:
            continue
        if text in names:
            matches.append((e - s, 100.0, s, e, names[text]))
            continue
        if len(text) < 4:
            continue
        best = process.extractOne(text, choices, scorer=fuzz.ratio, score_cutoff=LINK_THRESHOLD)
        if best:
            matches.append((e - s, best[1], s, e, names[best[0]]))

    matches.sort(key=lambda m: (-m[0], -m[1], m[2]))
    used_tokens: set[int] = set()
    chosen: list[tuple[int, str]] = []
    for _, _, s, e, eid in matches:
        if any(i in used_tokens for i in range(s, e)) or eid in {c[1] for c in chosen}:
            continue
        used_tokens.update(range(s, e))
        chosen.append((s, eid))
    return [by_id[eid] for _, eid in sorted(chosen)]


# ------------------------------------------------------------------ traversal helpers

def _rank(paths: list[list[Relationship]]) -> list[list[Relationship]]:
    unique: dict[tuple[str, ...], list[Relationship]] = {}
    for p in paths:
        unique.setdefault(tuple(r.id for r in p), p)
    ranked = sorted(unique.values(), key=lambda p: (len(p), -sum(r.confidence for r in p) / len(p)))
    return ranked[:MAX_PATHS]


def _out_edges(g: nx.MultiDiGraph, node: str, relation: str | None = None) -> list[Relationship]:
    rels = [d["rel"] for _, _, d in g.out_edges(node, data=True)]
    return [r for r in rels if relation is None or r.relation == relation]


def _in_edges(g: nx.MultiDiGraph, node: str, relation: str | None = None) -> list[Relationship]:
    rels = [d["rel"] for _, _, d in g.in_edges(node, data=True)]
    return [r for r in rels if relation is None or r.relation == relation]


def relation_lookup(g: nx.MultiDiGraph, start: str, relation: str, max_hops: int):
    """One-hop edges of `relation` in either direction; otherwise directed BFS for a path
    whose last edge has `relation`. Returns (paths, answer_ids)."""
    direct = [[r] for r in _out_edges(g, start, relation)] + [[r] for r in _in_edges(g, start, relation)]
    if direct:
        answers = [p[0].target_id if p[0].source_id == start else p[0].source_id for p in direct]
        return direct, answers
    found: list[list[Relationship]] = []
    queue = deque([(start, [], {start})])
    while queue and len(found) < 50:
        node, edges, visited = queue.popleft()
        if len(edges) >= max_hops:
            continue
        for r in _out_edges(g, node):
            if r.target_id in visited:
                continue
            path = edges + [r]
            if r.relation == relation:
                found.append(path)
            queue.append((r.target_id, path, visited | {r.target_id}))
    return found, [p[-1].target_id for p in found]


def chained_lookup(g: nx.MultiDiGraph, start: str, rels: list[str]):
    """X -r1-> Y -r2-> Z, trying both relation orders."""
    paths: list[list[Relationship]] = []
    orders = [(rels[-1], rels[0]), (rels[0], rels[-1])] if len(rels) >= 2 else []
    for r1, r2 in orders:
        for e1 in _out_edges(g, start, r1):
            for e2 in _out_edges(g, e1.target_id, r2):
                if e2.target_id != start:
                    paths.append([e1, e2])
        if paths:
            break
    return paths, [p[-1].target_id for p in paths]


def _undirected_best(g: nx.MultiDiGraph) -> nx.Graph:
    h = nx.Graph()
    h.add_nodes_from(g.nodes)
    for u, v, d in g.edges(data=True):
        r: Relationship = d["rel"]
        if h.has_edge(u, v) and h[u][v]["rel"].confidence >= r.confidence:
            continue
        h.add_edge(u, v, rel=r)
    return h


def connection_paths(g: nx.MultiDiGraph, a: str, b: str, max_len: int) -> list[list[Relationship]]:
    h = _undirected_best(g)
    if a not in h or b not in h:
        return []
    paths = []
    try:
        for nodes in islice(nx.shortest_simple_paths(h, a, b), 4):  # shortest + up to 3 more
            if len(nodes) - 1 > max_len:
                break
            paths.append([h[u][v]["rel"] for u, v in zip(nodes, nodes[1:])])
    except nx.NetworkXNoPath:
        return []
    return paths


def neighborhood_paths(g: nx.MultiDiGraph, start: str, hops: int = NEIGHBORHOOD_HOPS):
    h = _undirected_best(g)
    if start not in h:
        return []
    found: list[list[Relationship]] = []
    queue = deque([(start, [], {start})])
    while queue:
        node, edges, visited = queue.popleft()
        if len(edges) >= hops:
            continue
        for nbr in h.neighbors(node):
            if nbr in visited:
                continue
            path = edges + [h[node][nbr]["rel"]]
            found.append(path)
            queue.append((nbr, path, visited | {nbr}))
    return found


# ------------------------------------------------------------------ entry point

def reason(question: str, graph: GraphData, g: nx.MultiDiGraph, max_hops: int = DEFAULT_MAX_HOPS,
           explicit_max_hops: bool = False) -> ReasoningResult:
    entities = {e.id: e for e in graph.entities}
    matched = link_entities(question, graph)
    rels = detect_relations(question)
    res = ReasoningResult(question=question, pattern="no_entities", matched=matched, paths=[],
                          entities=entities, relations=rels, max_len=max_hops)
    if not matched:
        return res

    if len(matched) >= 2:
        a, b = matched[0].id, matched[1].id
        limit = min(CONNECTION_MAX_LEN, max_hops) if explicit_max_hops else CONNECTION_MAX_LEN
        res.max_len = limit
        paths = connection_paths(g, a, b, limit)
        res.pattern = "connection" if paths else "no_path"
        res.paths = _rank(paths)
        return res

    x = matched[0].id
    if len(rels) >= 2:
        paths, answers = chained_lookup(g, x, rels)
        if paths:
            res.pattern, res.paths = "chained", _rank(paths)
            res.answer_ids = _answers_in(res.paths, answers)
            return res
    for rel in rels:
        paths, answers = relation_lookup(g, x, rel, max_hops)
        if paths:
            res.pattern, res.paths, res.relations = "relation", _rank(paths), [rel]
            res.answer_ids = _answers_in(res.paths, answers)
            return res

    if rels and not CONNECTION_WORDS.search(question):
        res.note = "no_relation_match"
    res.pattern = "neighborhood"
    res.paths = _rank(neighborhood_paths(g, x))
    return res


def _answers_in(paths: list[list[Relationship]], answers: list[str]) -> list[str]:
    ids_in_paths = {n for p in paths for r in p for n in (r.source_id, r.target_id)}
    out: list[str] = []
    for a in answers:
        if a in ids_in_paths and a not in out:
            out.append(a)
    return out
