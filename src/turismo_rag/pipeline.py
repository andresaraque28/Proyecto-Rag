"""Orquesta recuperación y respuesta con fuentes."""

from time import perf_counter

from .config import Settings, get_settings
from .generation import Generator
from .retrieval import Retriever
from .schemas import Answer, QuestionRequest


class TourismAgent:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.retriever = Retriever(self.settings)
        self.generator = Generator(self.settings)

    def close(self) -> None:
        self.retriever.embedder.close()

    def ask(self, request: QuestionRequest) -> Answer:
        start = perf_counter()
        sources = self.retriever.search(request.question, request.top_k, request.category)
        answer, citations = self.generator.answer(request.question, sources)
        return Answer(question=request.question, answer=answer, sources=sources,
                      cited_sources=citations, grounded=bool(citations),
                      model=self.settings.chat_model,
                      elapsed_seconds=round(perf_counter() - start, 3))
