# Conserva únicamente el motor CPU de la imagen oficial de Ollama.
FROM ollama/ollama:0.40.5 AS ollama-cpu
RUN mkdir -p /cpu/usr/bin /cpu/usr/lib/ollama \
    && cp /bin/ollama /cpu/usr/bin/ollama \
    && cp -a /usr/lib/ollama/*.so* /usr/lib/ollama/llama-server \
       /usr/lib/ollama/*LICENSE* /cpu/usr/lib/ollama/

# Ubuntu mantiene la misma versión de glibc que el binario oficial de Ollama.
FROM ubuntu:24.04
COPY --from=ollama-cpu /cpu/usr/bin/ollama /usr/bin/ollama
COPY --from=ollama-cpu /cpu/usr/lib/ollama/ /usr/lib/ollama/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=127.0.0.1:11434 \
    OLLAMA_BASE_URL=http://127.0.0.1:11434 \
    OLLAMA_MODELS=/opt/ollama/models \
    OLLAMA_NUM_PARALLEL=1 \
    OLLAMA_MAX_LOADED_MODELS=2

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libstdc++6 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
# La instalación editable mantiene config.py bajo /app/src y resuelve /app/data.
RUN pip install --no-cache-dir -e .

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /opt/ollama/models \
    && chown -R app:app /opt/ollama
USER app

# Los modelos quedan en la imagen y no se descargan al arrancar en Render.
RUN set -eu; \
    ollama serve > /tmp/ollama-build.log 2>&1 & \
    server_pid=$!; \
    trap 'kill "$server_pid" 2>/dev/null || true' EXIT; \
    for attempt in $(seq 1 60); do \
        if ollama list > /dev/null 2>&1; then break; fi; \
        sleep 1; \
    done; \
    ollama pull embeddinggemma:latest; \
    ollama pull gemma3:4b

COPY --chown=app:app data/ ./data/
RUN mkdir -p data/processed data/vector_store data/evaluation

# El índice también queda listo dentro de la imagen.
RUN set -eu; \
    ollama serve > /tmp/ollama-index.log 2>&1 & \
    server_pid=$!; \
    trap 'kill "$server_pid" 2>/dev/null || true' EXIT; \
    for attempt in $(seq 1 60); do \
        if ollama list > /dev/null 2>&1; then break; fi; \
        sleep 1; \
    done; \
    turismo-rag index

COPY --chown=app:app docker/start.sh ./docker/start.sh
EXPOSE 8000
ENTRYPOINT ["/bin/sh", "/app/docker/start.sh"]
