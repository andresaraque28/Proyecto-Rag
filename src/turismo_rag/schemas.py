"""Contratos de entrada y salida de la API."""

from pydantic import BaseModel, Field, ConfigDict


class QuestionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=3, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=10)
    category: str | None = Field(default=None, min_length=1, max_length=100)


class Source(BaseModel):
    citation: int
    id: str
    text: str
    source: str
    category: str
    start_char: int
    end_char: int
    distance: float = Field(description="Distancia coseno: menor es más cercano; no es una probabilidad.")


class Answer(BaseModel):
    question: str
    answer: str
    sources: list[Source]
    cited_sources: list[int]
    grounded: bool = Field(description="Indica citas con números válidos, no verificación factual.")
    model: str
    elapsed_seconds: float
