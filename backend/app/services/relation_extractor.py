"""Relation extraction (plan 5.3): Gemini first, spaCy dependency rules as fallback."""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from functools import lru_cache

from rapidfuzz import fuzz
from spacy.tokens import Doc, Span, Token

from app.config import DATA_DIR, settings
from app.models import RELATION_TYPES
from app.services import llm
from app.services.entity_extractor import Mention, entities_in_doc, get_nlp, person_surnames
from app.services.ingestion import Chunk
from app.services.resolver import FUZZY_THRESHOLD, normalize_name

log = logging.getLogger(__name__)

RULE_CONFIDENCE = 0.5
LLM_CONFIDENCE = 0.8
LLM_CONCURRENCY = 3
MAX_PATH_LEN = 9


@dataclass
class Triple:
    subject: str
    subject_type: str
    relation: str
    object: str
    object_type: str
    sentence: str
    chunk_index: int
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DocumentExtraction:
    mentions: list[dict]   # [{text, type, count}]
    triples: list[Triple]
    method: str            # "rules" | "llm" | "mixed"


@lru_cache(maxsize=1)
def load_rules() -> dict:
    return json.loads((DATA_DIR / "verb_relations.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- rules

def _span(doc: Doc, m: Mention) -> Span | None:
    return doc.char_span(m.start, m.end, alignment_mode="expand")


def _effective_root(span: Span) -> Token:
    tok = span.root
    while tok.dep_ == "conj" and tok.head is not tok:
        tok = tok.head
    return tok


def _dep_path(a: Token, b: Token):
    chain_a = [a] + list(a.ancestors)
    chain_b = [b] + list(b.ancestors)
    pos_b = {t.i: k for k, t in enumerate(chain_b)}
    for k, t in enumerate(chain_a):
        if t.i in pos_b:
            up = chain_a[: k + 1]
            down = chain_b[: pos_b[t.i]]
            return up + list(reversed(down)), up[:-1], down
    return None, None, None


def _is_verb_like(tok: Token, rules: dict) -> bool:
    """VERB, or an inflected verb the small model tagged as NOUN ("Anthropic competes with ...")."""
    if tok.pos_ == "VERB":
        return True
    lemma = tok.lemma_.lower()
    return (tok.pos_ == "NOUN" and lemma in rules["verbs"] and lemma not in rules["nouns"]
            and tok.text.lower() != lemma)


def _relation_from_path(path: list[Token], rules: dict) -> str | None:
    interior = path[1:-1]
    for tok in interior:
        if not _is_verb_like(tok, rules):
            continue
        lemma = tok.lemma_.lower()
        if lemma not in rules["verbs"]:
            continue
        overrides = rules["prep_overrides"].get(lemma, {})
        preps = [c.text.lower() for c in tok.children if c.dep_ in {"prep", "prt", "agent"}]
        for p in preps:
            if p in overrides:
                return overrides[p]
        if lemma in rules["verbs_requiring_prep"]:
            continue
        return rules["verbs"][lemma]
    # role nouns ("CEO of", "part of") only in short, verb-free paths, so that
    # "investors such as X" in a long sentence does not link unrelated entities
    if len(path) > 6 or any(_is_verb_like(t, rules) for t in interior):
        return None
    for tok in interior:
        if tok.pos_ in {"NOUN", "PROPN"} and tok.lemma_.lower() in rules["nouns"]:
            return rules["nouns"][tok.lemma_.lower()]
    return None


def rule_triples_for_sentence(doc: Doc, mentions: list[Mention]) -> list[tuple[Mention, str, Mention]]:
    rules = load_rules()
    spans = [(m, _span(doc, m)) for m in mentions]
    spans = [(m, s) for m, s in spans if s is not None]
    out: list[tuple[Mention, str, Mention]] = []
    sentence_lower = doc.text.lower()
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            (m1, s1), (m2, s2) = spans[i], spans[j]
            if normalize_name(m1.text) == normalize_name(m2.text):
                continue
            r1, r2 = _effective_root(s1), _effective_root(s2)
            if r1.i == r2.i:
                continue
            path, chain1, chain2 = _dep_path(r1, r2)
            if not path or len(path) > MAX_PATH_LEN:
                continue
            # do not jump over another entity ("A partnered with B, which built C")
            own = set(range(s1.start, s1.end)) | set(range(s2.start, s2.end)) | {r1.i, r2.i}
            others = {t for m, s in spans if s is not s1 and s is not s2 for t in range(s.start, s.end)}
            if any(t.i in others and t.i not in own for t in path[1:-1]):
                continue
            relation = _relation_from_path(path, rules)
            if relation is None:
                continue
            subj, obj = m1, m2
            deps1 = {t.dep_ for t in chain1}
            deps2 = {t.dep_ for t in chain2}
            if "agent" in deps2 or ("agent" not in deps1 and "nsubj" in deps2 and "nsubj" not in deps1):
                subj, obj = m2, m1
            for rule in rules["keyword_overrides"]:
                if relation == rule["from"] and obj.type == "TECHNOLOGY" and any(
                    k in sentence_lower for k in rule["keywords"]
                ):
                    relation = rule["to"]
            if relation in rules["person_subject_relations"] and subj.type != "PERSON" and obj.type == "PERSON":
                subj, obj = obj, subj
            if relation == "works_at" and subj.type != "PERSON":
                continue
            if relation == "located_in" and obj.type != "LOCATION":
                continue
            out.append((subj, relation, obj))
    return out


# --------------------------------------------------------------------------- llm

PROMPT = """You extract knowledge-graph triples from text.

Allowed relations (use ONLY these): {relations}
"related_to" is a last resort; do not use it if a specific relation fits.

Rules:
- subject and object must be entities that appear in the text. Prefer names from the detected entity list.
- You may add technology entities (frameworks, cloud platforms, models, chips) that appear verbatim in the text
  but are missing from the list; list them in "new_entities" with type "TECHNOLOGY".
- "sentence" must be copied verbatim from the text, as one complete sentence.
- Only extract facts that are explicitly stated. Do not infer.
- If there are none, return {{"triples": [], "new_entities": []}}.

Return JSON only, in this shape:
{{"triples": [{{"subject": "...", "relation": "invested_in", "object": "...", "sentence": "..."}}],
  "new_entities": [{{"name": "...", "type": "TECHNOLOGY"}}]}}

Detected entities: {entities}

Text:
\"\"\"{text}\"\"\""""


def _match_mention(name: str, mentions: list[Mention]) -> Mention | None:
    norm = normalize_name(name)
    if not norm:
        return None
    best, best_score = None, 0.0
    for m in mentions:
        mn = normalize_name(m.text)
        if mn == norm or mn.replace(" ", "") == norm.replace(" ", ""):
            return m
        score = fuzz.token_sort_ratio(mn, norm)
        if score >= FUZZY_THRESHOLD and score > best_score:
            best, best_score = m, score
    return best


def _sentence_in_chunk(sentence: str, chunk: Chunk) -> str | None:
    s = " ".join(sentence.split())
    if not s or s not in " ".join(chunk.text.split()):
        return None
    for cs in chunk.sentences:
        if s in " ".join(cs.split()):
            return cs
    return s


def llm_triples_for_chunk(chunk: Chunk, mentions: list[Mention]) -> tuple[list[Triple], list[Mention]]:
    """Raises llm.LLMError or ValueError when the model output cannot be used."""
    ent_list = sorted({f"{m.text} ({m.type})" for m in mentions})
    prompt = PROMPT.format(relations=", ".join(RELATION_TYPES), entities="; ".join(ent_list) or "none",
                           text=chunk.text)
    data = None
    for _attempt in range(2):  # one retry on JSON parse failure
        try:
            data = llm.parse_json(llm.generate(prompt, json_mode=True))
            break
        except (json.JSONDecodeError, ValueError):
            continue
    if not isinstance(data, dict):
        raise ValueError("unparseable LLM output")

    new_mentions: list[Mention] = []
    for ne in data.get("new_entities", []) or []:
        name = str(ne.get("name", "")).strip()
        if name and name in chunk.text and ne.get("type") == "TECHNOLOGY":
            new_mentions.append(Mention(text=name, type="TECHNOLOGY", start=0, end=len(name)))
    pool = mentions + new_mentions

    triples: list[Triple] = []
    for t in data.get("triples", []) or []:
        rel = str(t.get("relation", "")).strip()
        if rel not in RELATION_TYPES:
            continue
        sentence = _sentence_in_chunk(str(t.get("sentence", "")), chunk)
        if sentence is None:
            continue
        s = _match_mention(str(t.get("subject", "")), pool)
        o = _match_mention(str(t.get("object", "")), pool)
        if s is None or o is None or normalize_name(s.text) == normalize_name(o.text):
            continue
        triples.append(Triple(s.text, s.type, rel, o.text, o.type, sentence, chunk.index, LLM_CONFIDENCE))
    return triples, new_mentions


# --------------------------------------------------------------------------- document

def extract_document(chunks: list[Chunk], use_llm: bool | None = None) -> DocumentExtraction:
    """Entities + relations for every chunk of a document."""
    use_llm = settings.llm_enabled if use_llm is None else use_llm
    nlp = get_nlp()

    # each unique sentence is parsed once and owned by the first chunk containing it
    owner: dict[str, int] = {}
    for ch in chunks:
        for s in ch.sentences:
            owner.setdefault(s, ch.index)
    unique = list(owner.keys())
    docs = dict(zip(unique, nlp.pipe(unique)))

    first_pass = [m for d in docs.values() for m in entities_in_doc(d)]
    surnames = person_surnames(first_pass)
    sent_mentions = {s: entities_in_doc(d, surnames) for s, d in docs.items()}

    counts: dict[tuple[str, str], int] = {}
    for ms in sent_mentions.values():
        for m in ms:
            counts[(m.text, m.type)] = counts.get((m.text, m.type), 0) + 1

    def rules_for_chunk(ch: Chunk) -> list[Triple]:
        out = []
        for s in ch.sentences:
            if owner[s] != ch.index:
                continue
            for subj, rel, obj in rule_triples_for_sentence(docs[s], sent_mentions[s]):
                out.append(Triple(subj.text, subj.type, rel, obj.text, obj.type, s, ch.index, RULE_CONFIDENCE))
        return out

    triples: list[Triple] = []
    methods = set()
    if use_llm:
        def work(ch: Chunk):
            ms = [m for s in ch.sentences for m in sent_mentions[s]]
            try:
                return ch, llm_triples_for_chunk(ch, ms), None
            except Exception as exc:  # noqa: BLE001
                return ch, None, exc

        with ThreadPoolExecutor(max_workers=LLM_CONCURRENCY) as pool:
            for ch, result, err in pool.map(work, chunks):
                if result is None:
                    log.warning("LLM extraction failed for chunk %s (%s); using rules", ch.index, err)
                    triples += rules_for_chunk(ch)
                    methods.add("rules")
                    continue
                llm_triples, new_mentions = result
                triples += llm_triples
                methods.add("llm")
                for m in new_mentions:
                    counts[(m.text, m.type)] = counts.get((m.text, m.type), 0) + 1
    else:
        for ch in chunks:
            triples += rules_for_chunk(ch)
        methods.add("rules")

    mentions = [{"text": t, "type": ty, "count": c} for (t, ty), c in counts.items()]
    method = methods.pop() if len(methods) == 1 else "mixed"
    return DocumentExtraction(mentions=mentions, triples=triples, method=method)
