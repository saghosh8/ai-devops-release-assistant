# Interview Prep — Day 21

Quick-reference answers for the questions this project is meant to prepare you for.
Written to be said out loud in 30–90 seconds each, not read verbatim.

## The 2-minute pitch

"I built an AI-powered DevOps release assistant that grew across three stages instead of
being three separate demos. It started as a plain LLM Q&A tool — ask a DevOps question,
get back a structured JSON runbook. Then I added RAG: it ingests live workflow YAML, PRs,
commits, and READMEs from three real GitHub repos, chunks and embeds them, stores them in
FAISS, and retrieves grounded context before answering with a local model. The final
stage turns it into an agent: it has real read tools against the GitHub API — PRs,
issues, workflow runs, logs — plus deterministic analysis functions for things like CI
failure categorization and PR risk scoring, and it can propose a write action (like
re-running a failed workflow) but never execute one without an explicit human approval
step. On top of that there's secret/PII scanning on every tool result, per-call cost and
latency logging, a small regression eval set, and the whole tool surface is also exposed
over MCP so any MCP client can use it, not just my own CLI."

## RAG vs. Agent — what's the actual difference?

- **RAG** retrieves relevant context and hands it to the model as part of the prompt; the
  model still only *answers*. It's a one-shot (or few-shot) pipeline: retrieve → generate.
- **An agent** can *decide*, across multiple steps, what to do next based on what it just
  learned — call a tool, look at the result, call another tool, then answer. It has a
  loop, not just a pipeline.
- They compose: this project's agent has a `search_repo_history` tool that *is* the RAG
  pipeline from Day 14, called as one option among several, not a replacement for it.
- The practical tell: if the answer requires investigation ("why did this fail," "is this
  PR risky") where the right next step depends on what you find, that's agent territory.
  If it's "find the passage that answers this," that's RAG.

## RAG vs. fine-tuning — when would you pick one over the other?

- **RAG** is the right default when the underlying facts change often (a repo's current
  state, this week's incidents) or you need traceability ("here's the PR that answer came
  from"). No retraining needed when the data changes — you just re-ingest.
- **Fine-tuning** is better for teaching a *behavior* or *style* the base model doesn't
  have — a specific output format, a domain vocabulary, a tone — not for injecting facts
  that go stale. Facts baked into fine-tuned weights still go out of date and can't be
  cited back to a source.
- They're not mutually exclusive: you could fine-tune for output style/format and still
  RAG in current facts. This project doesn't fine-tune at all — the JSON schema is
  enforced by prompting (`prompts.py`'s `JSON_SCHEMA_INSTRUCTIONS`), which was enough
  here and avoided the cost/complexity of training a model.

## Embeddings and vector databases, explained simply

- An **embedding** is a fixed-length vector that represents a piece of text such that
  texts with similar *meaning* end up close together in that vector space — closer than
  texts that just share words. `rag/embeddings.py` uses Sentence Transformers for this.
- A **vector database** (or in this project's case, just a FAISS index — a library, not a
  managed DB) stores those vectors and answers "which of these N vectors are closest to
  this query vector" efficiently, without comparing the query against every document with
  a naive loop.
- The pipeline: chunk the source text (`rag/chunking.py`) → embed each chunk → store in
  FAISS (`rag/vectorstore.py`) → at query time, embed the question the same way → ask
  FAISS for the top-K closest chunks → hand those chunks to the model as context.
- Why chunk at all instead of embedding whole documents: a whole README embedded as one
  vector blurs together many different topics, so a specific question matches it weakly;
  small, focused chunks (a single PR, a single YAML file) embed more precisely.

## How do you handle hallucination?

- **Ground answers in retrieved/tool-sourced content** rather than the model's memory
  whenever real, current facts matter — that's the entire point of both the RAG stage and
  the agent's tool calls. The agent's system prompt explicitly tells it to cite which
  tool/source each point in its answer came from.
- **Constrain the output shape.** The Day 7 structured-answer path uses a strict JSON
  schema (`JSON_SCHEMA_INSTRUCTIONS`) rather than free text, which makes it easier to
  catch a malformed/empty answer programmatically instead of trusting prose.
- **Scope guardrails.** `SCOPE_GUARDRAIL` tells the model to say "out of scope" rather
  than confabulate an answer to a non-DevOps question — refusing is better than a
  plausible-sounding wrong answer.
- **A small eval set** (`observability.EVAL_CASES` / `run_eval`) exists specifically to
  catch the case where a prompt or model change silently makes answers worse — this is
  the OWASP LLM09 (Overreliance) mitigation: don't just trust output, periodically check
  it against known-good expectations.
- What this project does *not* claim to do: eliminate hallucination entirely, or verify
  every generated claim against a source automatically. RAG and tool grounding reduce the
  *rate* of hallucination on grounded questions; they don't guarantee zero.

## Security: what did you actually mitigate, and how?

Mapped explicitly in `security.py`'s `MITIGATION_MAP` against the OWASP Top 10 for LLM
Applications:

- **LLM01 Prompt Injection** — an instruction-level defense (`INJECTION_DEFENSE_CLAUSE`,
  present in every system prompt) plus input-level detection. The CLI's version
  (`flag_suspicious_input`) is advisory — it warns but still answers, since a human is
  right there to notice a weird response. The agent's version
  (`flag_suspicious_input_strict`) is treated as *blocking* for the initial question and
  for tool output, because an autonomous loop has no human watching each step to catch a
  PR body or log line that says "ignore previous instructions."
- **LLM02 Insecure Output Handling** and **LLM06 Sensitive Information Disclosure** —
  every tool result is run through `security.sanitize_tool_output()` before it goes back
  into the model's context: regex-based secret detection (AWS keys, GitHub tokens, Google
  API keys, Slack tokens, private key blocks, generic `key=value` assignments) and PII
  detection (emails, phone numbers, SSNs, card-number-shaped strings), both redacted
  before display or reuse — findings carry only a redacted preview, never the raw match.
- **LLM08 Excessive Agency** — the core design decision of the whole write-tool surface:
  `rerun_workflow` and `comment_on_issue` both require `approved=True` to do anything, and
  raise `ApprovalRequiredError` otherwise. The agent's own model loop *never* sets that
  flag — only a human confirming interactively (or `--approve-writes` as an explicit,
  logged opt-in for non-interactive/CI use) can turn a proposal into a real action.
- **LLM04 Model Denial of Service** — bounded via `client._with_retries()`'s backoff cap
  and `agent.py`'s `max_steps` (default 6) — the loop cannot run away indefinitely
  regardless of what the model decides to do.
- **LLM09 Overreliance** — the small eval set described above.
- What's explicitly *not* attempted: this is a demonstration of the layered thinking the
  OWASP list is about, not a production-grade DLP or WAF. The regex patterns will miss
  novel secret formats; there's no rate limiting or auth on the MCP server itself.

## Cost and latency — how would you reason about this in production?

- **Every model call is logged** (`observability.track_call`) with latency in ms, input/
  output token counts, and an estimated cost per call, derived from a small
  `COST_PER_1K_TOKENS` table. That's enough to answer "what's this costing us" and "is
  this call unusually slow" from the JSONL log without a separate dashboard.
- **Latency in an agent scales with steps, not just tokens** — each tool-calling round
  trip is a full model call. `max_steps` is a deliberate cost/latency ceiling as much as a
  runaway-loop guard: it bounds the worst case regardless of how much the model wants to
  investigate.
- **Cheap-first ordering matters.** `log_analysis.py`'s regex signature matching runs
  *before* any LLM sees raw CI logs — logs can be huge, and a deterministic first pass
  means the model only ever receives the handful of lines that actually matter, which
  is both cheaper and more reliable than asking a model to skim a 20,000-character log.
- **Model choice is a cost/quality lever, not fixed** — `gemini-3.5-flash-lite` vs
  `gemini-3.5-flash` are both wired through the same code path (`--model` flag), so
  switching for a cheaper/faster tier on lower-stakes questions is a one-flag change, not
  a rewrite.
- What this doesn't do: real-time budget enforcement (a hard stop mid-conversation once a
  cost threshold is hit) or a live pricing API — the cost table is illustrative, not
  billing-accurate; a real production system would pull current pricing rather than a
  hardcoded table.
