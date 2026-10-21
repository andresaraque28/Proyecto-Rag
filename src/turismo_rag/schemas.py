"""Contratos de entrada y salida de la API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Carpetas de data/Documentos Fuente; un valor libre filtraba todo y devolvía [].
Category = Literal["Articulos del blog", "Artículos Wikipedia", "Guias turisticas"]


class QuestionRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True, extra="forbid",
        json_schema_extra={"examples": [{"question": "¿Qué días y horas está abierto el Mercado Central?"}]},
    )
    question: str = Field(min_length=3, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=10)
    category: Category | None = Field(default=None, description="Omítelo para buscar en todo.")

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if not any(character.isalnum() for character in value):
            raise ValueError("La pregunta debe contener letras o números.")
        if any(ord(character) < 32 for character in value):
            raise ValueError("La pregunta contiene caracteres de control no permitidos.")
        return value


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
