"""
Tests for github_tools.py. All GitHub API calls go through requests.get/post,
so every test monkeypatches those two functions with a fake response object
instead of hitting the network — same no-network philosophy as
test_rag_retriever.py's FakeEmbedder.
"""

import pytest

from devops_assistant import github_tools


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._json_data


def test_list_pull_requests_shapes_result(monkeypatch):
    fake_prs = [
        {"number": 1, "title": "Fix bug", "state": "open", "user": {"login": "alice"},
         "created_at": "2026-01-01T00:00:00Z", "merged_at": None, "html_url": "https://x/1"}
    ]
    monkeypatch.setattr(
        github_tools.requests, "get", lambda *a, **k: FakeResponse(fake_prs)
    )
    result = github_tools.list_pull_requests("owner/repo")
    assert result == [
        {"number": 1, "title": "Fix bug", "state": "open", "user": "alice",
         "created_at": "2026-01-01T00:00:00Z", "merged_at": None, "url": "https://x/1"}
    ]


def test_list_issues_excludes_pull_requests(monkeypatch):
    fake_issues = [
        {"number": 1, "title": "Real issue", "state": "open", "user": {"login": "bob"},
         "created_at": "2026-01-01T00:00:00Z", "labels": [], "html_url": "https://x/1"},
        {"number": 2, "title": "Actually a PR", "state": "open", "user": {"login": "bob"},
         "created_at": "2026-01-01T00:00:00Z", "labels": [], "html_url": "https://x/2",
         "pull_request": {}},
    ]
    monkeypatch.setattr(
        github_tools.requests, "get", lambda *a, **k: FakeResponse(fake_issues)
    )
    result = github_tools.list_issues("owner/repo")
    assert len(result) == 1
    assert result[0]["number"] == 1


def test_get_api_error_raises_github_tool_error(monkeypatch):
    monkeypatch.setattr(
        github_tools.requests, "get", lambda *a, **k: FakeResponse({}, status_code=404)
    )
    with pytest.raises(github_tools.GitHubToolError):
        github_tools.get_issue("owner/repo", 999)


def test_rerun_workflow_requires_approval(monkeypatch):
    called = {"posted": False}
    monkeypatch.setattr(
        github_tools.requests, "post",
        lambda *a, **k: called.__setitem__("posted", True) or FakeResponse({}),
    )
    with pytest.raises(github_tools.ApprovalRequiredError):
        github_tools.rerun_workflow("owner/repo", 123)
    assert called["posted"] is False, "the real API must never be called without approval"


def test_rerun_workflow_executes_when_approved(monkeypatch):
    monkeypatch.setattr(
        github_tools.requests, "post", lambda *a, **k: FakeResponse({}, status_code=201)
    )
    result = github_tools.rerun_workflow("owner/repo", 123, approved=True)
    assert result == {"status": "rerun_triggered", "action": "rerun_workflow",
                       "repo": "owner/repo", "run_id": 123}


def test_comment_on_issue_requires_approval(monkeypatch):
    monkeypatch.setattr(
        github_tools.requests, "post", lambda *a, **k: FakeResponse({"html_url": "x"})
    )
    with pytest.raises(github_tools.ApprovalRequiredError):
        github_tools.comment_on_issue("owner/repo", 1, "hello")


def test_tools_by_name_registry_contains_expected_tools():
    assert "list_pull_requests" in github_tools.TOOLS_BY_NAME
    assert "rerun_workflow" in github_tools.TOOLS_BY_NAME
    assert github_tools.TOOLS_BY_NAME["get_issue"] is github_tools.get_issue
