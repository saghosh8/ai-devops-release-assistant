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
               GitHub Actions demo and by tests)
  - "github" : pulls from real repos via the GitHub REST API.

Keeping both modes behind the same interface means retriever.py and rag_client.py
never need to know or care which source produced a Document.
"""

from __future__ import annotations

import json
import os
import base64
import requests
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

GITHUB_API = "https://api.github.com"


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


def _gh_headers(token: str | None) -> dict:
    token = token or os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def load_github(repo: str, token: str | None = None) -> list[Document]:
    """
    Pulls live data from a real GitHub repo: workflow YAMLs, recent PRs,
    recent commits, and README.
    """
    headers = _gh_headers(token)
    docs: list[Document] = []

    # workflow YAMLs
    try:
        resp = requests.get(
            f"{GITHUB_API}/repos/{repo}/contents/.github/workflows",
            headers=headers, timeout=15,
        )
        resp.raise_for_status()
        for item in resp.json():
            if item["type"] != "file" or not item["name"].endswith((".yml", ".yaml")):
                continue
            file_resp = requests.get(item["url"], headers=headers, timeout=15)
            file_resp.raise_for_status()
            content = base64.b64decode(file_resp.json()["content"]).decode("utf-8", "ignore")
            docs.append(Document(
                id=f"yaml:{repo}:{item['name']}",
                source_type="yaml",
                path=f"{repo}/.github/workflows/{item['name']}",
                date=None,
                text=content,
            ))
    except requests.HTTPError:
        pass

    # recent PRs
    try:
        resp = requests.get(
            f"{GITHUB_API}/repos/{repo}/pulls",
            headers=headers, params={"state": "all", "per_page": 20}, timeout=15,
        )
        resp.raise_for_status()
        for pr in resp.json():
            text = f"PR #{pr['number']}: {pr['title']}\n{pr.get('body') or ''}"
            docs.append(Document(
                id=f"pr:{repo}:{pr['number']}",
                source_type="pr",
                path=f"{repo} PR #{pr['number']}",
                date=pr.get("merged_at"),
                text=text,
            ))
    except requests.HTTPError:
        pass

    # recent commits
    try:
        resp = requests.get(
            f"{GITHUB_API}/repos/{repo}/commits",
            headers=headers, params={"per_page": 30}, timeout=15,
        )
        resp.raise_for_status()
        for c in resp.json():
            sha = c.get("sha", "")[:7]
            msg = c.get("commit", {}).get("message", "")
            docs.append(Document(
                id=f"commit:{repo}:{sha}",
                source_type="commit",
                path=f"{repo} commit {sha}",
                date=c.get("commit", {}).get("author", {}).get("date"),
                text=f"Commit {sha}: {msg}",
            ))
    except requests.HTTPError:
        pass

    # README
    try:
        resp = requests.get(f"{GITHUB_API}/repos/{repo}/readme", headers=headers, timeout=15)
        resp.raise_for_status()
        content = base64.b64decode(resp.json()["content"]).decode("utf-8", "ignore")
        docs.append(Document(
            id=f"doc:{repo}:README.md",
            source_type="doc",
            path=f"{repo}/README.md",
            date=None,
            text=content,
        ))
    except requests.HTTPError:
        pass

    return docs


def load(source: str = "local", **kwargs) -> list[Document]:
    if source == "local":
        return load_local(kwargs.get("sample_data_dir", "sample_repo_data"))
    if source == "github":
        repos = kwargs["repos"]  # list[str]
        token = kwargs.get("token")
        docs: list[Document] = []
        for repo in repos:
            docs.extend(load_github(repo, token))
        return docs
    raise ValueError(f"Unknown source: {source!r}")


GITHUB_REPOS = [
    "saghosh8/release-automation",
    "saghosh8/application-one",
    "saghosh8/application-two",
]
