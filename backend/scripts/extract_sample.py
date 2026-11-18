"""Phase 1 check: print entities and relationships extracted from the sample file.

Usage (from backend/):  python -m scripts.extract_sample [path]
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.config import SAMPLE_FILE
from app.services.graph_builder import DocumentInput, build_graph
from app.services.ingestion import ingest
from app.services.relation_extractor import extract_document


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else SAMPLE_FILE
    chunks = ingest(path.name, path.read_bytes())
    ext = extract_document(chunks)
    doc = DocumentInput("sample", path.name, ext.mentions, [t.to_dict() for t in ext.triples])
    graph, stats = build_graph("preview", [doc])
    names = {e.id: e.canonical_name for e in graph.entities}
    print(f"{len(chunks)} chunks, extraction method: {ext.method}")
    print(f"\nEntities ({len(graph.entities)}):")
    for e in graph.entities:
        alias = f"  aliases={e.aliases}" if e.aliases else ""
        print(f"  [{e.type:10}] {e.canonical_name} (x{e.mention_count}){alias}")
    print(f"\nRelationships ({len(graph.relationships)}):")
    for r in graph.relationships:
        print(f"  {names[r.source_id]} --{r.relation}--> {names[r.target_id]}  ({r.confidence})")
    print(f"\nStats: {stats.model_dump()}")


if __name__ == "__main__":
    main()
