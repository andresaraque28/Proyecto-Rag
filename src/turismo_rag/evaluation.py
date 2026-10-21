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
from .judge import Judge
from .monitoring import log_event
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
             split: str = "test", seed: int = 42, judge: bool = False) -> dict:
    settings = settings or get_settings()
    if limit is not None and limit <= 0:
        raise ValueError("limit debe ser positivo.")
    if split not in ("dev", "test", "all"):
        raise ValueError("split debe ser dev, test o all.")
    if judge and not generate:
        raise ValueError("judge requiere generate: el juez evalúa respuestas generadas.")
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
    evaluator = Judge(settings) if judge else None
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
                    if evaluator:
                        record.update(
                            faithfulness=evaluator.faithfulness(answer.answer, sources),
                            correctness=evaluator.correctness(row["pregunta"], answer.answer,
                                                              row["respuesta"]))
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
                 "no verificación factual. Referencias alternativas se evalúan por fila. "
                 "Las métricas del juez dependen del modelo juez y son aproximadas.",
    }
    if generate:
        summary["mean_token_f1_successful"] = mean(r["token_f1"] for r in successful) if successful else None
        summary["exact_match_successful"] = mean(r["exact_match"] for r in successful) if successful else None
        summary["abstention_rate_successful"] = mean(r["abstained"] for r in successful) if successful else None
    if judge:
        summary.update(judge_summary(successful))
        summary["judge_model"] = evaluator.model_name
    summary_path = output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    run = append_run(settings.evaluation_dir / "runs.jsonl", stamp, summary)
    log_event(settings, "evaluation_run", **run)
    return summary


def judge_summary(records: list[dict]) -> dict:
    """Alucinación sobre respuestas no abstenidas; acierto sobre todas, abstención = 0."""
    faithful = [r["faithfulness"] for r in records
                if "hallucinated" in r.get("faithfulness", {})]
    correct = [r["correctness"] for r in records if "score" in r.get("correctness", {})]
    errors = sum("judge_error" in r.get(key, {}) for r in records
                 for key in ("faithfulness", "correctness"))
    return {
        "judged_answers": len(faithful),
        "hallucination_response_rate": mean(f["hallucinated"] for f in faithful) if faithful else None,
        "mean_claim_hallucination_rate": mean(f["hallucination_rate"] for f in faithful) if faithful else None,
        "correctness_score": mean(c["score"] for c in correct) if correct else None,
        "correct_rate": mean(c["verdict"] == "correct" for c in correct) if correct else None,
        "judge_errors": errors,
    }


RUN_FIELDS = ("split", "total", "errors", "generate", "chat_model", "embedding_model", "top_k",
              "source_hit_at_k", "mrr_at_k", "mean_token_f1_successful",
              "abstention_rate_successful", "judge_model", "judged_answers",
              "hallucination_response_rate", "mean_claim_hallucination_rate",
              "correctness_score", "correct_rate", "judge_errors", "mean_seconds", "results_file")


def append_run(path: Path, stamp: str, summary: dict) -> dict:
    # Historial de una línea por ejecución para comparar modelos y configuraciones.
    run = {"run": stamp, **{key: summary[key] for key in RUN_FIELDS if key in summary}}
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(run, ensure_ascii=False) + "\n")
    return run
