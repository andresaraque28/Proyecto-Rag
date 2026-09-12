"""Índice persistente con publicación de una colección completa al terminar."""

import hashlib
import json
from contextlib import closing

import chromadb
from chromadb.config import Settings as ChromaSettings

from .chunking import split_documents, save_chunks
from .config import CHUNK_OVERLAP, CHUNK_SIZE, Settings, get_settings
from .embeddings import Embedder, ServiceError
from .ingestion import load_documents


def get_client(settings: Settings):
    return chromadb.PersistentClient(
        path=str(settings.chroma_dir), settings=ChromaSettings(anonymized_telemetry=False)
    )


def manifest_path(settings: Settings):
    return settings.chroma_dir / f"{settings.collection_name}.json"


def get_collection(settings: Settings):
    path = manifest_path(settings)
    if not path.is_file():
        raise ServiceError("No hay índice publicado. Ejecuta: turismo-rag index")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["embedding_model"] != settings.embedding_model:
        raise ServiceError("Cambió el modelo de embeddings. Ejecuta: turismo-rag index")
    collection = get_client(settings).get_collection(manifest["collection"], embedding_function=None)
    if collection.count() != manifest["chunks"]:
        raise ServiceError("El índice está incompleto. Ejecuta: turismo-rag index")
    return collection


def build_index(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    documents = load_documents()
    chunks = split_documents(documents)
    fingerprint = hashlib.sha256(json.dumps(
        {"model": settings.embedding_model, "size": CHUNK_SIZE,
         "overlap": CHUNK_OVERLAP, "embedding_prompt_version": 1, "chunks": chunks},
        ensure_ascii=False, sort_keys=True,
    ).encode("utf-8")).hexdigest()[:20]
    name = f"{settings.collection_name}_{fingerprint}"
    client = get_client(settings)
    collection = client.get_or_create_collection(
        name=name, embedding_function=None, metadata={"hnsw:space": "cosine"}
    )
    existing = set(collection.get(include=[])["ids"])
    pending = [chunk for chunk in chunks if chunk["id"] not in existing]
    with closing(Embedder(settings)) as embedder:
        for offset in range(0, len(pending), 32):
            batch = pending[offset:offset + 32]
            vectors = embedder.embed([chunk["text"] for chunk in batch])
            collection.upsert(
                ids=[chunk["id"] for chunk in batch],
                documents=[chunk["text"] for chunk in batch],
                embeddings=vectors,
                metadatas=[{key: value for key, value in chunk.items() if key not in ("text", "id")}
                           for chunk in batch],
            )
            print(f"Indexados: {min(offset + 32, len(pending))}/{len(pending)}", flush=True)
    if collection.count() != len(chunks):
        raise ServiceError("El índice generado no coincide con los fragmentos.")
    manifest = {"collection": name, "embedding_model": settings.embedding_model,
                "documents": len(documents), "chunks": len(chunks), "fingerprint": fingerprint}
    save_chunks(chunks)
    path = manifest_path(settings)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temporary.replace(path)
    return manifest
