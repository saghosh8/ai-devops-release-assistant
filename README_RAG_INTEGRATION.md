# Integrating this into ai-devops-release-assistant

Everything here is additive — nothing in your existing `devops_assistant/` (client.py,
prompts.py, tools.py, memory.py, formatter.py, cli.py) needs to change. Drop these in
and wire up two small things.

## 1. Copy these into your repo root

```
sample_repo_data/              # new — fixture data for the demo/tests
devops_assistant/rag/          # new — the whole RAG pipeline
.github/workflows/ask-rag-demo.yml   # new — separate workflow, doesn't touch
                                       # your existing ask-devops-assistant.yml
tests/test_rag_ingest_chunking.py
tests/test_rag_retriever.py
requirements-rag.txt           # kept separate from requirements.txt on purpose —
                                # faiss/sentence-transformers are heavy, Day 7's
                                # workflow shouldn't need to install them
```

## 2. Wire `ask-rag` into your existing CLI (optional but recommended)

`devops_assistant/rag/ask_rag.py` runs standalone right now
(`python -m devops_assistant.rag.ask_rag "question"`), which is all the demo workflow
needs. To make it feel like one CLI instead of two, add a subcommand to your existing
`cli.py`'s argparse setup:

```python
from devops_assistant.rag.ask_rag import main as ask_rag_main

# inside your subparsers setup:
rag_parser = subparsers.add_parser("ask-rag", help="Ask using retrieved repo context")
# ask_rag.py already defines its own argparse — simplest integration is to just
# delegate remaining argv to it:
```

If your `cli.py` subparser structure makes that delegation awkward, it's fine to leave
`ask_rag.py` as a separate entry point for now — the design principle in your
ROADMAP.md is "nothing later requires rewriting earlier work," and forcing a
non-trivial argparse merge isn't worth it just for cosmetic unification.

## 3. Update your test CI (tests.yml)

Add `pip install -r requirements-rag.txt` before the pytest step, or split into a
second job — your call. `faiss-cpu` installs in a few seconds; it won't meaningfully
slow down CI.

## 4. Update the README's Day → code mapping table

Following the same pattern as Days 1–7, add rows for Days 8–13:

| Day | Topic | Where it shows up |
|---|---|---|
| 9 | Document loaders, cleaning, metadata | `ingest.py` — `Document` dataclass, per-source-type loaders |
| 10 | Chunking, chunk size/overlap | `chunking.py` — boundary-aware splitting, YAML never split mid-block |
| 10 | Embeddings, cosine similarity | `embeddings.py` — sentence-transformers, cached by content hash |
| 11 | Vector databases, FAISS, metadata filtering | `vectorstore.py` — FAISS IndexFlatIP + metadata sidecar |
| 12 | Top-K, similarity search, retrieval quality | `retriever.py` — `retrieve(query, k, source_type)` |
| 13 | Prompt construction, context injection, Ollama | `rag_client.py` — `build_prompt()`, `call_ollama()` |

## Why `sample_repo_data/` instead of your live repo

Two honest reasons, worth stating in the README so it reads as a deliberate choice
rather than a shortcut:

1. **Deterministic, offline demo.** The Actions workflow and the test suite need to
   produce the same result every run without a `GITHUB_TOKEN` secret or live API
   rate-limit budget — same philosophy as Day 7's tests needing no live API calls.
2. **A compelling demo needs a *causal* scenario** (a bug traceable to a specific
   PR/commit) that your actual repo's history doesn't happen to contain yet. The
   fixture data is clearly labeled as seed data, not a claim about your repo's real
   history.

`ingest.load_github()` is stubbed and documented as the real extension point for when
you want to point this at an actual live repo (yours or someone else's) later —
nothing about the chunking/embedding/retrieval/answer code needs to change to support
that, only the ingestion source.

## Running it locally to sanity-check before pushing

```bash
pip install -r requirements-rag.txt
ollama serve &
ollama pull llama3.2:1b
python -m devops_assistant.rag.ask_rag \
  "I'm getting exit code 1 on the docker build step in deploy.yml, what's going on?" \
  --rebuild-index --markdown
```

Expected: the answer should cite `.github/workflows/deploy.yml`, `deployment_notes.md`,
and `PR #47` — if it doesn't mention PR #47 at all, that's a sign retrieval quality
needs tuning (try increasing `-k`, or check the embedding cache isn't stale).
