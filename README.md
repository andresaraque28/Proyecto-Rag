# Turismo Valencia RAG

Asistente local que consulta los documentos de `data/Documentos Fuente`, busca
fragmentos en ChromaDB y responde con Ollama mediante LangChain. FastAPI expone
el servicio. No requiere claves de API ni servicios de pago; utiliza los recursos
de tu equipo. La descarga inicial de dependencias y modelos requiere internet.

## Inicio rápido (PowerShell)

Desde la raíz del proyecto, con Python 3.12 y Ollama instalados:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ollama pull embeddinggemma:latest
ollama pull gemma3:4b
turismo-rag index
turismo-rag serve
```

Ollama debe estar ejecutándose. Si su aplicación no está abierta, ejecuta
`ollama serve` en otra terminal. La API escucha en `http://127.0.0.1:8000`.
Abre **http://127.0.0.1:8000/docs** para consultar desde el navegador:
selecciona `POST /ask`, pulsa **Try it out**, escribe el JSON y pulsa **Execute**.

`requirements-lock.txt` registra las versiones instaladas en Python 3.12 sobre
Windows. Para reproducir este entorno, instala primero
`python -m pip install -r requirements-lock.txt` y luego
`python -m pip install -e ".[dev]"`.

```json
{
  "question": "¿Qué hace del Mercado Central un lugar especial?",
  "top_k": 5
}
```

También puedes consultar sin servidor:

```powershell
turismo-rag ask "¿Qué puedo visitar en la Albufera?"
```

Si no activas el entorno, usa `.\.venv\Scripts\python.exe -m turismo_rag.main`
en lugar de `turismo-rag`, después de instalar el proyecto. Los comandos anteriores
`python -m src.turismo_rag.ingestion` y `python -m src.turismo_rag.chunking` siguen
funcionando desde la raíz. La instalación editable permite importar `turismo_rag`
directamente y refleja tus cambios sin reinstalar.

## API

| Método | Ruta | Uso |
|---|---|---|
| GET | `/health` | Comprueba índice, Ollama y modelos; 503 si falta alguno |
| POST | `/search` | Devuelve fragmentos y distancias sin generar una respuesta |
| POST | `/ask` | Devuelve respuesta, fuentes, citas, modelo y duración |
| GET | `/docs` | Interfaz interactiva y esquema de los endpoints |

`/search` y `/ask` aceptan `question`, `top_k` (1–10, opcional) y `category`
(opcional: `Articulos del blog`, `Artículos Wikipedia`, `Guias turisticas`).
Los campos desconocidos o preguntas vacías producen HTTP 422. Dependencias no
disponibles producen HTTP 503. Cada consulta es independiente, sin memoria de chat.

Ejemplo PowerShell que conserva los acentos:

```powershell
$consulta = @{ question = '¿Qué hace especial al Mercado Central?'; top_k = 5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/ask' -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($consulta))
```

`sources` contiene los fragmentos recuperados; `cited_sources` indica los números
que utilizó la respuesta. `grounded=true` solo significa que hay citas con números
válidos: **no garantiza que cada afirmación esté respaldada**. Si faltan citas,
son inválidas o no hay contexto, se devuelve una abstención. La distancia es coseno,
no una probabilidad de acierto. El modelo aún puede equivocarse y las fuentes
incluyen información histórica que no se actualiza automáticamente.

La configuración es para uso local. No exponer a internet tal cual: no incluye
autenticación, TLS ni límites de peticiones. Para detener el servidor usa Ctrl+C.

## Organización

```text
data/
  Documentos Fuente/       # 84 textos originales: base de conocimiento
  dataset.csv             # 812 filas de evaluación, fuera del índice
  processed/chunks.jsonl  # Fragmentos con posición y procedencia
  vector_store/           # ChromaDB y manifiesto del índice activo
  evaluation/             # Resultados y métricas de cada ejecución
src/turismo_rag/
  config.py               # Rutas y variables de entorno
  ingestion.py            # Lectura de textos
  chunking.py             # División en fragmentos
  embeddings.py           # Vectores locales con Ollama
  indexing.py             # Construcción y publicación del índice
  retrieval.py            # Búsqueda semántica
  generation.py           # Instrucciones y generación con LangChain
  pipeline.py             # Coordinación del asistente RAG
  schemas.py              # Formatos de entrada y salida
  api.py                  # FastAPI
  evaluation.py           # Evaluación del CSV
  main.py                 # Comandos de terminal
tests/                    # Pruebas sin descargar modelos
```

Es un asistente RAG con un flujo controlado de búsqueda y respuesta. No es un
sistema de múltiples agentes autónomos: esta base permite añadir decisiones y
herramientas más adelante sin mezclar responsabilidades.

## Configuración e indexación

Los valores predeterminados funcionan sin `.env`. Para cambiarlos, copia
`.env.example` a `.env` y edítalo. Usa `CHAT_MODEL` para el modelo de respuestas,
`EMBEDDING_MODEL` para embeddings y `TOP_K` para la cantidad de fragmentos.
Reinicia la API después de cambiar la configuración.

El modelo de embeddings predeterminado es EmbeddingGemma, multilingüe, con prefijos
distintos para preguntas y documentos. La división usa 1.000 caracteres y 150 de
solapamiento; se configura en `config.py`. Ejecuta `turismo-rag index` después de
cambiar documentos, fragmentación o modelo de embeddings, con la API detenida.

El índice se identifica por el contenido y la configuración. Ejecutarlo otra vez
sin cambios reutiliza los vectores; una interrupción se reanuda por lotes. Cuando
cambian los datos se crea otra colección y el manifiesto se cambia solo al terminar,
para evitar servir un índice parcial. Las colecciones anteriores se conservan y
ocupan espacio. Ejecuta una sola indexación a la vez. Si actualizas los pesos de un
modelo conservando su etiqueta, usa una nueva `COLLECTION_NAME` para reconstruir.

## Evaluación

```powershell
# Prueba pequeña de búsqueda para desarrollo, sin generar respuestas:
turismo-rag evaluate --split dev --limit 20

# Prueba pequeña de respuestas (más lenta):
turismo-rag evaluate --split dev --limit 5 --generate

# Evaluación de búsqueda en la partición reservada:
turismo-rag evaluate --split test

# Evaluación completa de las 812 filas, con respuestas:
turismo-rag evaluate --split all --generate
```

Las particiones se asignan con un hash estable de la pregunta normalizada
(aproximadamente 20 % desarrollo y 80 % prueba). Las preguntas duplicadas permanecen
en la misma partición; no se eliminan sus filas ni sus posibles referencias distintas.
El muestreo es reproducible con `--seed 42`. Ajusta parámetros con `dev` y reserva
`test` para la medición final. No ajustes modelos con el resultado de prueba si
quieres conservar esa separación.

Cada ejecución guarda un JSONL con los resultados por pregunta y un JSON de resumen:

- `source_hit_at_k`: proporción que recupera el archivo esperado entre los k fragmentos.
- `mrr_at_k`: recompensa encontrar ese archivo en posiciones anteriores.
- Con `--generate`, F1 de palabras y coincidencia exacta frente a la respuesta de referencia.
- Duración, errores, citas y tasa de abstención.

Hit y MRR verifican el archivo, no que el párrafo contenga la respuesta. F1 mide
coincidencia textual y puede penalizar una paráfrasis correcta. El contexto de
referencia se guarda para revisión manual; no se calcula una métrica semántica
de fidelidad. `grounded` tampoco sustituye esa evaluación. Los errores se registran
y cuentan como fallos de recuperación; las métricas de generación indican que
se calculan solo sobre consultas exitosas. El comando devuelve código 1 si hubo errores.
Una evaluación completa con generación puede tardar considerablemente según el equipo.

## Pruebas

```powershell
python -m pytest -q
```

Las pruebas unitarias no requieren Ollama. `/health`, la indexación y una consulta
real permiten verificar la integración local con los modelos.

## Referencias técnicas

- [Persistencia de ChromaDB](https://docs.trychroma.com/reference/python)
- [Embeddings de Ollama](https://docs.ollama.com/api/embed)
- [Prefijos de EmbeddingGemma](https://ai.google.dev/gemma/docs/embeddinggemma/inference-embeddinggemma-with-sentence-transformers)
- [ChatOllama en LangChain](https://docs.langchain.com/oss/python/integrations/chat/ollama)
- [Pruebas de FastAPI](https://fastapi.tiangolo.com/tutorial/testing/)

## Validación inicial realizada

- 84 documentos y 1.177 fragmentos indexados en ChromaDB.
- 15 pruebas automatizadas aprobadas; `pip check` no detectó conflictos.
- API comprobada por HTTP: documentación, estado, búsqueda, filtro de categoría,
  respuesta con citas, rechazo de entradas inválidas y abstención sin fuentes.
- Búsqueda sobre las 812 filas, `top_k=5`: 812 consultas exitosas, cero errores,
  archivo esperado recuperado en el 85,10 % de los casos, MRR 0,7004 y 0,243 s
  por consulta en este equipo. Es una medición inicial del conjunto completo;
  no se ajustaron parámetros con estos resultados.
- Generación: muestra de 5 preguntas de desarrollo con semilla 42, cero errores,
  F1 léxico medio 0,4334, una abstención y 10,81 s por consulta. Esta muestra pequeña
  no permite concluir la calidad global; no se generaron las 812 respuestas.

Resultados completos:

- [Resumen de búsqueda](data/evaluation/20260909T045441619945Z_all.summary.json)
- [Detalle de búsqueda](data/evaluation/20260909T045441619945Z_all.jsonl)
- [Resumen de generación](data/evaluation/20260909T045822290631Z_dev.summary.json)
- [Detalle de generación](data/evaluation/20260909T045822290631Z_dev.jsonl)
- [Ejemplo de respuesta de la API](data/evaluation/api_smoke.json)

Los resultados y la base vectorial son artefactos locales excluidos de Git.
El archivo `*.partial.jsonl` conserva una ejecución interrumpida y no forma parte
de las métricas anteriores. Las marcas de tiempo de los nombres usan UTC.
