#!/bin/sh
set -eu

ollama serve &
ollama_pid=$!
api_pid=

stop() {
    if [ -n "$api_pid" ]; then
        kill "$api_pid" 2>/dev/null || true
    fi
    kill "$ollama_pid" 2>/dev/null || true
}
trap stop INT TERM EXIT

for attempt in $(seq 1 60); do
    if ollama list >/dev/null 2>&1; then
        break
    fi
    if ! kill -0 "$ollama_pid" 2>/dev/null; then
        echo 'Ollama terminó durante el arranque.' >&2
        exit 1
    fi
    sleep 1
done

if ! ollama list >/dev/null 2>&1; then
    echo 'Ollama no respondió durante el arranque.' >&2
    exit 1
fi

turismo-rag serve --host 0.0.0.0 --port "${PORT:-8000}" &
api_pid=$!
wait "$api_pid"
