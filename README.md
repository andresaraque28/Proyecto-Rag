# Turismo Valencia RAG

Asistente local que consulta los documentos de `data/Documentos Fuente`, busca
fragmentos en ChromaDB y responde con Ollama mediante LangChain. FastAPI expone
el servicio. No requiere claves de API ni servicios de pago; utiliza los recursos
de tu equipo. La descarga inicial de dependencias y modelos requiere internet.

## Inicio rápido (PowerShell)

Desde la raíz del proyecto, con Python 3.12 y Ollama instalados:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-lock.txt
python -m pip install -e ".[dev]"
ollama pull embeddinggemma:latest
ollama pull gemma3:1b
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

## Docker

La imagen incluye Ollama, `embeddinggemma:latest`, `gemma3:1b`, los documentos y
el índice ChromaDB, de modo que el contenedor arranca sin descargar modelos ni
volver a calcular embeddings: al servir solo se genera el embedding de cada
pregunta. La construcción necesita internet y puede tardar bastante. La imagen
ocupa unos 3,7 GB. Para ejecutarla localmente:

```powershell
docker build --platform linux/amd64 -t turismo-rag:demo .
docker run --rm --name turismo-rag -p 127.0.0.1:8000:8000 turismo-rag:demo
```

Abre `http://127.0.0.1:8000/health` para verificar Ollama, los modelos y el
índice, y `http://127.0.0.1:8000/docs` para hacer consultas. No hace falta
instalar Ollama en el equipo que ejecuta este contenedor.

Para probar otro modelo de chat, pásalo al construir:
`docker build --build-arg CHAT_MODEL=gemma3:4b -t turismo-rag:demo .`

Las capas están ordenadas para aprovechar la caché: los modelos se descargan
antes de copiar el código, así que un cambio en `src/` o en `data/` no los vuelve
a descargar, aunque sí regenera el índice. Cambiar `CHAT_MODEL` repite la descarga.

`processed/`, `vector_store/` y `evaluation/` se crean dentro de la imagen y no
aparecen en la carpeta del proyecto. Para inspeccionarlos:
`docker run --rm --entrypoint sh turismo-rag:demo -c "ls -R /app/data/vector_store"`.

Si el contenedor falla con `set: Illegal option -`, `docker/start.sh` tiene finales
de línea de Windows (CRLF). `.gitattributes` fuerza LF para `*.sh` y el `Dockerfile`;
si el archivo ya estaba descargado, ejecuta `git add --renormalize .` y vuelve a
extraerlo, o conviértelo a LF en el editor, y reconstruye la imagen.

### Publicación y despliegue en Render

El flujo `.github/workflows/docker.yml` construye la imagen y la publica en
`ghcr.io/andresaraque28/proyecto-rag:latest` en cada push a `main` que cambie
el código, los datos o el `Dockerfile` (también se lanza a mano desde
**Actions → Docker → Run workflow**). Los modelos y el índice se generan en
GitHub, no en Render, y la caché del registro evita repetirlos cuando solo
cambia el código.

1. Tras la primera ejecución, en GitHub abre **Packages → proyecto-rag →
   Package settings** y cámbialo a **Public**, o registra en Render una
   credencial de GHCR con un token que tenga `read:packages`.
2. En Render crea un **Web Service** con **Existing Image** y la URL
   `ghcr.io/andresaraque28/proyecto-rag:latest`. Sin comando de inicio
   personalizado ni disco persistente; comprobación de salud en `/health`.
3. Copia el **Deploy Hook** del servicio y guárdalo en GitHub como secreto
   `RENDER_DEPLOY_HOOK_URL`. Cada imagen publicada lanzará un despliegue.

Con `gemma3:1b` y `embeddinggemma` cargados, el contenedor usa unos 2 GB de RAM:
elige un plan de al menos 2 GB, mejor 4 GB para dejar margen. El plan gratuito
de 512 MB no alcanza. Render asigna `PORT` y el contenedor escucha en ese
puerto. La URL pública termina en `.onrender.com`.

Los modelos y el índice están en la imagen, de modo que un reinicio no exige
descargarlos ni volver a indexar. Cuando cambien los documentos o el modelo de
embeddings, el flujo reconstruye la imagen. El tamaño del plan no garantiza la
velocidad: comprueba una respuesta real con anticipación.

La API no tiene autenticación ni límite de solicitudes. Para una demostración
pública, comparte la URL solo durante el evento y retira el servicio después.
El archivo `.env` se excluye de la imagen.

## API

| Método | Ruta | Uso |
|---|---|---|
| GET | `/health` | Comprueba índice, Ollama y modelos; 503 si falta alguno |
| POST | `/search` | Devuelve fragmentos y distancias sin generar una respuesta |
| POST | `/ask` | Devuelve respuesta, fuentes, citas, modelo y duración |
| GET | `/docs` | Interfaz interactiva y esquema de los endpoints |

`/search` y `/ask` aceptan `question`, `top_k` (1–10, opcional) y `category`
(opcional: `Articulos del blog`, `Artículos Wikipedia`, `Guias turisticas`).
En `/docs`, borra la línea `category` del ejemplo o elige uno de esos valores;
cualquier otro valor produce HTTP 422. Los campos desconocidos o preguntas vacías producen HTTP 422. Dependencias no
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

### Registro de la aplicación (`app.log`)

La aplicación escribe una línea JSON por evento en stdout (los **Logs** de Render)
y en `data/logs/app.log`. El archivo rota a los 5 MB y conserva tres copias
(`app.log.1` a `app.log.3`). Cambia la ruta con `LOG_FILE`; vacía la variable
(`LOG_FILE=`) para escribir solo en stdout.

| Evento | Origen | Campos principales |
|---|---|---|
| `search` | `/search` | pregunta, categoría, archivos recuperados, distancia mínima |
| `ask` | `/ask` | `request_id`, pregunta, modelo, `grounded`, citas, archivos, distancia mínima, duración |
| `ask_judged` | `/ask` con `JUDGE_REQUESTS=true` | mismo `request_id`, `hallucinated`, `hallucination_rate`, afirmaciones sin respaldo |
| `evaluation_run` | `turismo-rag evaluate` | la misma línea que se añade a `runs.jsonl` |

Los errores internos de la API también quedan en el archivo, con nivel `ERROR`
y la traza en `exception`. El juez de `ask_judged` revisa la respuesta después de
enviarla: no la retrasa, pero ocupa CPU en la misma instancia.

Las preguntas de la API no tienen respuesta de referencia, así que solo se mide la
alucinación, no el acierto; por eso no se añaden a `runs.jsonl`. Para revisar el
archivo desde PowerShell:

```powershell
Get-Content data/logs/app.log -Wait          # seguir los eventos en vivo
Get-Content data/logs/app.log | ConvertFrom-Json |
  Where-Object event -eq 'ask_judged' | Format-Table time, hallucinated, hallucination_rate
```

En Docker el archivo está en `/app/data/logs/app.log`. Para conservarlo al detener
el contenedor, monta una carpeta: `-v ${PWD}/data/logs:/app/data/logs`. En Render el
disco no es persistente; usa sus **Logs**, que reciben las mismas líneas. El
registro incluye las preguntas de los usuarios.

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
  judge.py                # Juez LLM de alucinación y acierto
  monitoring.py           # Registro JSON en stdout y data/logs/app.log
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
`JUDGE_MODEL`, `JUDGE_REQUESTS` y `LOG_FILE` controlan el juez de
alucinación y el registro (ver [Evaluación](#evaluación) y
[Registro de la aplicación](#registro-de-la-aplicación-applog)). Reinicia la API después de
cambiar la configuración.

`gemma3:1b` es el modelo predeterminado porque cabe en instancias pequeñas. Los
modelos pequeños tienden a omitir las citas, y una respuesta sin citas válidas se
convierte en abstención; por eso `generation.py` repite al final de cada consulta
la instrucción de citar. `gemma3:4b` responde mejor si el equipo lo permite.

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

# Alucinación y acierto con un juez LLM (implica --generate):
$env:JUDGE_MODEL = 'gemma3:4b'
turismo-rag evaluate --split dev --limit 20 --judge
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
- Con `--judge`, un modelo de Ollama (`JUDGE_MODEL`, o `CHAT_MODEL` si no se define)
  revisa cada respuesta:
  - `hallucination_response_rate`: proporción de respuestas con al menos una
    afirmación que los fragmentos recuperados no respaldan.
  - `mean_claim_hallucination_rate`: proporción media de afirmaciones sin respaldo.
  - `correctness_score` y `correct_rate`: acierto frente a la referencia
    (correcta = 1, parcial = 0,5, incorrecta o abstención = 0).
  - `judge_errors`: veces que el juez no devolvió JSON válido; esas filas no cuentan.

  Por pregunta, el JSONL guarda `faithfulness` (afirmaciones sin respaldo) y
  `correctness` (veredicto y motivo). Las abstenciones no se juzgan por alucinación.

Además, cada ejecución añade una línea a `data/evaluation/runs.jsonl` con sus
métricas principales, modelos y archivo de resultados. Sirve para comparar
ejecuciones, por ejemplo `gemma3:1b` frente a `gemma3:4b`:

```powershell
Get-Content data/evaluation/runs.jsonl | ConvertFrom-Json |
  Format-Table run, chat_model, judge_model, hallucination_response_rate, correctness_score
```

Hit y MRR verifican el archivo, no que el párrafo contenga la respuesta. F1 mide
coincidencia textual y puede penalizar una paráfrasis correcta. El contexto de
referencia se guarda para revisión manual. El juez es otro modelo y también se
equivoca: con `gemma3:1b` como juez los resultados son poco fiables, y juzgar un
modelo consigo mismo tiende a ser indulgente. Úsalo para comparar configuraciones,
no como verificación factual. `grounded` no sustituye esa evaluación. Los errores se registran
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
- 19 pruebas automatizadas aprobadas; `pip check` no detectó conflictos.
- API comprobada por HTTP: documentación, estado, búsqueda, filtro de categoría,
  respuesta con citas, rechazo de entradas inválidas y abstención sin fuentes.
- Búsqueda sobre las 812 filas, `top_k=5`: 812 consultas exitosas, cero errores,
  archivo esperado recuperado en el 85,10 % de los casos, MRR 0,7004 y 0,243 s
  por consulta en este equipo. Es una medición inicial del conjunto completo;
  no se ajustaron parámetros con estos resultados.
- Generación con `gemma3:4b`: muestra de 5 preguntas de desarrollo con semilla 42,
  cero errores, F1 léxico medio 0,4334, una abstención y 10,81 s por consulta. Esta
  muestra pequeña no permite concluir la calidad global; no se generaron las 812
  respuestas.
- Generación con `gemma3:1b` y juez `gemma3:4b`: 10 preguntas de desarrollo con
  semilla 42, cero errores, 10 % de respuestas con alguna afirmación sin respaldo,
  1 % de afirmaciones sin respaldo, acierto 0,40 frente a la referencia, ninguna
  abstención y 10,42 s por consulta. El modelo pequeño rara vez inventa, pero suele
  responder solo una parte de la pregunta.
- Imagen Docker con `gemma3:1b`: 3,7 GB; unos 1,9 GB de RAM con ambos modelos
  cargados y entre 8 y 16 s por respuesta en CPU en este equipo.

Resultados completos:

- [Resumen de búsqueda](data/evaluation/20260909T045441619945Z_all.summary.json)
- [Detalle de búsqueda](data/evaluation/20260909T045441619945Z_all.jsonl)
- [Resumen de generación](data/evaluation/20260909T045822290631Z_dev.summary.json)
- [Detalle de generación](data/evaluation/20260909T045822290631Z_dev.jsonl)
- [Ejemplo de respuesta de la API](data/evaluation/api_smoke.json)

Los resultados y la base vectorial son artefactos locales excluidos de Git.
El archivo `*.partial.jsonl` conserva una ejecución interrumpida y no forma parte
de las métricas anteriores. Las marcas de tiempo de los nombres usan UTC.

## 9. Integración continua y validación de entradas

El proyecto incluye un workflow de GitHub Actions en
`.github/workflows/ci.yml`. Se ejecuta en cada `push` y `pull_request` usando
Python 3.12 y realiza estas comprobaciones:

1. Instala el proyecto y sus dependencias de desarrollo.
2. Ejecuta Ruff sobre `src` y `tests` para detectar errores de calidad del código.
3. Ejecuta toda la suite automatizada con pytest.

Un segundo workflow, `.github/workflows/docker.yml`, publica la imagen en GHCR
para Render (ver [Publicación y despliegue en Render](#publicación-y-despliegue-en-render)).

Las versiones de las herramientas de desarrollo están fijadas en
`pyproject.toml` para que las comprobaciones sean reproducibles:

Para ejecutar localmente las mismas comprobaciones:

```powershell
python -m pip install -e ".[dev]"
ruff check src tests
python -m pytest -q
```

Las entradas de `/ask` y `/search` se validan mediante `QuestionRequest` en
`src/turismo_rag/schemas.py`. El sistema rechaza con HTTP 422:

- Preguntas vacías, demasiado cortas o compuestas únicamente por símbolos.
- Preguntas que contienen caracteres de control.
- Categorías distintas de las tres carpetas de `data/Documentos Fuente`.
- Valores de `top_k` fuera del rango permitido de 1 a 10.
- Campos desconocidos que no forman parte del formato de la petición.

Estas reglas se cubren mediante pruebas en `tests/test_rag.py`. La validación
ocurre antes de acceder a ChromaDB, Ollama o al modelo de generación.
