"""Juez LLM local: mide alucinación frente al contexto y acierto frente a la referencia."""

import json

from langchain_ollama import ChatOllama

from .config import Settings
from .generation import ABSTENTION
from .schemas import Source

FAITHFULNESS_PROMPT = """Eres un evaluador estricto de sistemas RAG.
Divide la RESPUESTA en afirmaciones factuales atómicas. Para cada una decide si los
FRAGMENTOS la respaldan explícitamente. Lo que no aparezca en ellos no está respaldado,
aunque sea cierto en el mundo real. Ignora las marcas de cita como [1].
Devuelve solo JSON: {"claims": [{"claim": "...", "supported": true}]}"""

CORRECTNESS_PROMPT = """Eres un evaluador estricto de sistemas RAG.
Compara la RESPUESTA con la REFERENCIA para la PREGUNTA dada.
Usa "correct" si transmite la información esencial de la referencia sin contradecirla,
"partial" si acierta solo una parte y "incorrect" si falla, contradice o no responde.
Devuelve solo JSON: {"verdict": "correct", "reason": "una frase"}"""

CORRECTNESS_SCORES = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}

# Ollama restringe la salida a estos esquemas; el modo JSON libre producía claves rotas.
FAITHFULNESS_SCHEMA = {
    "type": "object", "required": ["claims"],
    "properties": {"claims": {"type": "array", "items": {
        "type": "object", "required": ["claim", "supported"],
        "properties": {"claim": {"type": "string"}, "supported": {"type": "boolean"}},
    }}},
}
CORRECTNESS_SCHEMA = {
    "type": "object", "required": ["verdict", "reason"],
    "properties": {"verdict": {"type": "string", "enum": list(CORRECTNESS_SCORES)},
                   "reason": {"type": "string"}},
}


class Judge:
    def __init__(self, settings: Settings):
        self.model_name = settings.judge_model or settings.chat_model
        options = {"model": self.model_name, "base_url": settings.ollama_base_url,
                   "temperature": 0, "num_ctx": 8192, "num_predict": 800,
                   "client_kwargs": {"timeout": settings.request_timeout}}
        self.faithfulness_model = ChatOllama(format=FAITHFULNESS_SCHEMA, **options)
        self.correctness_model = ChatOllama(format=CORRECTNESS_SCHEMA, **options)

    @staticmethod
    def _ask(model, system: str, human: str) -> dict:
        response = model.invoke([("system", system), ("human", human)])
        data = json.loads(response.content)
        if not isinstance(data, dict):
            raise ValueError("El juez no devolvió un objeto JSON.")
        return data

    def faithfulness(self, answer: str, sources: list[Source]) -> dict:
        """Proporción de afirmaciones sin respaldo en los fragmentos que vio el modelo."""
        result = {"judge_model": self.model_name}
        if answer == ABSTENTION:
            return result | {"skipped": "abstention"}
        context = json.dumps([{"citation": s.citation, "text": s.text} for s in sources],
                             ensure_ascii=False)
        try:
            data = self._ask(self.faithfulness_model, FAITHFULNESS_PROMPT,
                             f"FRAGMENTOS:\n{context}\n\nRESPUESTA:\n{answer}")
            claims = [c for c in data.get("claims", [])
                      if isinstance(c, dict) and isinstance(c.get("supported"), bool)]
        except Exception as exc:
            return result | {"judge_error": f"{type(exc).__name__}: {exc}"}
        if not claims:
            return result | {"judge_error": "El juez no extrajo afirmaciones válidas."}
        unsupported = [str(c.get("claim", "")) for c in claims if not c["supported"]]
        return result | {
            "claims": len(claims), "unsupported_claims": unsupported,
            "hallucination_rate": len(unsupported) / len(claims),
            "hallucinated": bool(unsupported),
        }

    def correctness(self, question: str, answer: str, reference: str) -> dict:
        """Compara con la respuesta de referencia; una abstención cuenta como incorrecta."""
        result = {"judge_model": self.model_name}
        if answer == ABSTENTION:
            return result | {"verdict": "incorrect", "score": 0.0, "reason": "abstención"}
        try:
            data = self._ask(self.correctness_model, CORRECTNESS_PROMPT,
                             f"PREGUNTA: {question}\n\nREFERENCIA: {reference}\n\nRESPUESTA: {answer}")
            verdict = str(data.get("verdict", "")).strip().lower()
            if verdict not in CORRECTNESS_SCORES:
                raise ValueError(f"Veredicto desconocido: {verdict!r}")
        except Exception as exc:
            return result | {"judge_error": f"{type(exc).__name__}: {exc}"}
        return result | {"verdict": verdict, "score": CORRECTNESS_SCORES[verdict],
                         "reason": str(data.get("reason", ""))}
