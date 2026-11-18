"""PDF/TXT -> clean text -> sentence chunks (plan 5.1)."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import pymupdf as fitz  # PyMuPDF

from app.config import settings

CHUNK_SIZE = 5
CHUNK_OVERLAP = 1

_PAGE_NUM_RE = re.compile(r"^\s*(page\s*)?\d{1,4}(\s*(of|/)\s*\d{1,4})?\s*$", re.IGNORECASE)


class IngestionError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass
class Chunk:
    index: int
    sentences: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(self.sentences)


def extract_pages(filename: str, data: bytes, max_bytes: int | None = None,
                  max_pages: int | None = None) -> list[str]:
    """Return raw text per page. Raises IngestionError on invalid input."""
    max_bytes = settings.max_upload_bytes if max_bytes is None else max_bytes
    max_pages = settings.max_pages if max_pages is None else max_pages
    if len(data) > max_bytes:
        raise IngestionError(413, f"File is larger than {max_bytes // (1024 * 1024)} MB.")
    if not data:
        raise IngestionError(422, "File is empty.")

    name = filename.lower()
    if name.endswith(".pdf"):
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:  # noqa: BLE001
            raise IngestionError(422, f"Could not read PDF: {exc}") from exc
        with doc:
            if doc.page_count > max_pages:
                raise IngestionError(422, f"PDF has {doc.page_count} pages; the limit is {max_pages}.")
            pages = [page.get_text("text") for page in doc]
        if not any(p.strip() for p in pages):
            raise IngestionError(422, "PDF contains no extractable text (scanned PDFs are not supported).")
        return pages
    if name.endswith(".txt") or name.endswith(".md"):
        try:
            return [data.decode("utf-8")]
        except UnicodeDecodeError as exc:
            raise IngestionError(422, "Text file must be UTF-8 encoded.") from exc
    raise IngestionError(422, "Unsupported file type. Upload a .pdf or .txt file.")


def _repeated_edge_lines(pages: list[str]) -> set[str]:
    """Header/footer lines (first or last 2 lines of a page) repeated on >= 3 pages."""
    counter: Counter[str] = Counter()
    for page in pages:
        lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
        edge = set(lines[:2] + lines[-2:])
        counter.update(edge)
    return {line for line, n in counter.items() if n >= 3 and len(line) < 120}


def normalize(pages: list[str]) -> str:
    """Clean text; paragraphs are separated by a blank line."""
    repeated = _repeated_edge_lines(pages) if len(pages) >= 3 else set()
    kept_pages = []
    for page in pages:
        lines = []
        for line in page.splitlines():
            s = line.strip()
            if s in repeated or _PAGE_NUM_RE.match(s):
                continue
            lines.append(line.rstrip())
        kept_pages.append("\n".join(lines))
    text = "\n\n".join(kept_pages)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n\s*(\w)", r"\1\2", text)  # hyphenated line breaks
    paragraphs = re.split(r"\n\s*\n", text)
    cleaned = [re.sub(r"\s+", " ", p).strip() for p in paragraphs]
    return "\n\n".join(p for p in cleaned if p)


def split_sentences(text: str) -> list[str]:
    from app.services.entity_extractor import get_nlp

    nlp = get_nlp()
    sentences: list[str] = []
    for para in text.split("\n\n"):
        if not para.strip():
            continue
        doc = nlp(para)
        for sent in doc.sents:
            s = sent.text.strip()
            if s:
                sentences.append(s)
    return sentences


def chunk_sentences(sentences: list[str], size: int = CHUNK_SIZE,
                    overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    if not sentences:
        return []
    step = max(1, size - overlap)
    chunks: list[Chunk] = []
    start = 0
    while True:
        chunks.append(Chunk(index=len(chunks), sentences=sentences[start:start + size]))
        if start + size >= len(sentences):
            break
        start += step
    return chunks


def ingest(filename: str, data: bytes, **limits) -> list[Chunk]:
    pages = extract_pages(filename, data, **limits)
    text = normalize(pages)
    chunks = chunk_sentences(split_sentences(text))
    if not chunks:
        raise IngestionError(422, "No text could be extracted from the file.")
    return chunks
