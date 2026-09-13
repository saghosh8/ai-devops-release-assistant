"""
mcp_server.py — Day 20: expose this assistant's tools over MCP, so it can be
called from any MCP-compatible client (Claude Desktop, Claude Code, another
agent), not just this repo's own CLI.

Uses the official `mcp` SDK's MCPServer (the mcp>=2.0 name for what earlier
SDK versions called FastMCP — see requirements.txt for the pinned version).
`add_tool(fn)` introspects a plain Python function's type hints and
docstring, the same shape every tool in this project already has for
Gemini's automatic function calling (tools.py) and for agent.py's manual
function-calling loop — one implementation, three call sites, as
github_tools.py's module docstring puts it.

Write tools (rerun_workflow, comment_on_issue) are registered exactly as
github_tools.py defines them, `approved: bool = False` included in the
exposed schema rather than hidden — an MCP client calling this server IS a
human (or an agent acting for one) making an explicit tool call, unlike
agent.py's own model loop, so there is no need to hide the approval
parameter here; the gate is that it must be explicitly and deliberately set
True by whoever is calling, not defaulted or inferred.

Run it:
    python -m devops_assistant.mcp_server                    # stdio (default)
    python -m devops_assistant.mcp_server --transport sse --port 8787
"""

from __future__ import annotations

import argparse

from mcp.server.mcpserver import MCPServer

from . import github_tools
from .agent import (
    analyze_recent_commits,
    diagnose_workflow_run,
    review_pull_request,
    search_repo_history,
    troubleshoot_latest_failed_run,
)
from .client import AssistantError, ask_structured
from .tools import get_utc_time

mcp = MCPServer(
    name="devops-release-assistant",
    description=(
        "AI-powered DevOps release assistant: structured runbook answers, "
        "RAG search over ingested repo history, and real read/write tools "
        "against GitHub (PRs, issues, workflow runs, commits)."
    ),
)


def ask_devops_question(question: str) -> dict:
    """Ask a general DevOps/SRE question and get back a structured runbook:
    summary, root cause, ordered steps, runnable commands, best practices,
    references. Does not look at any specific repo's data — for that, use
    search_repo_history or the GitHub-backed tools instead.
    """
    try:
        return ask_structured(question)
    except AssistantError as e:
        return {"error": str(e)}


# Read-only GitHub tools, registered as-is.
for _fn in (
    github_tools.list_pull_requests,
    github_tools.get_pull_request,
    github_tools.list_issues,
    github_tools.get_issue,
    github_tools.list_workflow_runs,
    github_tools.get_workflow_run,
    github_tools.get_workflow_run_jobs,
    github_tools.get_job_logs,
    github_tools.get_commit,
    github_tools.list_recent_commits,
):
    mcp.add_tool(_fn)

# Write tools — approved=False by default in the schema itself; see module docstring.
for _fn in (github_tools.rerun_workflow, github_tools.comment_on_issue):
    mcp.add_tool(_fn)

# Composite analysis tools (agent.py) — the same ones agent.py's own model
# loop is steered toward using, now reachable from any MCP client too.
for _fn in (
    diagnose_workflow_run,
    review_pull_request,
    analyze_recent_commits,
    troubleshoot_latest_failed_run,
    search_repo_history,
):
    mcp.add_tool(_fn)

mcp.add_tool(ask_devops_question)
mcp.add_tool(get_utc_time)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="devops-assistant-mcp")
    parser.add_argument(
        "--transport", default="stdio", choices=["stdio", "sse", "streamable-http"]
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for sse/streamable-http")
    parser.add_argument("--port", type=int, default=8787, help="Port for sse/streamable-http")
    args = parser.parse_args(argv)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
