"""Búsqueda semántica de fragmentos en ChromaDB."""

from .config import Settings
from .embeddings import Embedder
from .indexing import get_collection
from .schemas import Source


class Retriever:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.embedder = Embedder(settings)

    def search(self, question: str, top_k: int | None = None,
               category: str | None = None) -> list[Source]:
        collection = get_collection(self.settings)
        count = collection.count()
        if not count:
            return []
        options = {"where": {"category": category}} if category else {}
        result = collection.query(
            query_embeddings=self.embedder.embed([question], query=True),
            n_results=min(top_k or self.settings.top_k, count),
            include=["documents", "metadatas", "distances"], **options,
        )
        sources = []
        for identifier, text, metadata, distance in zip(
            result["ids"][0], result["documents"][0],
            result["metadatas"][0], result["distances"][0],
        ):
            if self.settings.max_distance is not None and distance > self.settings.max_distance:
                continue
            sources.append(Source(citation=len(sources) + 1, id=identifier, text=text,
                                  distance=distance, **metadata))
        return sources
