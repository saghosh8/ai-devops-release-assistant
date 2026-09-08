"""
embeddings.py — Day 10 (embeddings, embedding dimensions, cosine similarity)

Wraps sentence-transformers (all-MiniLM-L6-v2 — small, free, local, runs fine on a
GitHub Actions runner's CPU). Embeddings are cached on disk keyed by a hash of the
chunk text, so re-running ingestion on unchanged content doesn't recompute anything.

The Embedder is intentionally a thin class with a swappable `model_name` so
rag_client.py / retriever.py never need to know which embedding model is in use.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_CACHE_PATH = ".rag_cache/embeddings_cache.json"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Embedder:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        cache_path: str = DEFAULT_CACHE_PATH,
    ):
        self.model_name = model_name
        self.cache_path = Path(cache_path)
        self._model = None  # lazy-loaded — keeps import fast for tests that mock this
        self._cache: dict[str, list[float]] = self._load_cache()

    def _load_cache(self) -> dict[str, list[float]]:
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache), encoding="utf-8")

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (N, D) float32 array of embeddings, using the cache where possible."""
        to_compute: list[str] = []
        to_compute_idx: list[int] = []
        vectors: list[list[float] | None] = [None] * len(texts)

        for i, text in enumerate(texts):
            key = _hash_text(text)
            if key in self._cache:
                vectors[i] = self._cache[key]
            else:
                to_compute.append(text)
                to_compute_idx.append(i)

        if to_compute:
            model = self._load_model()
            computed = model.encode(to_compute, normalize_embeddings=True)
            for idx, vec, text in zip(to_compute_idx, computed, to_compute):
                vec_list = vec.tolist()
                vectors[idx] = vec_list
                self._cache[_hash_text(text)] = vec_list
            self._save_cache()

        return np.array(vectors, dtype="float32")

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]
