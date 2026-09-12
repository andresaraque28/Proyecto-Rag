"""Lee los documentos originales y conserva su procedencia.

Desde la raíz del proyecto:
    python -m src.turismo_rag.ingestion
"""

from pathlib import Path
from typing import TypedDict

from .config import DOCUMENTS_DIR


class Document(TypedDict):
    """Texto y metadatos que acompañarán a cada documento."""

    text: str
    source: str
    category: str


def load_documents(documents_dir: Path = DOCUMENTS_DIR) -> list[Document]:
    """Lee los .txt de la carpeta y sus subcarpetas en orden estable.

    La fuente es una ruta relativa con barras '/', compatible con la
    columna 'archivo' del benchmark. El CSV no se carga como documento.
    """
    documents_dir = Path(documents_dir)
    if not documents_dir.is_dir():
        raise FileNotFoundError(f"No existe la carpeta de documentos: {documents_dir}")

    paths = sorted(documents_dir.rglob("*.txt"))
    if not paths:
        raise ValueError(f"No se encontraron documentos .txt en: {documents_dir}")

    documents: list[Document] = []
    for path in paths:
        # utf-8-sig también admite archivos UTF-8 con marca BOM inicial.
        text = path.read_text(encoding="utf-8-sig")
        if not text.strip():
            raise ValueError(f"El documento está vacío: {path}")

        relative_path = path.relative_to(documents_dir)
        documents.append(
            {
                "text": text,
                "source": relative_path.as_posix(),
                "category": relative_path.parts[0] if len(relative_path.parts) > 1 else "Sin categoría",
            }
        )

    return documents


def main() -> None:
    """Muestra un resumen para comprobar la lectura sin usar un modelo."""
    documents = load_documents()
    print(f"Documentos cargados: {len(documents)}")
    for category in sorted({document["category"] for document in documents}):
        count = sum(document["category"] == category for document in documents)
        print(f"  {category}: {count}")

    first = documents[0]
    print(f"\nPrimer documento: {first['source']}")
    print(f"Caracteres: {len(first['text'])}")
    print(f"Vista previa:\n{first['text'][:300]}")


if __name__ == "__main__":
    main()
