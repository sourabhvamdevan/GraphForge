from fastapi.testclient import TestClient

from app.config import SAMPLE_FILE, settings
from app.main import app

CANONICAL = "Which cloud infrastructure is associated with the company Microsoft invested in?"


def test_end_to_end_without_llm():
    assert not settings.llm_enabled
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert health == {"status": "ok", "llm_enabled": False}

        with SAMPLE_FILE.open("rb") as fh:
            up = client.post("/api/documents", files={"file": ("tech_ecosystem.txt", fh, "text/plain")})
        assert up.status_code == 200, up.text
        doc = up.json()
        assert doc["chunks"] > 0 and doc["status"] == "processed"
        assert any(d["document_id"] == doc["document_id"] for d in client.get("/api/documents").json())

        built = client.post("/api/graph/build", json={"document_ids": [doc["document_id"]]})
        assert built.status_code == 200, built.text
        graph = built.json()
        assert len(graph["entities"]) >= 15 and len(graph["relationships"]) >= 20
        assert graph["stats"]["node_count"] == len(graph["entities"])
        assert all(r["evidence"] for r in graph["relationships"])
        gid = graph["graph_id"]

        assert client.get(f"/api/graph/{gid}").status_code == 200
        assert client.get(f"/api/graph/{gid}/export").json()["graph_id"] == gid
        detail = client.get(f"/api/graph/{gid}/entity/openai").json()
        assert detail["entity"]["canonical_name"] == "OpenAI" and detail["incoming"]
        hits = client.get(f"/api/graph/{gid}/search", params={"q": "altman"}).json()
        assert hits[0]["canonical_name"] == "Sam Altman" and "Altman" in hits[0]["aliases"]

        q = client.post("/api/query", json={"graph_id": gid, "question": CANONICAL}).json()
        assert q["answer"].startswith("Azure")
        path = [(s["source"], s["relation"], s["target"]) for s in q["paths"][0]]
        assert path == [("Microsoft", "invested_in", "OpenAI"), ("OpenAI", "uses_infrastructure", "Azure")]
        assert all(s["evidence"]["sentence"] for s in q["paths"][0])

        low = client.post("/api/query", json={"graph_id": gid, "question": "What did Zorblax Corp acquire?"}).json()
        assert low["confidence"] == "low"


def test_errors():
    with TestClient(app) as client:
        assert client.get("/api/graph/missing").status_code == 404
        r = client.post("/api/documents", files={"file": ("x.png", b"123", "image/png")})
        assert r.status_code == 422 and "detail" in r.json()
        big = b"a" * (settings.max_upload_bytes + 10)
        assert client.post("/api/documents", files={"file": ("big.txt", big, "text/plain")}).status_code == 413
        assert client.post("/api/graph/build", json={"document_ids": ["nope"]}).status_code == 404
