"""Vectores locales mediante Ollama; Chroma recibe los vectores explícitos."""

import httpx

from .config import Settings


class ServiceError(RuntimeError):
    """Dependencia local no disponible o respuesta inválida."""


class Embedder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.Client(
            base_url=settings.ollama_base_url.rstrip('/'), timeout=settings.request_timeout
        )

    def close(self) -> None:
        self.client.close()

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        # Instrucciones de recuperación recomendadas para EmbeddingGemma.
        if self.settings.embedding_model.split(":")[0] == "embeddinggemma":
            prefix = "task: search result | query: " if query else "title: none | text: "
            texts = [prefix + text for text in texts]
        try:
            response = self.client.post(
                "/api/embed",
                json={"model": self.settings.embedding_model, "input": texts, "truncate": False},
            )
            response.raise_for_status()
            vectors = response.json()["embeddings"]
            if len(vectors) != len(texts) or any(not vector for vector in vectors):
                raise ValueError("Número de vectores incorrecto")
            return vectors
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ServiceError(
                "No se pudieron generar embeddings. Comprueba Ollama y ejecuta "
                f"ollama pull {self.settings.embedding_model}."
            ) from exc
