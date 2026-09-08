"""
ingest.py — Day 9 (document loaders, cleaning, metadata)

Loads content into a common Document shape:
    {
        "id": str,
        "source_type": "yaml" | "pr" | "commit" | "doc",
        "path": str,            # file path or PR/commit identifier
        "date": str | None,     # ISO date if known, for recency filtering later
        "text": str,            # the actual content to embed
    }

Two sources are supported:
  - "local"  : reads from sample_repo_data/ (deterministic, offline, used by the
               GitHub Actions demo and by tests — this is the only mode that works
               without a GitHub token or live network access)
  - "github" : (stub) pulls from a real repo via the GitHub REST API. Left as a
               documented extension point — not required for the demo, since we
               only have GitHub Actions to show this in and don't want the demo's
               correctness to depend on live API rate limits or a token secret.

Keeping both modes behind the same interface means retriever.py and rag_client.py
never need to know or care which source produced a Document.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


@dataclass
class Document:
    id: str
    source_type: str
    path: str
    date: str | None
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def _read_yaml_docs(base: Path) -> Iterable[Document]:
    workflows_dir = base / "workflows"
    if not workflows_dir.exists():
        return
    for yml_path in sorted(workflows_dir.glob("*.yml")):
        text = yml_path.read_text(encoding="utf-8")
        yield Document(
            id=f"yaml:{yml_path.name}",
            source_type="yaml",
            path=f".github/workflows/{yml_path.name}",
            date=None,
            text=text,
        )


def _read_pr_docs(base: Path) -> Iterable[Document]:
    prs_dir = base / "prs"
    if not prs_dir.exists():
        return
    for pr_path in sorted(prs_dir.glob("*.json")):
        pr = json.loads(pr_path.read_text(encoding="utf-8"))
        text = (
            f"PR #{pr['number']}: {pr['title']}\n"
            f"Files changed: {', '.join(pr.get('files_changed', []))}\n"
            f"{pr.get('description', '')}"
        )
        yield Document(
            id=f"pr:{pr['number']}",
            source_type="pr",
            path=f"PR #{pr['number']}",
            date=pr.get("merged_at"),
            text=text,
        )


def _read_commit_docs(base: Path) -> Iterable[Document]:
    commits_path = base / "commits" / "commits.json"
    if not commits_path.exists():
        return
    commits = json.loads(commits_path.read_text(encoding="utf-8"))
    for c in commits:
        text = (
            f"Commit {c['sha']}: {c['message']}\n"
            f"Files changed: {', '.join(c.get('files_changed', []))}"
        )
        yield Document(
            id=f"commit:{c['sha']}",
            source_type="commit",
            path=f"commit {c['sha']}",
            date=c.get("date"),
            text=text,
        )


def _read_doc_docs(base: Path) -> Iterable[Document]:
    docs_dir = base / "docs"
    if not docs_dir.exists():
        return
    for doc_path in sorted(docs_dir.glob("*.md")):
        text = doc_path.read_text(encoding="utf-8")
        yield Document(
            id=f"doc:{doc_path.name}",
            source_type="doc",
            path=doc_path.name,
            date=None,
            text=text,
        )


def load_local(sample_data_dir: str = "sample_repo_data") -> list[Document]:
    """Load all fixture documents from a local sample_repo_data directory."""
    base = Path(sample_data_dir)
    if not base.exists():
        raise FileNotFoundError(
            f"sample_repo_data directory not found at '{base}'. "
            "Run this from the repo root, or pass --sample-data-dir."
        )
    docs: list[Document] = []
    docs.extend(_read_yaml_docs(base))
    docs.extend(_read_pr_docs(base))
    docs.extend(_read_commit_docs(base))
    docs.extend(_read_doc_docs(base))
    return docs


def load_github(repo: str, token: str | None = None) -> list[Document]:
    """
    Stub for pulling live data from a real GitHub repo (workflow YAML, recent PRs,
    commits, docs) via the REST API. Not wired into the demo — the Actions demo and
    tests use load_local() so the pipeline is deterministic and doesn't need a
    GITHUB_TOKEN secret or live rate-limit budget to run reliably in CI.

    Implement this the same way client.py in the Day 7 stage handles auth/retries,
    if/when this becomes needed for a real target repo.
    """
    raise NotImplementedError(
        "Live GitHub ingestion is a documented future extension — "
        "the demo and tests use load_local() instead."
    )


def load(source: str = "local", **kwargs) -> list[Document]:
    if source == "local":
        return load_local(kwargs.get("sample_data_dir", "sample_repo_data"))
    if source == "github":
        return load_github(kwargs["repo"], kwargs.get("token"))
    raise ValueError(f"Unknown source: {source!r}")
