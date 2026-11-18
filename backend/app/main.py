from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.config import settings
from app.models import HealthResponse
from app.routers import documents, graph, query
from app.services.entity_extractor import get_nlp

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    get_nlp()  # load spaCy once at startup
    yield


app = FastAPI(title="GraphForge", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(query.router, prefix="/api")


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", llm_enabled=settings.llm_enabled)
