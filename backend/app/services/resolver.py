"""Deterministic entity resolution (plan 5.4)."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from rapidfuzz import fuzz

from app.models import Entity

FUZZY_THRESHOLD = 90
CORPORATE_SUFFIXES = {"inc", "corp", "corporation", "ltd", "llc", "co", "plc", "gmbh"}


def normalize_name(name: str) -> str:
    s = name.lower().replace("&", " and ")
    s = re.sub(r"['’]s\b", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    tokens = [t for t in s.split() if t]
    while tokens and tokens[-1] in CORPORATE_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "entity"


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def _should_merge(a: str, b: str, etype: str) -> bool:
    if a == b or a.replace(" ", "") == b.replace(" ", ""):
        return True
    ta, tb = set(a.split()), set(b.split())
    # token-subset merge only for people ("Altman" / "Sam Altman"); for orgs it would
    # wrongly fold "Google DeepMind" into "Google".
    if etype == "PERSON" and ta and tb and (ta <= tb or tb <= ta):
        return True
    if min(len(a), len(b)) >= 4 and fuzz.token_sort_ratio(a, b) >= FUZZY_THRESHOLD:
        return True
    return False


class Resolution:
    """Result of resolving mentions: entities plus a surface-name lookup."""

    def __init__(self, entities: list[Entity], lookup: dict[tuple[str, str], str],
                 type_of: dict[str, str]):
        self.entities = entities
        self._lookup = lookup      # (normalized name, type) -> entity id
        self._type_of = type_of    # normalized name -> voted type

    def entity_id(self, surface: str, etype: str | None = None) -> str | None:
        norm = normalize_name(surface)
        voted = self._type_of.get(norm, etype)
        for t in (voted, etype):
            if t and (norm, t) in self._lookup:
                return self._lookup[(norm, t)]
        return None


def resolve(mentions: list[dict]) -> Resolution:
    """mentions: [{text, type, count}] possibly from many documents."""
    # 1. vote a single type per normalized name (spaCy often flips ORG/GPE/PERSON for
    #    the same surface form). OTHER never takes part in voting.
    votes: dict[str, Counter] = defaultdict(Counter)
    for m in mentions:
        norm = normalize_name(m["text"])
        if norm and m["type"] != "OTHER":
            votes[norm][m["type"]] += m.get("count", 1)
    type_of = {n: c.most_common(1)[0][0] for n, c in votes.items()}

    # 2. group by (normalized, type)
    groups: dict[tuple[str, str], dict] = {}
    for m in mentions:
        norm = normalize_name(m["text"])
        if not norm:
            continue
        etype = m["type"] if m["type"] == "OTHER" else type_of.get(norm, m["type"])
        g = groups.setdefault((norm, etype), {"surfaces": Counter(), "count": 0})
        g["surfaces"][m["text"]] += m.get("count", 1)
        g["count"] += m.get("count", 1)

    keys = list(groups.keys())
    uf = _UnionFind(len(keys))
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            (na, ta), (nb, tb) = keys[i], keys[j]
            if ta == tb and _should_merge(na, nb, ta):
                uf.union(i, j)

    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(len(keys)):
        clusters[uf.find(i)].append(i)

    entities: list[Entity] = []
    lookup: dict[tuple[str, str], str] = {}
    used_ids: set[str] = set()
    for members in clusters.values():
        surfaces: Counter = Counter()
        count = 0
        for i in members:
            surfaces.update(groups[keys[i]]["surfaces"])
            count += groups[keys[i]]["count"]
        etype = keys[members[0]][1]
        canonical = max(surfaces, key=lambda s: (len(s), surfaces[s], s))
        aliases = sorted({s for s in surfaces if s != canonical})
        eid = slugify(canonical)
        if eid in used_ids:
            eid = f"{eid}-{etype.lower()}"
        used_ids.add(eid)
        entities.append(Entity(id=eid, canonical_name=canonical, type=etype,  # type: ignore[arg-type]
                               aliases=aliases, mention_count=count))
        for i in members:
            lookup[keys[i]] = eid
    entities.sort(key=lambda e: (-e.mention_count, e.canonical_name))
    return Resolution(entities, lookup, type_of)
