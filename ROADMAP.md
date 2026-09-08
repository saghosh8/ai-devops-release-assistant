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

## 🔜 v1.0-day21 — Full agent: AI-Powered DevOps Release Assistant

Per the course diagram: RAG pipeline + vector search + LLM, wired to an agent that can
both **answer** and **act** via tools against GitHub/CI-CD.

Planned additions:

| File | What it will do |
|---|---|
| `agent.py` | Planning loop: given a question, decide whether to retrieve, call a tool, or answer directly, possibly across multiple steps (Day 15) |
| `github_tools.py` | Real GitHub API tools (read PRs/issues/workflow runs; *execute* actions like re-running a workflow only behind an explicit human-approval gate) (Day 16) |
| `analysis/` | PR review, commit analysis, CI/CD failure analysis, log analysis, deployment troubleshooting as distinct, testable functions the agent can call (Day 17) |
| `security.py` | Prompt-injection defenses (extending what v0.1 already has), secret-leak scanning on any content passed to the model, basic PII detection, mapped explicitly against the OWASP LLM Top 10 (Day 18) |
| `observability.py` | Prompt/model versioning, per-call cost and latency logging, a small eval set to catch regressions (Day 19) |
| `mcp_server.py` | Expose this assistant's tools over MCP, so it can be called from any MCP-compatible client, not just this CLI (Day 20) |

Also planned: an interview prep doc — 2-minute pitch, RAG vs Agent, RAG vs fine-tuning,
embeddings/vector DB explanations, hallucination handling, security and cost/latency Q&A
(Day 21 prep list).

## Design principle across all three milestones

Nothing in a later milestone should require deleting or rewriting an earlier one — v0.2
adds retrieval *alongside* the existing structured-answer path, and v1.0 adds an agent
*on top of* both. If a planned change would require ripping out earlier work instead of
building on it, that's a sign the architecture needs rethinking before continuing.
