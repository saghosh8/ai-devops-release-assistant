"""Simple local memory (Day 6: context management & memory).

Deliberately not a database or a vector store — just a JSON file of recent
Q&A pairs. Two things it's used for:

  1. `history` command — show what you've asked before.
  2. `--continue` flag on `ask` — fold the last exchange back in as context,
     so a short follow-up question ("what about on EKS specifically?") still
     has something to refer to. This is context management, made visible.
"""

from __future__ import annotations

import json
import os
from typing import List

HISTORY_FILE = os.path.join(os.getcwd(), ".devops_assistant_history.json")
MAX_STORED = 20


def load_history() -> List[dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def append_history(question: str, summary: str) -> None:
    history = load_history()
    history.append({"question": question, "summary": summary})
    history = history[-MAX_STORED:]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def build_context_messages(turns: int = 1) -> list:
    """Turn the last N history entries into prior user/assistant turns.

    Kept intentionally lossy (question + one-line summary only, not the full
    structured answer) — a small, cheap window rather than an ever-growing
    transcript. That tradeoff *is* context management.
    """
    history = load_history()[-turns:]
    messages = []
    for entry in history:
        messages.append({"role": "user", "content": entry["question"]})
        messages.append({"role": "assistant", "content": entry["summary"]})
    return messages
