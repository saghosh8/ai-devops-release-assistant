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

Pulls real repo content (workflow YAMLs, PRs, commits, README) via the GitHub
REST API. retriever.py and rag_client.py only ever see Document objects and
don't need to know how they were produced.
"""

from __future__ import annotations

import os
import base64
import requests
from dataclasses import dataclass, asdict

GITHUB_API = "https://api.github.com"

GITHUB_REPOS = [
    "saghosh8/release-automation",
    "saghosh8/application-one",
    "saghosh8/application-two",
]


@dataclass
class Document:
    id: str
    source_type: str
    path: str
    date: str | None
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


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


def load(source: str = "github", **kwargs) -> list[Document]:
    if source == "github":
        repos = kwargs.get("repos", GITHUB_REPOS)
        token = kwargs.get("token")
        docs: list[Document] = []
        for repo in repos:
            docs.extend(load_github(repo, token))
        return docs
    raise ValueError(f"Unknown source: {source!r}")
