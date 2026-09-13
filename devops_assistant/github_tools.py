"""
github_tools.py — Day 16 (tool-use against a real external API)

Real, callable GitHub REST API tools the agent (agent.py) can reach for. Split
deliberately into two trust tiers:

  - READ tools (list/get PRs, issues, workflow runs, jobs, logs, commits) are
    always safe to call — they never mutate anything, so the agent can call
    them freely while planning.

  - WRITE tools (re-running a workflow, commenting on an issue/PR) touch the
    real repo. Per the roadmap, these only ever execute behind an *explicit*
    human-approval gate: every write tool takes `approved: bool = False` and
    raises ApprovalRequiredError unless the caller (a human, via the CLI's
    `--approve-writes` flag, or an MCP client's own confirmation step) has
    explicitly set it True for *that specific call*. The agent itself is
    never allowed to set approved=True on its own — see agent.py, which never
    passes that kwarg. This is the concrete mitigation for OWASP LLM08
    (Excessive Agency): the model can *propose* an action, it cannot *commit*
    one.

Every function is a plain, type-hinted, docstringed Python function so it can
also be handed straight to Gemini's automatic function-calling (as tools.py's
get_utc_time already demonstrates) or wrapped as an MCP tool (mcp_server.py) —
one implementation, three call sites.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

import requests

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 15


class GitHubToolError(Exception):
    """Raised for any GitHub API failure we want callers to handle cleanly."""


class ApprovalRequiredError(GitHubToolError):
    """Raised when a write action is attempted without approved=True."""


def _headers(token: Optional[str] = None) -> dict:
    token = token or os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(path: str, params: Optional[dict] = None, token: Optional[str] = None) -> dict | list:
    try:
        resp = requests.get(
            f"{GITHUB_API}{path}", headers=_headers(token), params=params, timeout=DEFAULT_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        raise GitHubToolError(f"GitHub API GET {path} failed: {e}") from e
    except requests.RequestException as e:
        raise GitHubToolError(f"GitHub API GET {path} could not complete: {e}") from e


def _require_approval(action: str, approved: bool, details: dict) -> None:
    if not approved:
        raise ApprovalRequiredError(
            f"'{action}' is a write action against a real repo and was NOT executed. "
            f"Re-call with approved=True only after a human has explicitly confirmed it. "
            f"Proposed action: {details}"
        )


# --- Read tools --------------------------------------------------------------


def list_pull_requests(repo: str, state: str = "open", per_page: int = 10) -> list[dict]:
    """List pull requests for a GitHub repo.

    Args:
        repo: "owner/name", e.g. "saghosh8/application-one".
        state: "open", "closed", or "all".
        per_page: max number of PRs to return (most recent first).
    """
    data = _get(f"/repos/{repo}/pulls", params={"state": state, "per_page": per_page})
    return [
        {
            "number": pr["number"],
            "title": pr["title"],
            "state": pr["state"],
            "user": pr.get("user", {}).get("login"),
            "created_at": pr.get("created_at"),
            "merged_at": pr.get("merged_at"),
            "url": pr.get("html_url"),
        }
        for pr in data
    ]


def get_pull_request(repo: str, number: int) -> dict:
    """Get full details (including changed-files stats) for one pull request."""
    pr = _get(f"/repos/{repo}/pulls/{number}")
    files = _get(f"/repos/{repo}/pulls/{number}/files", params={"per_page": 100})
    return {
        "number": pr["number"],
        "title": pr["title"],
        "body": pr.get("body") or "",
        "state": pr["state"],
        "user": pr.get("user", {}).get("login"),
        "additions": pr.get("additions"),
        "deletions": pr.get("deletions"),
        "changed_files": pr.get("changed_files"),
        "created_at": pr.get("created_at"),
        "merged_at": pr.get("merged_at"),
        "url": pr.get("html_url"),
        "files": [{"filename": f["filename"], "additions": f["additions"], "deletions": f["deletions"]}
                  for f in files],
    }


def list_issues(repo: str, state: str = "open", per_page: int = 10) -> list[dict]:
    """List issues for a GitHub repo (pull requests are excluded)."""
    data = _get(f"/repos/{repo}/issues", params={"state": state, "per_page": per_page})
    return [
        {
            "number": i["number"],
            "title": i["title"],
            "state": i["state"],
            "user": i.get("user", {}).get("login"),
            "created_at": i.get("created_at"),
            "labels": [l["name"] for l in i.get("labels", [])],
            "url": i.get("html_url"),
        }
        for i in data
        if "pull_request" not in i
    ]


def get_issue(repo: str, number: int) -> dict:
    """Get full details for one issue, including its body."""
    i = _get(f"/repos/{repo}/issues/{number}")
    return {
        "number": i["number"],
        "title": i["title"],
        "body": i.get("body") or "",
        "state": i["state"],
        "labels": [l["name"] for l in i.get("labels", [])],
        "url": i.get("html_url"),
    }


def list_workflow_runs(repo: str, status: Optional[str] = None, per_page: int = 10) -> list[dict]:
    """List recent GitHub Actions workflow runs for a repo.

    Args:
        status: optional filter, e.g. "completed", "failure", "in_progress".
    """
    params = {"per_page": per_page}
    if status:
        params["status"] = status
    data = _get(f"/repos/{repo}/actions/runs", params=params)
    return [
        {
            "id": r["id"],
            "name": r.get("name"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "head_branch": r.get("head_branch"),
            "head_sha": r.get("head_sha"),
            "event": r.get("event"),
            "created_at": r.get("created_at"),
            "url": r.get("html_url"),
        }
        for r in data.get("workflow_runs", [])
    ]


def get_workflow_run(repo: str, run_id: int) -> dict:
    """Get details for one workflow run."""
    r = _get(f"/repos/{repo}/actions/runs/{run_id}")
    return {
        "id": r["id"],
        "name": r.get("name"),
        "status": r.get("status"),
        "conclusion": r.get("conclusion"),
        "head_branch": r.get("head_branch"),
        "head_sha": r.get("head_sha"),
        "run_attempt": r.get("run_attempt"),
        "created_at": r.get("created_at"),
        "url": r.get("html_url"),
    }


def get_workflow_run_jobs(repo: str, run_id: int) -> list[dict]:
    """Get the jobs (and their steps) for one workflow run — this is where a
    failing step actually shows up."""
    data = _get(f"/repos/{repo}/actions/runs/{run_id}/jobs")
    return [
        {
            "id": j["id"],
            "name": j["name"],
            "status": j.get("status"),
            "conclusion": j.get("conclusion"),
            "steps": [
                {"name": s["name"], "status": s.get("status"), "conclusion": s.get("conclusion"),
                 "number": s.get("number")}
                for s in j.get("steps", [])
            ],
        }
        for j in data.get("jobs", [])
    ]


def get_job_logs(repo: str, job_id: int, token: Optional[str] = None, max_chars: int = 20000) -> str:
    """Fetch the raw log text for one job. Truncated to max_chars from the end
    (the failure is almost always in the tail of the log, not the head)."""
    try:
        resp = requests.get(
            f"{GITHUB_API}/repos/{repo}/actions/jobs/{job_id}/logs",
            headers=_headers(token), timeout=DEFAULT_TIMEOUT, allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise GitHubToolError(f"Could not fetch logs for job {job_id}: {e}") from e
    except requests.RequestException as e:
        raise GitHubToolError(f"Could not fetch logs for job {job_id}: {e}") from e
    text = resp.text
    return text[-max_chars:] if len(text) > max_chars else text


def get_commit(repo: str, sha: str) -> dict:
    """Get details for one commit."""
    c = _get(f"/repos/{repo}/commits/{sha}")
    return {
        "sha": c["sha"][:7],
        "message": c.get("commit", {}).get("message", ""),
        "author": c.get("commit", {}).get("author", {}).get("name"),
        "date": c.get("commit", {}).get("author", {}).get("date"),
        "files": [{"filename": f["filename"], "additions": f["additions"], "deletions": f["deletions"]}
                  for f in c.get("files", [])],
    }


def list_recent_commits(repo: str, per_page: int = 10) -> list[dict]:
    """List recent commits on a repo's default branch."""
    data = _get(f"/repos/{repo}/commits", params={"per_page": per_page})
    return [
        {
            "sha": c.get("sha", "")[:7],
            "message": c.get("commit", {}).get("message", ""),
            "date": c.get("commit", {}).get("author", {}).get("date"),
        }
        for c in data
    ]


# --- Write tools (human-approval-gated) ---------------------------------------


def rerun_workflow(repo: str, run_id: int, approved: bool = False, token: Optional[str] = None) -> dict:
    """Re-run a failed (or completed) GitHub Actions workflow run.

    THIS IS A WRITE ACTION. It will not execute unless approved=True — see the
    module docstring. The agent must surface this as a proposed action and
    wait for a human to confirm before this is ever called with approved=True.
    """
    details = {"action": "rerun_workflow", "repo": repo, "run_id": run_id}
    _require_approval("rerun_workflow", approved, details)
    try:
        resp = requests.post(
            f"{GITHUB_API}/repos/{repo}/actions/runs/{run_id}/rerun",
            headers=_headers(token), timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise GitHubToolError(f"Failed to re-run workflow {run_id}: {e}") from e
    print(f"[github_tools] APPROVED write executed: {details}", file=sys.stderr)
    return {"status": "rerun_triggered", **details}


def comment_on_issue(
    repo: str, number: int, body: str, approved: bool = False, token: Optional[str] = None
) -> dict:
    """Post a comment on an issue or pull request.

    THIS IS A WRITE ACTION — see rerun_workflow's docstring; the same
    human-approval gate applies here.
    """
    details = {"action": "comment_on_issue", "repo": repo, "number": number, "body": body}
    _require_approval("comment_on_issue", approved, details)
    try:
        resp = requests.post(
            f"{GITHUB_API}/repos/{repo}/issues/{number}/comments",
            headers=_headers(token), json={"body": body}, timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise GitHubToolError(f"Failed to comment on #{number}: {e}") from e
    print(f"[github_tools] APPROVED write executed: {details}", file=sys.stderr)
    return {"status": "comment_posted", **details, "url": resp.json().get("html_url")}


READ_TOOLS = [
    list_pull_requests, get_pull_request, list_issues, get_issue,
    list_workflow_runs, get_workflow_run, get_workflow_run_jobs, get_job_logs,
    get_commit, list_recent_commits,
]
WRITE_TOOLS = [rerun_workflow, comment_on_issue]
ALL_TOOLS = READ_TOOLS + WRITE_TOOLS
TOOLS_BY_NAME = {fn.__name__: fn for fn in ALL_TOOLS}
