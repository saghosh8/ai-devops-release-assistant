"""
retriever.py — Day 12 (top-K, similarity search, retrieval quality)

Wraps an Embedder + VectorStore behind a single retrieve(query, k) call. Supports an
optional source_type filter (e.g. "only search PRs") because DevOps questions often
implicitly scope themselves — "why did the workflow fail" is really a YAML + recent
commits question, not a docs question.

Hybrid search / reranking are deliberately not implemented here — noted as a future
improvement rather than built, to keep this milestone's scope honest (same spirit as
the Day 7 README's design notes about not overbuilding a demo project).
"""

from __future__ import annotations

from devops_assistant.rag.chunking import chunk_documents
from devops_assistant.rag.embeddings import Embedder
from devops_assistant.rag.ingest import load
from devops_assistant.rag.vectorstore import VectorStore, DEFAULT_INDEX_DIR


class Retriever:
    def __init__(self, embedder: Embedder | None = None, index_dir: str = DEFAULT_INDEX_DIR):
        self.embedder = embedder or Embedder()
        self.index_dir = index_dir
        self._store: VectorStore | None = None

    def build_index(self, source: str = "local", **ingest_kwargs) -> None:
        """Ingest -> chunk -> embed -> build a fresh FAISS index, then persist it."""
        docs = load(source=source, **ingest_kwargs)
        chunks = chunk_documents(docs)
        if not chunks:
            raise ValueError("No chunks produced from ingested documents.")

        texts = [c.text for c in chunks]
        vectors = self.embedder.embed(texts)

        store = VectorStore(dim=vectors.shape[1])
        store.add(vectors, chunks)
        store.save(self.index_dir)
        self._store = store

    def _load_store(self) -> VectorStore:
        if self._store is not None:
            return self._store
        if not VectorStore.exists(self.index_dir):
            raise RuntimeError(
                "No index found. Call build_index() first "
                "(or run `ask-rag --rebuild-index`)."
            )
        self._store = VectorStore.load(self.index_dir)
        return self._store

    def retrieve(
        self, query: str, k: int = 4, source_type: str | None = None
    ) -> list[dict]:
        store = self._load_store()
        query_vec = self.embedder.embed_one(query)

        # Over-fetch when filtering, since a source_type filter is applied after
        # the similarity search on this small, flat-index scale.
        fetch_k = k * 4 if source_type else k
        results = store.search(query_vec, k=fetch_k)

        if source_type:
            results = [r for r in results if r["source_type"] == source_type]

        return results[:k]
