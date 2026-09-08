"""
ask_rag.py — CLI entry point: `python -m devops_assistant.rag.ask_rag "<question>"`

Runnable standalone (used directly by the GitHub Actions demo workflow) and also
designed to be wired into the main argparse CLI in devops_assistant/cli.py as an
`ask-rag` subcommand alongside the existing `ask` / `stream` / `tools-demo` commands.
See README_RAG_INTEGRATION.md for the two-line snippet to add it there.
"""

from __future__ import annotations

import argparse
import json
import sys

from devops_assistant.rag.embeddings import Embedder
from devops_assistant.rag.rag_client import ask_rag, DEFAULT_OLLAMA_MODEL
from devops_assistant.rag.retriever import Retriever
from devops_assistant.rag.vectorstore import DEFAULT_INDEX_DIR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ask-rag",
        description="Ask a DevOps question, answered using retrieved repo context.",
    )
    parser.add_argument("question", help="The question to ask")
    parser.add_argument(
        "--source",
        default="local",
        choices=["local", "github"],
        help="Where to ingest repo data from (default: local fixture data)",
    )
    parser.add_argument(
        "--sample-data-dir",
        default="sample_repo_data",
        help="Path to local fixture data (used when --source local)",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Rebuild the FAISS index before answering, even if one already exists",
    )
    parser.add_argument("-k", type=int, default=4, help="Number of chunks to retrieve")
    parser.add_argument(
        "--filter",
        dest="source_type",
        default=None,
        choices=["yaml", "pr", "commit", "doc"],
        help="Restrict retrieval to a single content type",
    )
    parser.add_argument("--model", default=DEFAULT_OLLAMA_MODEL, help="Ollama model to use")
    parser.add_argument(
        "--markdown", action="store_true", help="Print the answer as Markdown"
    )
    args = parser.parse_args(argv)

    retriever = Retriever(embedder=Embedder(), index_dir=DEFAULT_INDEX_DIR)

    needs_build = args.rebuild_index or not _index_exists()
    if needs_build:
        print("Building index from repo data...", file=sys.stderr)
        retriever.build_index(
            source=args.source, sample_data_dir=args.sample_data_dir
        )

    result = ask_rag(
        args.question,
        retriever,
        k=args.k,
        source_type=args.source_type,
        model=args.model,
    )

    if args.markdown:
        print(f"### Question\n{args.question}\n")
        print(f"### Answer\n{result['answer']}\n")
        print("### Sources")
        for s in result["sources"]:
            print(f"- `{s['path']}` ({s['source_type']}, score={s['score']:.3f})")
    else:
        print(json.dumps(result, indent=2))

    return 0


def _index_exists() -> bool:
    from devops_assistant.rag.vectorstore import VectorStore

    return VectorStore.exists(DEFAULT_INDEX_DIR)


if __name__ == "__main__":
    sys.exit(main())
