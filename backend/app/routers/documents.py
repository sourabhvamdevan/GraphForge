from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from app import db
from app.config import SAMPLE_FILE, settings
from app.models import DocumentSummary, DocumentUploadResponse
from app.services.ingestion import IngestionError, ingest
from app.services.relation_extractor import extract_document

router = APIRouter(prefix="/documents", tags=["documents"])


def process_document(name: str, data: bytes) -> DocumentUploadResponse:
    try:
        chunks = ingest(name, data)
    except IngestionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    extraction = extract_document(chunks)
    doc_id = uuid.uuid4().hex[:12]
    db.save_document(doc_id, name, [c.sentences for c in chunks], extraction.mentions,
                     [t.to_dict() for t in extraction.triples], extraction.method)
    return DocumentUploadResponse(document_id=doc_id, name=name, chunks=len(chunks), status="processed")


@router.post("", response_model=DocumentUploadResponse)
def upload_document(file: UploadFile = File(...)) -> DocumentUploadResponse:
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"File is larger than {settings.max_upload_mb} MB.")
    return process_document(file.filename or "upload.txt", data)


@router.post("/sample", response_model=DocumentUploadResponse)
def load_sample() -> DocumentUploadResponse:
    """Process the bundled sample document (used by the UI's 'Load sample data' button)."""
    return process_document(SAMPLE_FILE.name, SAMPLE_FILE.read_bytes())


@router.get("", response_model=list[DocumentSummary])
def list_documents() -> list[DocumentSummary]:
    return [DocumentSummary(**d) for d in db.list_documents()]
