"""Evalúa recuperación y, opcionalmente, respuestas; nunca indexa el CSV."""

from collections import Counter
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
from statistics import mean
from time import perf_counter
import unicodedata

from .config import BENCHMARK_PATH, Settings, get_settings
from .indexing import manifest_path
from .pipeline import TourismAgent
from .schemas import QuestionRequest


def normalize(text: str) -> list[str]:
    text = re.sub(r"\[\d+\]", "", text)
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.findall(r"\w+", text)


def token_f1(prediction: str, reference: str) -> float:
    predicted, expected = Counter(normalize(prediction)), Counter(normalize(reference))
    shared = sum((predicted & expected).values())
    total = sum(predicted.values()) + sum(expected.values())
    return 2 * shared / total if total else 1.0


def question_split(question: str) -> str:
    # Agrupa duplicados de la pregunta en la misma partición.
    key = " ".join(normalize(question)).encode("utf-8")
    return "dev" if int(hashlib.sha256(key).hexdigest(), 16) % 5 == 0 else "test"


def evaluate(settings: Settings | None = None, *, benchmark: Path = BENCHMARK_PATH,
             limit: int | None = None, generate: bool = False,
             split: str = "test", seed: int = 42) -> dict:
    settings = settings or get_settings()
    if limit is not None and limit <= 0:
        raise ValueError("limit debe ser positivo.")
    if split not in ("dev", "test", "all"):
        raise ValueError("split debe ser dev, test o all.")
    with benchmark.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"pregunta", "respuesta", "contexto", "archivo"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"El CSV debe contener: {sorted(required)}")
        rows = list(reader)
    if any(not (row.get(key) or "").strip() for row in rows for key in required):
        raise ValueError("El CSV tiene celdas vacías en columnas obligatorias.")
    selected = [(index + 1, row) for index, row in enumerate(rows)
                if split == "all" or question_split(row["pregunta"]) == split]
    random.Random(seed).shuffle(selected)
    if limit:
        selected = selected[:limit]
    if not selected:
        raise ValueError("No hay preguntas para evaluar.")
    settings.evaluation_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = settings.evaluation_dir / f"{stamp}_{split}.jsonl"
    agent = TourismAgent(settings)
    index_manifest_path = manifest_path(settings)
    index_manifest = (json.loads(index_manifest_path.read_text(encoding="utf-8"))
                      if index_manifest_path.is_file() else None)
    records = []
    with closing(agent), output.open("w", encoding="utf-8") as file:
        for position, (row_id, row) in enumerate(selected, 1):
            start = perf_counter()
            record = {"row": row_id, "question": row["pregunta"],
                      "reference_answer": row["respuesta"], "reference_context": row["contexto"],
                      "expected_source": row["archivo"], "error": None}
            try:
                # Solo la pregunta entra al sistema; las referencias se usan después.
                if generate:
                    answer = agent.ask(QuestionRequest(question=row["pregunta"]))
                    sources = answer.sources
                    record.update(answer=answer.answer, cited_sources=answer.cited_sources,
                                  token_f1=token_f1(answer.answer, row["respuesta"]),
                                  exact_match=normalize(answer.answer) == normalize(row["respuesta"]),
                                  abstained=not answer.grounded)
                else:
                    sources = agent.retriever.search(row["pregunta"])
                expected = row["archivo"].replace("\\", "/")
                rank = next((i for i, source in enumerate(sources, 1)
                             if source.source == expected), None)
                record.update(source_hit=rank is not None, reciprocal_rank=1 / rank if rank else 0,
                              sources=[source.model_dump() for source in sources])
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            record["elapsed_seconds"] = round(perf_counter() - start, 3)
            records.append(record)
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
            file.flush()
            if position == 1 or position % 25 == 0 or position == len(selected):
                print(f"Evaluadas: {position}/{len(selected)}", flush=True)
    successful = [record for record in records if record["error"] is None]
    summary = {
        "total": len(records), "successful": len(successful), "errors": len(records) - len(successful),
        "split": split, "seed": seed, "generate": generate, "top_k": settings.top_k,
        "chat_model": settings.chat_model, "embedding_model": settings.embedding_model,
        "max_distance": settings.max_distance,
        "index": index_manifest,
        "benchmark_sha256": hashlib.sha256(benchmark.read_bytes()).hexdigest(),
        "source_hit_at_k": sum(record.get("source_hit", False) for record in records) / len(records),
        "mrr_at_k": sum(record.get("reciprocal_rank", 0) for record in records) / len(records),
        "mean_seconds": mean(record["elapsed_seconds"] for record in records),
        "results_file": str(output),
        "notes": "Hit y MRR miden el archivo fuente, no la suficiencia del fragmento. "
                 "Los errores cuentan como fallos de recuperación. F1 es coincidencia léxica, "
                 "no verificación factual. Referencias alternativas se evalúan por fila.",
    }
    if generate:
        summary["mean_token_f1_successful"] = mean(r["token_f1"] for r in successful) if successful else None
        summary["exact_match_successful"] = mean(r["exact_match"] for r in successful) if successful else None
        summary["abstention_rate_successful"] = mean(r["abstained"] for r in successful) if successful else None
    summary_path = output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
