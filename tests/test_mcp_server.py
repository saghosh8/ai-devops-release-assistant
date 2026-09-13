"""
Smoke test for mcp_server.py: confirms every intended tool actually registers
with the MCPServer instance and that a representative tool can be called
through the MCP call_tool path end-to-end. Not a protocol-conformance test
(the mcp SDK itself owns that) — just "did we wire this up correctly".
"""

import asyncio

from devops_assistant import mcp_server


def test_all_expected_tools_are_registered():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "list_pull_requests", "get_pull_request", "list_issues", "get_issue",
        "list_workflow_runs", "get_workflow_run", "get_workflow_run_jobs",
        "get_job_logs", "get_commit", "list_recent_commits",
        "rerun_workflow", "comment_on_issue",
        "diagnose_workflow_run", "review_pull_request", "analyze_recent_commits",
        "troubleshoot_latest_failed_run", "search_repo_history",
        "ask_devops_question", "get_utc_time",
    }
    assert expected <= names


def test_write_tool_schema_exposes_approved_flag():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    rerun = next(t for t in tools if t.name == "rerun_workflow")
    props = rerun.input_schema.get("properties", {})
    assert "approved" in props, "the approval gate must be visible in the MCP tool schema"


def test_get_utc_time_tool_is_callable_end_to_end():
    result = asyncio.run(mcp_server.mcp.call_tool("get_utc_time", {}))
    # call_tool returns (content_blocks, structured_result) in this SDK version;
    # just confirm it ran without raising and produced some output.
    assert result is not None
