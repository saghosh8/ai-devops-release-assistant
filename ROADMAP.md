# Roadmap

This repo grows across three milestones, one per course week. Each milestone is tagged
in git so the assistant's evolution is inspectable at any point — see the README's
milestone table for tags.

## ✅ v0.1-day7 — Plain LLM assistant (current)

- Ask a DevOps question, get a structured JSON runbook back
- System/user prompts, few-shot examples, prompt templates, prompt chaining, prompt security
- Real API auth, streaming, rate-limit backoff, error handling
- Model selection across Gemini tiers (quality/cost/latency)
- Local memory (`--continue`), one real tool-use example, scope guardrail

No retrieval, no external data, no agent loop yet — every answer comes purely from what
the model already knows plus the question.

## 🔜 v0.2-day14 — RAG: DevOps Release Assistant

Per the course diagram: `GitHub → YAML/PRs/Commits/Docs → Embeddings → FAISS → Retriever → Ollama → DevOps Assistant`

Planned additions:

- **`ingest/`** — pull real content from a target GitHub repo: workflow YAML, recent PR
  descriptions, commit messages, and docs (Day 9: document loaders, cleaning, metadata)
- **`chunking.py`** — split ingested content into chunks with a configurable size/overlap
  (Day 10)
- **`embeddings.py`** — embed chunks with Sentence Transformers (Day 10: embeddings,
  cosine similarity)
- **`vectorstore.py`** — store/query embeddings in FAISS, with metadata filtering (Day 11)
- **`retriever.py`** — top-K similarity search, with room to add hybrid search/reranking
  later (Day 12)
- **`rag_client.py`** — construct a prompt that injects retrieved context, and answer via
  **Ollama** (local model) rather than the Gemini API — this is the milestone where the
  assistant starts reasoning over *your* repo's actual data, not just general knowledge
  (Day 13)
- New CLI command: `devops-assistant ask-rag "<question>" --repo <owner/repo>`

This milestone answers questions like *"what changed in the last release?"* or *"why did
this workflow fail last time?"* — things the Day 7 assistant structurally cannot know,
because it has no access to your repo's actual history.

## 🔜 v1.0-day21 — Full agent: AI-Powered DevOps Release Assistant

Per the course diagram: RAG pipeline + vector search + LLM, wired to an agent that can
both **answer** and **act** via tools against GitHub/CI-CD.

Planned additions:

- **`agent.py`** — planning loop: given a question, decide whether to retrieve, call a
  tool, or answer directly, possibly across multiple steps (Day 15)
- **`github_tools.py`** — real GitHub API tools (read PRs/issues/workflow runs; *execute*
  actions like re-running a workflow only behind an explicit human-approval gate) (Day 16)
- **`analysis/`** — PR review, commit analysis, CI/CD failure analysis, log analysis,
  deployment troubleshooting as distinct, testable functions the agent can call (Day 17)
- **`security.py`** — prompt-injection defenses (extending what v0.1 already has),
  secret-leak scanning on any content passed to the model, basic PII detection, mapped
  explicitly against the OWASP LLM Top 10 (Day 18)
- **`observability.py`** — prompt/model versioning, per-call cost and latency logging,
  a small eval set to catch regressions (Day 19)
- **`mcp_server.py`** — expose this assistant's tools over MCP, so it can be called from
  any MCP-compatible client, not just this CLI (Day 20)
- Interview prep doc: 2-minute pitch, RAG vs Agent, RAG vs fine-tuning, embeddings/vector
  DB explanations, hallucination handling, security and cost/latency Q&A (Day 21 prep list)

## Design principle across all three milestones

Nothing in a later milestone should require deleting or rewriting an earlier one — v0.2
adds retrieval *alongside* the existing structured-answer path, and v1.0 adds an agent
*on top of* both. If a planned change would require ripping out earlier work instead of
building on it, that's a sign the architecture needs rethinking before continuing.
