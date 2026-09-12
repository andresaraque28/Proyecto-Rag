"""Divide documentos y guarda fragmentos con su procedencia.

Ejecutar desde la raíz: python -m src.turismo_rag.chunking
No realiza llamadas a modelos.
"""

import json
from pathlib import Path
from typing import TypedDict

from .config import CHUNK_OVERLAP, CHUNK_SIZE, CHUNKS_PATH
from .ingestion import Document, load_documents


class Chunk(TypedDict):
    """Un fragmento y su ubicación exacta dentro del documento original."""

    id: str
    text: str
    source: str
    category: str
    start_char: int
    end_char: int


def split_documents(
    documents: list[Document],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """Genera fragmentos de hasta chunk_size caracteres.

    Prefiere terminar en párrafos, líneas, oraciones o espacios, en ese
    orden. Busca esos cortes en la parte final del fragmento para evitar
    fragmentos demasiado pequeños. Si no encuentra uno, corta por tamaño.
    El inicio del siguiente fragmento retrocede chunk_overlap caracteres;
    por eso puede comenzar en medio de una palabra.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size debe ser mayor que cero.")
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_overlap debe estar entre 0 y chunk_size - 1.")

    chunks: list[Chunk] = []
    for document in documents:
        text = document["text"]
        start = 0
        index = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                # Cada corte debe permitir avanzar incluso con solapamiento.
                search_start = start + max(chunk_size // 2, chunk_overlap)
                for separator in ("\n\n", "\n", ". ", "? ", "! ", " "):
                    position = text.rfind(separator, search_start, end)
                    if position != -1:
                        end = position + len(separator)
                        break

            fragment = text[start:end]
            if fragment.strip():
                chunks.append(
                    {
                        "id": f"{document['source']}::chunk_{index:04d}",
                        "text": fragment,
                        "source": document["source"],
                        "category": document["category"],
                        "start_char": start,
                        "end_char": end,
                    }
                )
                index += 1

            if end == len(text):
                break
            start = end - chunk_overlap

    return chunks


def save_chunks(chunks: list[Chunk], output_path: Path = CHUNKS_PATH) -> None:
    """Guarda un objeto JSON por línea; reemplaza el resultado anterior."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for chunk in chunks:
            file.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def main() -> None:
    documents = load_documents()
    chunks = split_documents(documents)
    save_chunks(chunks)

    print(f"Documentos cargados: {len(documents)}")
    print(f"Fragmentos generados: {len(chunks)}")
    print(f"Tamaño máximo: {CHUNK_SIZE} caracteres")
    print(f"Solapamiento: {CHUNK_OVERLAP} caracteres")
    print(f"Archivo generado: {CHUNKS_PATH}")
    if chunks:
        first = chunks[0]
        print(f"\nPrimer fragmento: {first['id']}")
        print(f"Vista previa:\n{first['text'][:300]}")


if __name__ == "__main__":
    main()
