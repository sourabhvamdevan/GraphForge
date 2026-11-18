"""Paths -> answer text (plan 6.4-6.6). Never answers without a supporting path."""
from __future__ import annotations

import logging
import re

from rapidfuzz import fuzz

from app.config import settings
from app.models import QueryResponse, ReasoningStep, Relationship
from app.services import llm
from app.services.entity_extractor import get_nlp
from app.services.reasoner import ReasoningResult

log = logging.getLogger(__name__)

PHRASES = {
    "founded": "founded",
    "works_at": "works at",
    "invested_in": "invested in",
    "acquired": "acquired",
    "partnered_with": "partnered with",
    "uses": "uses",
    "uses_infrastructure": "uses infrastructure from",
    "developed": "developed",
    "located_in": "is located in",
    "competes_with": "competes with",
    "part_of": "is part of",
    "collaborates_with": "collaborates with",
    "related_to": "is related to",
}


def _name(res: ReasoningResult, eid: str) -> str:
    e = res.entities.get(eid)
    return e.canonical_name if e else eid


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def path_sentence(res: ReasoningResult, path: list[Relationship]) -> str:
    parts: list[str] = []
    for i, r in enumerate(path):
        s, t, ph = _name(res, r.source_id), _name(res, r.target_id), PHRASES.get(r.relation, r.relation)
        if i == 0:
            parts.append(f"{s} {ph} {t}")
        elif r.source_id == path[i - 1].target_id:
            parts.append(f", which {ph} {t}")
        else:
            parts.append(f", and {s} {ph} {t}")
    return "".join(parts) + "."


def template_answer(res: ReasoningResult) -> str:
    if res.pattern == "no_entities":
        return ("I couldn't match any entity in your question to the graph, so I can't answer it. "
                "Try naming a person, company or technology that appears in the documents.")
    if res.pattern == "no_path":
        a, b = res.matched[0].canonical_name, res.matched[1].canonical_name
        return f"I found no path between {a} and {b} within {res.max_len} hops in the graph."
    sentences = " ".join(path_sentence(res, p) for p in res.paths)
    if res.pattern in {"relation", "chained"}:
        lead = _join([_name(res, a) for a in res.answer_ids])
        return f"{lead}. {sentences}" if lead else sentences
    if res.pattern == "connection":
        a, b = res.matched[0].canonical_name, res.matched[1].canonical_name
        hops = len(res.paths[0])
        more = len(res.paths) - 1
        tail = f" I found {more} longer path{'s' if more != 1 else ''} as well." if more else ""
        return (f"{a} and {b} are connected in {hops} hop{'s' if hops != 1 else ''}: "
                f"{path_sentence(res, res.paths[0])}{tail}")
    # neighborhood fallback
    x = res.matched[0].canonical_name
    if not res.paths:
        return f"{x} is in the graph but has no relationships, so I can't answer this."
    if res.note == "no_relation_match":
        wanted = " or ".join(r.replace("_", " ") for r in res.relations)
        return (f"I found no '{wanted}' relationship for {x}, so I can't answer that directly. "
                f"Its closest connections are: {sentences}")
    return f"I couldn't identify a specific question pattern. Here are {x}'s closest connections: {sentences}"


def compute_confidence(res: ReasoningResult) -> str:
    if res.pattern in {"no_entities", "no_path", "neighborhood"} or not res.paths:
        return "low"
    for p in res.paths:
        if all(r.evidence for r in p) and sum(r.confidence for r in p) / len(p) >= 0.7:
            return "high"
    return "medium"


# ------------------------------------------------------------------ optional LLM phrasing

LLM_PROMPT = """Answer the question in one or two sentences using ONLY the facts below.
Do not mention any company, person, product or place that is not in the facts.
If the facts do not answer the question, say so.

Question: {question}

Facts (reasoning paths with source sentences):
{facts}

Answer:"""


def _llm_answer(res: ReasoningResult) -> str | None:
    facts = []
    for i, p in enumerate(res.paths, 1):
        for r in p:
            ev = r.evidence[0].sentence if r.evidence else "(no source sentence)"
            facts.append(f"[path {i}] {_name(res, r.source_id)} --{r.relation}--> {_name(res, r.target_id)}"
                         f"  | source: \"{ev}\"")
    try:
        text = llm.generate(LLM_PROMPT.format(question=res.question, facts="\n".join(facts))).strip()
    except llm.LLMError as exc:
        log.warning("LLM answer failed: %s", exc)
        return None
    return text if text and _grounded(text, res) else None


def _grounded(text: str, res: ReasoningResult) -> bool:
    """Reject the LLM answer if it names any entity that is not on the retrieved paths."""
    on_path = {n for p in res.paths for r in p for n in (r.source_id, r.target_id)}
    allowed = set()
    for eid in on_path:
        e = res.entities[eid]
        allowed.update(n.lower() for n in [e.canonical_name, *e.aliases])
    lower = text.lower()
    for eid, e in res.entities.items():
        if eid in on_path:
            continue
        for n in [e.canonical_name, *e.aliases]:
            if len(n) >= 3 and re.search(rf"\b{re.escape(n.lower())}\b", lower):
                if not any(n.lower() in a for a in allowed):
                    return False
    for ent in get_nlp()(text).ents:
        if ent.label_ in {"DATE", "CARDINAL", "ORDINAL", "PERCENT", "MONEY", "QUANTITY", "TIME"}:
            continue
        if not any(fuzz.partial_ratio(ent.text.lower(), a) >= 85 for a in allowed):
            return False
    return True


def answer(res: ReasoningResult) -> QueryResponse:
    text = template_answer(res)
    if settings.llm_enabled and res.paths and res.pattern not in {"no_entities", "no_path"}:
        text = _llm_answer(res) or text

    steps = [
        [ReasoningStep(source=_name(res, r.source_id), relation=r.relation, target=_name(res, r.target_id),
                       evidence=r.evidence[0] if r.evidence else None) for r in p]
        for p in res.paths
    ]
    node_ids: list[str] = []
    edge_ids: list[str] = []
    for p in res.paths:
        for r in p:
            for n in (r.source_id, r.target_id):
                if n not in node_ids:
                    node_ids.append(n)
            if r.id not in edge_ids:
                edge_ids.append(r.id)
    if not res.paths:
        node_ids = [e.id for e in res.matched]
    return QueryResponse(
        question=res.question,
        answer=text,
        matched_entities=[e.canonical_name for e in res.matched],
        paths=steps,
        highlighted_node_ids=node_ids,
        highlighted_edge_ids=edge_ids,
        confidence=compute_confidence(res),  # type: ignore[arg-type]
    )
