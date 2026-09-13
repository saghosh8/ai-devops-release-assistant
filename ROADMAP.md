# Roadmap

This repo grows across three milestones, one per course week. Each milestone is tagged
in git so the assistant's evolution is inspectable at any point — see the README's
milestone table for tags.

## ✅ v0.1-day7 — Plain LLM assistant

Per the course diagram: `Question → System prompt + JSON schema → Gemini → Structured runbook`

- Ask a DevOps question, get a structured JSON runbook back — no retrieval, no external
  data, no agent loop yet; every answer comes purely from what the model already knows
  plus the question

| File | What it does |
|---|---|
| `client.py` | API calls: auth, retries, streaming, tool-use loop |
| `prompts.py` | System/user prompts + JSON schema + scope guardrail |
| `tools.py` | One real tool-use example (`get_utc_time`) |
| `memory.py` | Local history + context-window management |
| `formatter.py` | Terminal (ANSI) and Markdown renderers |
| `cli.py` | argparse CLI: `ask` / `stream` / `tools-demo` / `history` |

## ✅ v0.2-day14 — RAG: DevOps Release Assistant (current)

Per the course diagram: `GitHub → YAML/PRs/Commits/Docs → Embeddings → FAISS → Retriever → Ollama → DevOps Assistant`

Ingests live from **three real repos** — [`release-automation`](https://github.com/saghosh8/release-automation),
`application-one`, `application-two` — instead of local sample/fixture data. Generation
runs on a local model via Ollama rather than a paid API, so the whole pipeline is
runnable with nothing but a GitHub token.

| File | What it does |
|---|---|
| `rag/ingest.py` | Pulls workflow YAML, PR titles/bodies, commit messages, and README from each configured repo via the GitHub REST API (Day 9: document loaders, cleaning, metadata) |
| `rag/embeddings.py` | Embeds chunks with Sentence Transformers (Day 10: embeddings, cosine similarity) |
| `rag/vectorstore.py` | Stores/queries embeddings in FAISS (Day 11) |
| `rag/retriever.py` | Builds the index from `ingest.load()`, runs top-K similarity search with an optional `source_type` filter (Day 12) |
| `rag/rag_client.py` | Constructs a prompt from retrieved context and answers via a local Ollama model (Day 13) |
| `rag/ask_rag.py` | CLI entry point — question in, cited answer out |

Run it: `python -m devops_assistant.rag.ask_rag "<question>" --repos owner/repo1 owner/repo2`
(defaults to the configured `GITHUB_REPOS` list if `--repos` is omitted), or via the
**"Ask RAG Anything"** GitHub Actions workflow — no local setup required, Ollama installs
and runs inside the job.

This milestone answers questions like *"what changed in the release workflow?"* or *"is
there any security issue across these repos?"* — things the Day 7 assistant structurally
cannot know, because it has no access to real repo history.

## ✅ v1.0-day21 — Full agent: AI-Powered DevOps Release Assistant

Per the course diagram: RAG pipeline + vector search + LLM, wired to an agent that can
both **answer** and **act** via tools against GitHub/CI-CD.

| File | What it does |
|---|---|
| `agent.py` | Planning loop: given a question, decides whether to search repo history, call a GitHub tool, run one of `analysis/`'s functions, or answer directly — across up to 6 steps. Uses Gemini's *manual* (not automatic) function calling specifically so a human-approval step can sit between "model proposes a write action" and "GitHub API is actually called" (Day 15) |
| `github_tools.py` | Real GitHub REST API tools: read PRs/issues/workflow runs/jobs/logs/commits freely; the two write tools (`rerun_workflow`, `comment_on_issue`) raise `ApprovalRequiredError` unless called with `approved=True` — the agent's own model loop never sets that flag itself (Day 16) |
| `analysis/` | `pr_review.py`, `commit_analysis.py`, `ci_failure_analysis.py`, `log_analysis.py`, `deployment_troubleshooting.py` — plain, deterministic, dict-in/dict-out functions with no GitHub API calls inside them, so each is testable with fixture data alone. `agent.py` wires GitHub data into them via composite tools (`diagnose_workflow_run`, `review_pull_request`, `troubleshoot_latest_failed_run`) (Day 17) |
| `security.py` | Secret-leak scanning and PII detection (`scan_content`, `redact`, `sanitize_tool_output`) applied to every tool result before it re-enters the model's context; a blocking prompt-injection check for the agent's autonomous loop; an explicit `MITIGATION_MAP` against the OWASP LLM Top 10 (Day 18) |
| `observability.py` | `track_call` context manager logs latency, estimated cost, and prompt/model version per call to a local JSONL file; `run_eval` runs a small fixed eval set against any predict function to catch regressions (Day 19) |
| `mcp_server.py` | Exposes 19 tools (all of `github_tools.py`, the composite analysis tools, RAG search, and the original Day 7 `ask`) over MCP via the official `mcp` SDK, so any MCP-compatible client — not just this repo's CLI — can call them (Day 20) |

Run it: `python -m devops_assistant agent "<question>"` (add `--verbose` for the tool-call
transcript, `--approve-writes` to auto-approve any proposed write action instead of being
prompted interactively), or via the **"Run Agent"** GitHub Actions workflow. Run the MCP
server with `python -m devops_assistant.mcp_server`.

See [`INTERVIEW_PREP.md`](INTERVIEW_PREP.md) for the Day 21 prep list: 2-minute pitch, RAG
vs Agent, RAG vs fine-tuning, embeddings/vector DB explanations, hallucination handling,
security and cost/latency Q&A.

## Design principle across all three milestones

Nothing in a later milestone should require deleting or rewriting an earlier one — v0.2
adds retrieval *alongside* the existing structured-answer path, and v1.0 adds an agent
*on top of* both. If a planned change would require ripping out earlier work instead of
building on it, that's a sign the architecture needs rethinking before continuing.
