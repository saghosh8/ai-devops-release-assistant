"""observability.py — Day 19 (prompt/model versioning, per-call cost and
latency logging, a small eval set to catch regressions).

Deliberately file-based (a JSONL log, a Python list of eval cases) rather
than wired to a real observability platform — same "demonstrate the concept
plainly" philosophy as memory.py's JSON-file history. Swap
CallRecord/log_call for a real backend (Datadog, Langfuse, etc.) without
touching any caller, since every caller only ever sees log_call(record).
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

DEFAULT_LOG_PATH = ".observability/calls.jsonl"

# Bump these when a prompt's *wording* changes in a way that could change
# behavior — lets observability.run_eval() (and a human skimming the log)
# tell "the model got worse" apart from "we changed the prompt on purpose".
PROMPT_VERSIONS = {
    "structured_runbook": "v1",
    "stream_answer": "v1",
    "refine_question": "v1",
    "agent_decision": "v1",
}

# Rough, illustrative $ per 1K tokens — NOT pulled from a live pricing API.
# Good enough to compare relative cost across models/calls in this demo;
# check https://ai.google.dev/gemini-api/docs/pricing before trusting an
# absolute number.
COST_PER_1K_TOKENS = {
    "gemini-3.5-flash": {"input": 0.00010, "output": 0.00040},
    "gemini-3.5-flash-lite": {"input": 0.00004, "output": 0.00015},
}


@dataclass
class CallRecord:
    timestamp: str
    model: str
    prompt_name: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    estimated_cost_usd: float
    success: bool
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = COST_PER_1K_TOKENS.get(model)
    if not rates:
        return 0.0
    return round((input_tokens / 1000) * rates["input"] + (output_tokens / 1000) * rates["output"], 6)


def log_call(record: CallRecord, log_path: str = DEFAULT_LOG_PATH) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict()) + "\n")


def load_calls(log_path: str = DEFAULT_LOG_PATH) -> list[dict]:
    path = Path(log_path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@contextmanager
def track_call(
    model: str,
    prompt_name: str,
    log_path: str = DEFAULT_LOG_PATH,
    prompt_version: Optional[str] = None,
):
    """Context manager that times a call and logs a CallRecord on exit.

    Usage:
        with track_call(model, "structured_runbook") as t:
            response = ...  # do the actual API call
            t["input_tokens"] = response.usage_metadata.prompt_token_count
            t["output_tokens"] = response.usage_metadata.candidates_token_count

    If the block raises, the record is still logged with success=False and
    the exception's string, then re-raised — a failed call is still a call
    worth counting toward latency/cost/error-rate tracking.
    """
    state = {"input_tokens": 0, "output_tokens": 0}
    start = time.monotonic()
    try:
        yield state
        success, error = True, None
    except Exception as e:  # noqa: BLE001 — intentionally broad, we re-raise below
        success, error = False, str(e)
        raise
    finally:
        latency_ms = (time.monotonic() - start) * 1000
        record = CallRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            model=model,
            prompt_name=prompt_name,
            prompt_version=prompt_version or PROMPT_VERSIONS.get(prompt_name, "unknown"),
            input_tokens=state["input_tokens"],
            output_tokens=state["output_tokens"],
            latency_ms=round(latency_ms, 1),
            estimated_cost_usd=estimate_cost(model, state["input_tokens"], state["output_tokens"]),
            success=success,
            error=error,
        )
        log_call(record, log_path=log_path)


# --- Small eval set (Day 19 / LLM09 Overreliance mitigation) -----------------
# Deliberately small (a handful of cases, not a benchmark suite) — the point
# is catching an obvious regression (e.g. a prompt edit that breaks JSON
# output, or a model swap that stops respecting the scope guardrail), not
# rigorous quality measurement.

EVAL_CASES: list[dict] = [
    {"question": "why is my pod stuck in CrashLoopBackOff?", "expected_category": "Kubernetes"},
    {"question": "my GitHub Actions workflow fails on npm install", "expected_category": "CI/CD"},
    {"question": "nginx ingress returns 504 gateway timeout", "expected_category": "Networking"},
    {"question": "what's the best pizza topping?", "expected_category": "Out of scope"},
    {"question": "how do I roll back a bad ECS deployment?", "expected_category": "Cloud"},
    {"question": "my prometheus alerts are too noisy", "expected_category": "Observability"},
]


def run_eval(
    predict_fn: Callable[[str], dict], cases: list[dict] = EVAL_CASES
) -> dict:
    """Run predict_fn(question) -> structured answer dict against a small
    fixed eval set and report pass/fail on the `category` field.

    predict_fn is injected rather than hardcoded to client.ask_structured so
    tests can pass a fake/deterministic function with no API key or network
    access required.
    """
    results = []
    passed = 0
    for case in cases:
        try:
            answer = predict_fn(case["question"])
            got = answer.get("category")
            ok = got == case["expected_category"]
        except Exception as e:  # noqa: BLE001
            got, ok = None, False
            answer = {"error": str(e)}
        passed += int(ok)
        results.append({
            "question": case["question"],
            "expected_category": case["expected_category"],
            "got_category": got,
            "passed": ok,
        })

    return {
        "passed": passed,
        "total": len(cases),
        "pass_rate": round(passed / len(cases), 3) if cases else 0.0,
        "results": results,
    }


def print_eval_report(report: dict) -> None:
    print(f"Eval: {report['passed']}/{report['total']} passed ({report['pass_rate']:.0%})")
    for r in report["results"]:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"  [{mark}] {r['question']!r} -> expected={r['expected_category']!r} got={r['got_category']!r}")
