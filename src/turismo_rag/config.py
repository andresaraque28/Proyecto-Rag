"""Rutas del proyecto, independientes de la carpeta de ejecución."""

from pathlib import Path
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Este archivo está en Proyecto_Agentes/src/turismo_rag/config.py.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DOCUMENTS_DIR = DATA_DIR / "Documentos Fuente"
BENCHMARK_PATH = DATA_DIR / "dataset.csv"
PROCESSED_DIR = DATA_DIR / "processed"
CHUNKS_PATH = PROCESSED_DIR / "chunks.jsonl"

# Medidas en caracteres, no en tokens.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


class Settings(BaseSettings):
    """Lee opciones desde .env o variables de entorno, sin claves de pago."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )
    ollama_base_url: str = "http://127.0.0.1:11434"
    chat_model: str = "gemma3:4b"
    embedding_model: str = "embeddinggemma:latest"
    chroma_dir: Path = DATA_DIR / "vector_store"
    collection_name: str = "valencia_tourism"
    evaluation_dir: Path = DATA_DIR / "evaluation"
    top_k: int = Field(default=5, ge=1, le=10)
    request_timeout: float = Field(default=180, gt=0)
    max_distance: float | None = Field(default=None, ge=0, le=2)


@lru_cache
def get_settings() -> Settings:
    return Settings()
