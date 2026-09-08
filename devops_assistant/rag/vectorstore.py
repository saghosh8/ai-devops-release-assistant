"""
vectorstore.py — Day 11 (vector databases, FAISS, indexing, metadata filtering)

FAISS only stores vectors and returns integer positions — it has no concept of what
a chunk *is*. This module pairs a FAISS IndexFlatIP (inner product on normalized
vectors == cosine similarity) with a parallel metadata list, and persists both to
disk together so a saved index is never separated from the chunks it indexes.

IndexFlatIP/IndexFlatL2 is deliberately simple (no IVF/HNSW) — appropriate for a
single-repo, demo-scale corpus. Documented as a place to upgrade if this is ever
pointed at a much larger repo.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import faiss
import numpy as np

from devops_assistant.rag.chunking import Chunk

DEFAULT_INDEX_DIR = ".rag_cache/index"


class VectorStore:
    def __init__(self, dim: int):
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        self.metadata: list[dict] = []

    def add(self, embeddings: np.ndarray, chunks: list[Chunk]) -> None:
        if embeddings.shape[0] != len(chunks):
            raise ValueError("embeddings and chunks must be the same length")
        self.index.add(embeddings)
        self.metadata.extend(c.to_dict() for c in chunks)

    def search(self, query_embedding: np.ndarray, k: int = 4) -> list[dict]:
        query = query_embedding.reshape(1, -1).astype("float32")
        scores, indices = self.index.search(query, k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            item = dict(self.metadata[idx])
            item["score"] = float(score)
            results.append(item)
        return results

    def save(self, index_dir: str = DEFAULT_INDEX_DIR) -> None:
        path = Path(index_dir)
        path.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(path / "index.faiss"))
        with open(path / "metadata.pkl", "wb") as f:
            pickle.dump({"dim": self.dim, "metadata": self.metadata}, f)

    @classmethod
    def load(cls, index_dir: str = DEFAULT_INDEX_DIR) -> "VectorStore":
        path = Path(index_dir)
        with open(path / "metadata.pkl", "rb") as f:
            saved = pickle.load(f)
        store = cls(dim=saved["dim"])
        store.index = faiss.read_index(str(path / "index.faiss"))
        store.metadata = saved["metadata"]
        return store

    @classmethod
    def exists(cls, index_dir: str = DEFAULT_INDEX_DIR) -> bool:
        path = Path(index_dir)
        return (path / "index.faiss").exists() and (path / "metadata.pkl").exists()
