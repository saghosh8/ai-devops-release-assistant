"""
Tests the retriever end-to-end (ingest -> chunk -> embed -> index -> search) using a
fake, deterministic embedder instead of sentence-transformers, so this test suite has
no model download and no network dependency. load() is monkeypatched with fixed
in-memory Documents instead of reading sample_repo_data, since ingestion now pulls
from live GitHub repos.
"""

import re
import numpy as np

from devops_assistant.rag.embeddings import Embedder
from devops_assistant.rag.ingest import Document
from devops_assistant.rag.retriever import Retriever

VOCAB = [
    "docker",
    "build",
    "node",
    "kubectl",
    "deploy",
    "eks",
    "retry",
    "package",
    "lock",
    "workflow",
]

FIXTURE_DOCS = [
    Document(
        id="pr:47",
        source_type="pr",
        path="PR #47",
        date="2026-01-01",
        text="PR #47: Fix docker build failing on node:20 base image\n"
             "Files changed: Dockerfile, package-lock.json",
    ),
    Document(
        id="pr:52",
        source_type="pr",
        path="PR #52",
        date="2026-01-05",
        text="PR #52: Add retry logic for flaky deploy step\n"
             "Files changed: deploy.yml",
    ),
    Document(
        id="doc:deployment_notes.md",
        source_type="doc",
        path="deployment_notes.md",
        date=None,
        text="Deployment notes: workflow uses kubectl to deploy to eks after docker build.",
    ),
    Document(
        id="yaml:deploy.yml",
        source_type="yaml",
        path=".github/workflows/deploy.yml",
        date=None,
        text="name: deploy\non: push\njobs:\n  build:\n    steps:\n      - run: docker build .",
    ),
]


class FakeEmbedder(Embedder):
    """Deterministic bag-of-words embedding — no model download, but still lets
    retrieval tests check that relevant content scores higher than irrelevant
    content for a given query."""

    def __init__(self):
        # Skip the real Embedder.__init__ (no cache file needed for this fake).
        self.model_name = "fake"
        self._cache = {}
        self.cache_path = None

    def embed(self, texts):
        vectors = []
        for text in texts:
            words = re.findall(r"[a-z]+", text.lower())
            vec = np.array([words.count(w) for w in VOCAB], dtype="float32")
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec)
        return np.array(vectors, dtype="float32")


def _build_retriever_with_fixtures(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "devops_assistant.rag.retriever.load",
        lambda source=None, **kwargs: FIXTURE_DOCS,
    )
    index_dir = str(tmp_path / "index")
    retriever = Retriever(embedder=FakeEmbedder(), index_dir=index_dir)
    retriever.build_index()
    return retriever


def test_retriever_ranks_relevant_content_first(tmp_path, monkeypatch):
    retriever = _build_retriever_with_fixtures(tmp_path, monkeypatch)

    results = retriever.retrieve("why is my docker build failing with node", k=3)

    assert len(results) == 3
    top_paths = [r["path"] for r in results]
    # The Dockerfile/node-related PR and docs should outrank the unrelated retry PR.
    assert any("47" in p or "deployment_notes" in p or "workflow" in p.lower()
               for p in top_paths)


def test_retriever_source_type_filter(tmp_path, monkeypatch):
    retriever = _build_retriever_with_fixtures(tmp_path, monkeypatch)

    results = retriever.retrieve("deploy", k=5, source_type="pr")
    assert all(r["source_type"] == "pr" for r in results)
