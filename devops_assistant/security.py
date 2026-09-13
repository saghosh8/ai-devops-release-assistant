"""security.py — Day 18 (prompt-injection defenses, secret-leak scanning,
basic PII detection), mapped explicitly against the OWASP Top 10 for LLM
Applications.

Extends what v0.1 (Day 7) already had in prompts.py — INJECTION_DEFENSE_CLAUSE
and flag_suspicious_input() stay there and are reused here, not duplicated.
This module adds the pieces the Day 7 stage had no reason to need yet: real
tool output can now contain secrets (a workflow YAML with an inline token,
a log line with a leaked key) and real PII (an email in a commit author
field), and the agent now has a write-capable action space that regex
input-checking alone can't govern.

Every function below is annotated with the OWASP LLM Top 10 (2025) category
it mitigates. This is a demonstration of the layered thinking the category
is about, same spirit as the Day 3 prompt-security notes — not a
production-grade DLP/security system.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from devops_assistant.prompts import flag_suspicious_input  # noqa: F401 (re-exported)

OWASP_LLM_TOP_10 = {
    "LLM01": "Prompt Injection",
    "LLM02": "Insecure Output Handling",
    "LLM03": "Training Data Poisoning",
    "LLM04": "Model Denial of Service",
    "LLM05": "Supply Chain Vulnerabilities",
    "LLM06": "Sensitive Information Disclosure",
    "LLM07": "Insecure Plugin Design",
    "LLM08": "Excessive Agency",
    "LLM09": "Overreliance",
    "LLM10": "Model Theft",
}

# Which mitigation in this project maps to which OWASP category, for the
# interview-prep doc and for anyone auditing the codebase against the list.
MITIGATION_MAP = {
    "LLM01": "prompts.INJECTION_DEFENSE_CLAUSE (instruction-level) + "
             "prompts.flag_suspicious_input() (input-level warning) + "
             "security.flag_suspicious_input_strict() (blocking variant used by the agent loop)",
    "LLM02": "security.sanitize_tool_output() — every tool result is scanned/redacted "
             "before it is fed back into a prompt or shown to the user",
    "LLM04": "client._with_retries() bounded backoff + agent.Agent max_steps step budget "
             "(bounds cost/time per request regardless of how the model behaves)",
    "LLM05": "pinned minimum versions in requirements*.txt; embeddings.py caches by content "
             "hash rather than trusting an external cache blindly",
    "LLM06": "security.scan_content() secret/PII patterns, applied to tool output and to "
             "observability logs before they're written to disk",
    "LLM08": "github_tools.py's approval gate — every write tool raises ApprovalRequiredError "
             "unless a human explicitly sets approved=True; the agent never sets it itself",
    "LLM09": "observability.run_eval() — a small, versioned eval set that fails loudly if a "
             "prompt/model change regresses answer quality, instead of trusting output blindly",
}


# --- Secret-leak scanning (LLM06: Sensitive Information Disclosure) ----------

_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws_secret_key", re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}")),
    ("github_token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("generic_api_key_assignment", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][A-Za-z0-9\-_/.+]{16,}['\"]"
    )),
]

# --- PII detection (LLM06) ----------------------------------------------------

_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("phone", re.compile(r"\b(?:\+?\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
]


@dataclass
class Finding:
    kind: str  # "secret" or "pii"
    category: str
    line_number: int
    redacted_preview: str


def scan_content(text: str) -> list[Finding]:
    """Scan arbitrary text (tool output, log lines, model output) for secrets
    and PII. Returns findings with a *redacted* preview only — the raw match
    is never included in the Finding, so logging/printing a Finding can never
    itself leak the secret it found.
    """
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for category, pattern in _SECRET_PATTERNS:
            m = pattern.search(line)
            if m:
                findings.append(Finding("secret", category, i, _redact_match(line, m)))
        for category, pattern in _PII_PATTERNS:
            m = pattern.search(line)
            if m:
                findings.append(Finding("pii", category, i, _redact_match(line, m)))
    return findings


def _redact_match(line: str, match: re.Match) -> str:
    start, end = match.span()
    return line[:start] + "[REDACTED]" + line[end:]


def redact(text: str) -> str:
    """Return text with every detected secret/PII span replaced by a
    [REDACTED:<category>] marker. Safe to log or display."""
    result = text
    for category, pattern in _SECRET_PATTERNS + _PII_PATTERNS:
        result = pattern.sub(f"[REDACTED:{category}]", result)
    return result


def sanitize_tool_output(output: str) -> tuple[str, list[Finding]]:
    """LLM02 (Insecure Output Handling) + LLM06 (Sensitive Information
    Disclosure) mitigation: run this on every raw tool result (especially
    get_job_logs, which returns arbitrary CI log text) before it goes back
    into a prompt or gets shown to a user. Returns (sanitized_text, findings)
    so callers can log/warn about what was redacted without re-exposing it.
    """
    findings = scan_content(output)
    return redact(output), findings


# --- Prompt-injection: blocking variant for autonomous agent steps (LLM01) ---


def flag_suspicious_input_strict(text: str) -> str | None:
    """Same detection as prompts.flag_suspicious_input(), but intended to be
    treated as *blocking* rather than advisory when it fires inside the
    agent's autonomous loop (agent.py) — a human typing a weird question at
    the CLI is one thing; an LLM autonomously feeding another LLM call
    attacker-controlled tool output (e.g. a PR body) is exactly the scenario
    OWASP LLM01 is about, and there's no human in the loop to notice.
    """
    return flag_suspicious_input(text)
