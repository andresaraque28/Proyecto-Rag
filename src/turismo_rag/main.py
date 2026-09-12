"""Comandos del proyecto: index, ask, evaluate y serve."""

import argparse
from contextlib import closing
import json


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Debe ser mayor que cero.")
    return number


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG local de turismo de Valencia")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("index", help="Lee documentos y crea o reanuda el índice ChromaDB")
    ask = commands.add_parser("ask", help="Consulta desde la terminal")
    ask.add_argument("question")
    ask.add_argument("--top-k", type=int, choices=range(1, 11), default=None)
    evaluation = commands.add_parser("evaluate", help="Evalúa el benchmark")
    evaluation.add_argument("--limit", type=positive_int)
    evaluation.add_argument("--generate", action="store_true", help="También genera y evalúa respuestas")
    evaluation.add_argument("--split", choices=["dev", "test", "all"], default="test")
    evaluation.add_argument("--seed", type=int, default=42)
    serve = commands.add_parser("serve", help="Inicia la API local")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        if args.command == "index":
            from .indexing import build_index
            result = build_index()
        elif args.command == "ask":
            from .pipeline import TourismAgent
            from .schemas import QuestionRequest
            with closing(TourismAgent()) as agent:
                result = agent.ask(QuestionRequest(question=args.question, top_k=args.top_k)).model_dump()
        elif args.command == "evaluate":
            from .evaluation import evaluate
            result = evaluate(limit=args.limit, generate=args.generate, split=args.split, seed=args.seed)
        else:
            import uvicorn
            uvicorn.run("turismo_rag.api:app", host=args.host, port=args.port)
            return
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "evaluate" and result["errors"]:
            raise SystemExit(1)
    except (RuntimeError, ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
