"""spaCy NER + EntityRuler (plan 5.2)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache

import spacy
from spacy.language import Language
from spacy.tokens import Doc, Span

from app.config import DATA_DIR

LABEL_MAP = {
    "PERSON": "PERSON",
    "ORG": "ORG",
    "GPE": "LOCATION",
    "LOC": "LOCATION",
    "LOCATION": "LOCATION",
    "PRODUCT": "PRODUCT",
    "TECHNOLOGY": "TECHNOLOGY",
}

STOPLIST = {
    "ceo", "cto", "cfo", "ai", "inc", "corp", "ltd", "llc", "co", "company", "the company",
    "today", "models", "the modern ai ecosystem", "researchers", "research", "firm", "startup",
}

ROLE_NOUNS = {
    "ceo", "cto", "cfo", "president", "chairman", "chairwoman", "founder", "co-founder",
    "cofounder", "engineer", "researcher", "scientist", "director", "executive", "head",
}


@dataclass
class Mention:
    text: str
    type: str
    start: int  # char offsets within the sentence
    end: int


@lru_cache(maxsize=1)
def get_nlp() -> Language:
    nlp = spacy.load("en_core_web_sm")
    tech_terms = json.loads((DATA_DIR / "tech_terms.json").read_text(encoding="utf-8"))
    seeds = json.loads((DATA_DIR / "entity_seeds.json").read_text(encoding="utf-8"))
    patterns = [{"label": "TECHNOLOGY", "pattern": t} for t in tech_terms]
    for label, terms in seeds.items():
        patterns += [{"label": label, "pattern": t} for t in terms]
    ruler = nlp.add_pipe("entity_ruler", before="ner", config={"overwrite_ents": True})
    ruler.add_patterns(patterns)
    return nlp


def clean_entity_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^(the|a|an)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(['’]s|['’])$", "", text)
    return text.strip(" .,;:!?\"'()[]")


def is_valid_entity(text: str) -> bool:
    if len(text) < 2 or text.isdigit():
        return False
    if text.lower() in STOPLIST:
        return False
    return any(c.isalpha() for c in text)


def _is_role_subject(span: Span) -> bool:
    """'X is the CEO of Y' -> X is a person, whatever NER said."""
    root = span.root
    if root.dep_ != "nsubj" or root.head.lemma_ != "be":
        return False
    return any(c.dep_ == "attr" and c.lemma_.lower() in ROLE_NOUNS for c in root.head.children)


def entities_in_doc(doc: Doc, known_surnames: set[str] | None = None) -> list[Mention]:
    """Typed, filtered mentions in a parsed sentence."""
    mentions: list[Mention] = []
    covered: set[int] = set()
    for ent in doc.ents:
        etype = LABEL_MAP.get(ent.label_)
        if etype is None:
            continue
        if etype in {"ORG", "LOCATION", "PRODUCT"} and ent.label_ not in {"TECHNOLOGY"} \
                and _is_role_subject(ent) and len(ent) >= 2 and all(t.is_title for t in ent):
            etype = "PERSON"
        text = clean_entity_text(ent.text)
        if not is_valid_entity(text):
            continue
        start = ent.start_char + ent.text.find(text) if text in ent.text else ent.start_char
        mentions.append(Mention(text=text, type=etype, start=start, end=start + len(text)))
        covered.update(range(ent.start, ent.end))
    # surname-only references to people already seen ("Altman" -> "Sam Altman")
    if known_surnames:
        for tok in doc:
            if tok.i in covered or tok.pos_ != "PROPN":
                continue
            if tok.text in known_surnames:
                mentions.append(Mention(text=tok.text, type="PERSON", start=tok.idx,
                                        end=tok.idx + len(tok.text)))
    mentions.sort(key=lambda m: m.start)
    return mentions


def person_surnames(mentions: list[Mention]) -> set[str]:
    out = set()
    for m in mentions:
        parts = m.text.split()
        if m.type == "PERSON" and len(parts) >= 2 and parts[-1][:1].isupper():
            out.add(parts[-1])
    return out
