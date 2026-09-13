"""log_analysis.py — Day 17: raw CI log analysis as a distinct, testable
function.

Regex-based signature matching over raw log text. Deliberately not an LLM
call — logs can be huge and noisy, and a cheap, deterministic first pass
means the (expensive) LLM step in ci_failure_analysis.py only ever sees the
handful of lines that actually matter, not the whole log.
"""

from __future__ import annotations

import re

# Each pattern maps to a short, stable category name used elsewhere
# (ci_failure_analysis.py buckets on these). Order matters: first match wins
# per line, and more specific patterns are listed before generic ones.
_SIGNATURES: list[tuple[str, re.Pattern]] = [
    ("oom_killed", re.compile(r"\bOOMKilled\b|\bout of memory\b|\bMemoryError\b", re.IGNORECASE)),
    ("timeout", re.compile(r"\btimed?[ -]?out\b|\bdeadline exceeded\b", re.IGNORECASE)),
    ("permission_denied", re.compile(r"\bpermission denied\b|\b403 forbidden\b|\bunauthorized\b", re.IGNORECASE)),
    ("connection_error", re.compile(r"\bconnection refused\b|\bconnection reset\b|\bECONNREFUSED\b", re.IGNORECASE)),
    ("dependency_install_failure", re.compile(
        r"npm ERR!|ERESOLVE|could not find a version|pip.*(no matching distribution|failed building wheel)",
        re.IGNORECASE,
    )),
    ("docker_build_failure", re.compile(r"failed to solve|error building image|dockerfile.*not found", re.IGNORECASE)),
    ("test_failure", re.compile(r"\bFAILED\b|\bAssertionError\b|\d+ failed,?\s*\d*\s*passed", re.IGNORECASE)),
    ("python_traceback", re.compile(r"^Traceback \(most recent call last\):", re.MULTILINE)),
    ("generic_error", re.compile(r"^\s*(ERROR|Error:|error:)\b")),
    ("non_zero_exit", re.compile(r"exit code (\d+)|process completed with exit code (\d+)", re.IGNORECASE)),
]


def extract_errors(log_text: str, max_matches: int = 10) -> list[dict]:
    """Scan raw log text for known failure signatures.

    Returns a list of {"category": str, "line": str, "line_number": int},
    ordered by line number, deduplicated by category+line, capped at
    max_matches (logs are matched tail-first upstream by github_tools, so the
    most failure-relevant lines are already near the end).
    """
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    lines = log_text.splitlines()

    for i, line in enumerate(lines, start=1):
        for category, pattern in _SIGNATURES:
            if pattern.search(line):
                key = (category, line.strip())
                if key in seen:
                    continue
                seen.add(key)
                findings.append({"category": category, "line": line.strip()[:300], "line_number": i})
                break  # one category per line — avoid double-counting a single failure
        if len(findings) >= max_matches:
            break

    return findings


def summarize_categories(findings: list[dict]) -> dict:
    """Collapse a findings list into counts per category, most common first."""
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["category"]] = counts.get(f["category"], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))
