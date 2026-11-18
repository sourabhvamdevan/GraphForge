import pymupdf
import pytest

from app.services.ingestion import IngestionError, chunk_sentences, ingest, normalize


def _pdf_bytes(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(72, 72, 540, 760), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_txt_produces_chunks():
    text = " ".join(f"Company{i} developed Product{i}." for i in range(12))
    chunks = ingest("notes.txt", text.encode())
    assert len(chunks) >= 3
    assert all(1 <= len(c.sentences) <= 5 for c in chunks)
    # 1-sentence overlap between consecutive chunks
    assert chunks[0].sentences[-1] == chunks[1].sentences[0]
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_pdf_produces_chunks():
    data = _pdf_bytes(["Microsoft invested in OpenAI. OpenAI uses Azure infrastructure.",
                       "Google developed TensorFlow. Meta developed PyTorch."])
    chunks = ingest("paper.pdf", data)
    joined = " ".join(c.text for c in chunks)
    assert "Microsoft invested in OpenAI." in joined
    assert "Meta developed PyTorch." in joined


def test_oversized_file_rejected():
    with pytest.raises(IngestionError) as exc:
        ingest("big.txt", b"x" * 2048, max_bytes=1024)
    assert exc.value.status_code == 413


def test_too_many_pages_rejected():
    data = _pdf_bytes([f"Page {i} text." for i in range(4)])
    with pytest.raises(IngestionError) as exc:
        ingest("long.pdf", data, max_pages=3)
    assert exc.value.status_code == 422


def test_unsupported_type_rejected():
    with pytest.raises(IngestionError) as exc:
        ingest("image.png", b"\x89PNG....")
    assert exc.value.status_code == 422


def test_normalize_strips_headers_page_numbers_and_hyphens():
    pages = [f"ACME Annual Report\nSection {i} intro.\nThe trans-\nformer model {i} is great.\nClosing {i}.\n{i}"
             for i in range(1, 5)]
    text = normalize(pages)
    assert "ACME Annual Report" not in text
    assert "transformer" in text
    assert "\n4" not in text


def test_chunk_sentences_overlap():
    chunks = chunk_sentences([f"S{i}." for i in range(9)])
    assert [c.sentences for c in chunks] == [
        ["S0.", "S1.", "S2.", "S3.", "S4."],
        ["S4.", "S5.", "S6.", "S7.", "S8."],
    ]
