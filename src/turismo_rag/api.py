"""API local. Interfaz interactiva disponible en /docs."""

import logging
from contextlib import asynccontextmanager
from functools import lru_cache

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .config import get_settings
from .embeddings import ServiceError
from .indexing import get_collection
from .pipeline import TourismAgent
from .schemas import Answer, QuestionRequest, Source

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if get_agent.cache_info().currsize:
        get_agent().close()
        get_agent.cache_clear()


app = FastAPI(title="Turismo Valencia RAG", version="0.1.0", lifespan=lifespan,
              description="Consultas locales con Ollama y ChromaDB. Cada petición es independiente.")
logger = logging.getLogger(__name__)


@lru_cache
def get_agent() -> TourismAgent:
    return TourismAgent()


@app.exception_handler(ServiceError)
async def service_error(request: Request, exc: ServiceError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logger.exception("Error durante la consulta", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Error interno. Revisa el registro del servidor."})


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    settings = get_settings()
    issues = []
    count = 0
    try:
        count = get_collection(settings).count()
    except Exception:
        issues.append("Índice no disponible o incompatible; ejecuta turismo-rag index.")
    try:
        response = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=5)
        response.raise_for_status()
        models = {model["name"] for model in response.json()["models"]}
        for model in (settings.chat_model, settings.embedding_model):
            normalized = model if ":" in model else model + ":latest"
            if normalized not in models:
                issues.append(f"Modelo pendiente: ollama pull {model}")
    except (httpx.HTTPError, ValueError, KeyError):
        issues.append("Ollama no responde.")
    return JSONResponse(status_code=503 if issues else 200, content={
        "status": "not_ready" if issues else "ready", "chunks": count,
        "chat_model": settings.chat_model, "embedding_model": settings.embedding_model,
        "issues": issues,
    })


@app.post("/search", response_model=list[Source])
def search(request: QuestionRequest, agent: TourismAgent = Depends(get_agent)):
    return agent.retriever.search(request.question, request.top_k, request.category)


@app.post("/ask", response_model=Answer)
def ask(request: QuestionRequest, agent: TourismAgent = Depends(get_agent)):
    return agent.ask(request)
