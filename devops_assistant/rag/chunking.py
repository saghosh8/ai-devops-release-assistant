"""
chunking.py — Day 10 (chunking, chunk size, chunk overlap)

Splits each Document into one or more Chunks. Two rules that matter more than the
exact size number:

  1. Never split a YAML file mid-block — split on top-level `jobs:`/`steps:`
     boundaries (or not at all, if it's short, which our fixtures are). A half-YAML
     chunk retrieved out of context can actively mislead the model.
  2. Never split a PR/commit/doc across an unrelated boundary — split on blank
     lines / paragraphs, never mid-sentence.

For fixture-sized content (a few hundred words per document) most documents will
end up as a single chunk. The chunking logic below still applies real token-based
limits so it behaves correctly once real, longer repo content is ingested via
ingest.load_github() later.
"""

from __future__ import annotations

from dataclasses import dataclass

from devops_assistant.rag.ingest import Document

# Simple whitespace-token approximation — avoids a tiktoken dependency for a
# demo-scale project. Swap for a real tokenizer if you start ingesting large docs.
DEFAULT_MAX_TOKENS = 400
DEFAULT_OVERLAP_TOKENS = 60


@dataclass
class Chunk:
    id: str
    source_type: str
    path: str
    date: str | None
    text: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "path": self.path,
            "date": self.date,
            "text": self.text,
        }


def _token_count(text: str) -> int:
    return len(text.split())


def _split_paragraphs(text: str) -> list[str]:
    # Blank-line-separated blocks — a safe boundary for markdown/PR text.
    parts = [p.strip() for p in text.split("\n\n")]
    return [p for p in parts if p]


def _chunk_paragraphs(
    paragraphs: list[str], max_tokens: int, overlap_tokens: int
) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = _token_count(para)
        if current and current_tokens + para_tokens > max_tokens:
            chunks.append("\n\n".join(current))
            # carry the tail of the previous chunk forward as overlap
            overlap: list[str] = []
            overlap_count = 0
            for p in reversed(current):
                overlap_count += _token_count(p)
                overlap.insert(0, p)
                if overlap_count >= overlap_tokens:
                    break
            current = overlap
            current_tokens = overlap_count
        current.append(para)
        current_tokens += para_tokens

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_document(
    doc: Document,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    if doc.source_type == "yaml":
        # Keep workflow YAML intact — splitting mid-job/step produces broken,
        # misleading fragments. Only split if it genuinely exceeds max_tokens.
        if _token_count(doc.text) <= max_tokens:
            pieces = [doc.text]
        else:
            pieces = _chunk_paragraphs(
                _split_paragraphs(doc.text), max_tokens, overlap_tokens
            )
    else:
        pieces = _chunk_paragraphs(
            _split_paragraphs(doc.text), max_tokens, overlap_tokens
        )
        if not pieces:
            pieces = [doc.text]

    return [
        Chunk(
            id=f"{doc.id}#{i}",
            source_type=doc.source_type,
            path=doc.path,
            date=doc.date,
            text=piece,
        )
        for i, piece in enumerate(pieces)
    ]


def chunk_documents(
    docs: list[Document],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in docs:
        chunks.extend(chunk_document(doc, max_tokens, overlap_tokens))
    return chunks
