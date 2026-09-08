"""
rag_client.py — Day 13 (retriever -> prompt construction -> context injection -> Ollama)

Builds a prompt that injects retrieved chunks (with source labels) and answers via a
local Ollama model instead of the Gemini API used in the Day 7 stage. This is the
milestone where the assistant starts reasoning over the repo's actual data instead of
only general knowledge, so every answer is required to cite which file/PR/commit each
part of it came from — a generic-sounding answer with no citations is a sign
retrieval didn't actually help and should be treated as a bug, not accepted output.

Talks to Ollama's local HTTP API directly (http://localhost:11434) rather than a
Python wrapper library, to keep the dependency footprint small — matching how
client.py in the Day 7 stage talks to the Gemini API directly too.
"""

from __future__ import annotations

import json
import requests

from devops_assistant.rag.retriever import Retriever

DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_OLLAMA_MODEL = "llama3.2:1b"

SYSTEM_INSTRUCTIONS = """You are a DevOps assistant answering questions about a \
specific repository using only the retrieved context below. Rules:
- Only use the retrieved context and the question. Do not invent files, PRs, or \
commits that are not shown in the context.
- Every claim about the repo must cite its source using the exact label shown \
before each context block, e.g. (source: PR #47).
- If the retrieved context does not contain enough information to answer \
confidently, say so plainly instead of guessing.
- Keep the answer structured: Root cause, Evidence (with citations), Suggested steps.
"""


def build_prompt(question: str, retrieved_chunks: list[dict]) -> str:
    context_blocks = []
    for chunk in retrieved_chunks:
        label = f"(source: {chunk['path']})"
        context_blocks.append(f"{label}\n{chunk['text']}")
    context_text = "\n\n---\n\n".join(context_blocks)

    return (
        f"{SYSTEM_INSTRUCTIONS}\n\n"
        f"Retrieved context:\n\n{context_text}\n\n"
        f"---\n\nQuestion: {question}\n\nAnswer:"
    )


def call_ollama(
    prompt: str,
    model: str = DEFAULT_OLLAMA_MODEL,
    url: str = DEFAULT_OLLAMA_URL,
    timeout: int = 120,
) -> str:
    response = requests.post(
        url,
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("response", "").strip()


def ask_rag(
    question: str,
    retriever: Retriever,
    k: int = 4,
    source_type: str | None = None,
    model: str = DEFAULT_OLLAMA_MODEL,
) -> dict:
    """Retrieve context for the question, ask Ollama, and return answer + sources."""
    retrieved = retriever.retrieve(question, k=k, source_type=source_type)
    if not retrieved:
        return {
            "answer": (
                "No relevant context was found in the indexed repo data for this "
                "question. Try rebuilding the index or rephrasing the question."
            ),
            "sources": [],
        }

    prompt = build_prompt(question, retrieved)
    answer = call_ollama(prompt, model=model)

    return {
        "answer": answer,
        "sources": [
            {"path": r["path"], "source_type": r["source_type"], "score": r["score"]}
            for r in retrieved
        ],
    }
