from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from turismo_rag.api import app, get_agent
from turismo_rag.chunking import split_documents
from turismo_rag.config import Settings
from turismo_rag.embeddings import ServiceError
from turismo_rag.evaluation import question_split, token_f1
from turismo_rag.generation import ABSTENTION, Generator
from turismo_rag.indexing import get_collection
from turismo_rag.schemas import Source


def test_chunk_coverage_and_overlap():
    text = "Un párrafo turístico de Valencia.\n\n" * 100
    chunks = split_documents([{"text": text, "source": "blog/a.txt", "category": "blog"}])
    assert chunks[0]["start_char"] == 0
    assert chunks[-1]["end_char"] == len(text)
    assert len({c["id"] for c in chunks}) == len(chunks)
    for chunk in chunks:
        assert chunk["text"] == text[chunk["start_char"]:chunk["end_char"]]
        assert 0 < len(chunk["text"]) <= 1000
    for previous, current in zip(chunks, chunks[1:]):
        assert current["start_char"] == previous["end_char"] - 150


@pytest.mark.parametrize("size,overlap", [(0, 0), (10, 10), (10, -1)])
def test_invalid_chunk_settings(size, overlap):
    with pytest.raises(ValueError):
        split_documents([], size, overlap)


def test_missing_index_is_actionable(tmp_path):
    with pytest.raises(ServiceError, match="turismo-rag index"):
        get_collection(Settings(chroma_dir=tmp_path, _env_file=None))


def test_metrics_and_duplicate_partition():
    assert token_f1("València [1]", "Valencia") == 1
    assert token_f1("Madrid", "Valencia") == 0
    assert question_split("¿Qué visitar en València?") == question_split("que visitar en valencia")


@pytest.mark.parametrize("content,expected", [
    ("Está en Valencia [1].", [1]), ("Está en Valencia [9].", []),
    ("Está en Valencia.", []),
    ("Está en Valencia [1, 1].", [1]),
    ("Está en Valencia [1]. También [9, 10].", []),
])
def test_generation_rejects_invalid_citations(content, expected):
    generator = Generator.__new__(Generator)
    generator.model = SimpleNamespace(invoke=lambda messages: SimpleNamespace(content=content))
    source = Source(citation=1, id="a", text="Valencia", source="a.txt", category="blog",
                    start_char=0, end_char=8, distance=0.2)
    answer, citations = generator.answer("¿Dónde está?", [source])
    assert citations == expected
    if not expected:
        assert answer == ABSTENTION


def test_no_context_does_not_call_model():
    generator = Generator.__new__(Generator)
    assert generator.answer("¿Dónde?", []) == (ABSTENTION, [])


def test_api_validation_and_dependency_error():
    def fail(*args):
        raise ServiceError("Ollama no disponible")
    app.dependency_overrides[get_agent] = lambda: SimpleNamespace(ask=fail)
    try:
        with TestClient(app) as client:
            assert client.post("/ask", json={"question": "   "}).status_code == 422
            assert client.post("/ask", json={"question": "Valencia", "top_k": 11}).status_code == 422
            response = client.post("/ask", json={"question": "¿Qué visitar?"})
            assert response.status_code == 503
            assert response.json()["detail"] == "Ollama no disponible"
            assert client.get("/docs").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_index_reuse_and_failed_replacement_preserves_active_index(tmp_path, monkeypatch):
    from turismo_rag import indexing

    documents = [{"text": "Mercado Central de Valencia", "source": "blog/a.txt", "category": "blog"}]
    calls = []

    def embed(self, texts):
        calls.append(texts)
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(indexing, "load_documents", lambda: documents)
    monkeypatch.setattr(indexing, "save_chunks", lambda chunks: None)
    monkeypatch.setattr(indexing.Embedder, "embed", embed)
    settings = Settings(chroma_dir=tmp_path, _env_file=None)
    original = indexing.build_index(settings)
    assert indexing.build_index(settings) == original
    assert len(calls) == 1  # No vuelve a generar vectores.

    documents[:] = [{"text": "La Albufera", "source": "guias/b.txt", "category": "guias"}]

    def fail(*args):
        raise ServiceError("Servicio interrumpido")

    monkeypatch.setattr(indexing.Embedder, "embed", fail)
    with pytest.raises(ServiceError):
        indexing.build_index(settings)
    assert indexing.get_collection(settings).get()["ids"] == ["blog/a.txt::chunk_0000"]

    monkeypatch.setattr(indexing.Embedder, "embed", embed)
    replacement = indexing.build_index(settings)
    assert replacement["collection"] != original["collection"]
    assert indexing.get_collection(settings).get()["ids"] == ["guias/b.txt::chunk_0000"]


def test_evaluation_never_passes_reference_to_search(tmp_path, monkeypatch):
    import csv
    from turismo_rag import evaluation

    path = tmp_path / "benchmark.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["pregunta", "respuesta", "contexto", "archivo"])
        writer.writeheader()
        writer.writerow({"pregunta": "¿Qué visitar?", "respuesta": "REFERENCIA SECRETA",
                         "contexto": "CONTEXTO SECRETO", "archivo": "blog/a.txt"})
    seen = []

    def search(question):
        seen.append(question)
        return [Source(citation=1, id="a", text="Mercado", source="blog/a.txt", category="blog",
                       start_char=0, end_char=7, distance=0.1)]

    monkeypatch.setattr(evaluation, "TourismAgent", lambda settings: SimpleNamespace(
        retriever=SimpleNamespace(search=search), close=lambda: None))
    result = evaluation.evaluate(Settings(evaluation_dir=tmp_path, _env_file=None),
                                 benchmark=path, split="all")
    assert seen == ["¿Qué visitar?"]
    assert result["source_hit_at_k"] == 1
    assert result["mrr_at_k"] == 1
    assert result["errors"] == 0
