"""pr_review.py — Day 17: PR review as a distinct, testable function.

Purely heuristic (no LLM call) so it's fast, deterministic, and cheap enough
for the agent to run on every PR it looks at without burning a model call.
agent.py can still hand the result to the LLM afterwards for a natural-
language summary; the risk scoring itself stays deterministic and testable.
"""

from __future__ import annotations

LARGE_DIFF_LINES = 500
SENSITIVE_PATH_HINTS = (
    ".github/workflows/", "secrets", "credentials", ".env", "Dockerfile",
    "terraform", ".tf", "iam", "policy.json",
)
RISKY_TITLE_HINTS = ("wip", "do not merge", "dont merge", "hotfix", "revert")


def review_pr(pr: dict) -> dict:
    """Score a pull request's risk from its metadata + changed files.

    Args:
        pr: shape returned by github_tools.get_pull_request — must include
            title, body, additions, deletions, changed_files, files[].

    Returns:
        {"risk": "low"|"medium"|"high", "flags": [str], "summary": str}
    """
    flags: list[str] = []
    files = pr.get("files") or []
    total_lines = (pr.get("additions") or 0) + (pr.get("deletions") or 0)

    if total_lines > LARGE_DIFF_LINES:
        flags.append(f"Large diff ({total_lines} lines changed) — harder to review thoroughly")

    if not (pr.get("body") or "").strip():
        flags.append("No PR description — reviewers have no stated intent to check the diff against")

    title_lower = (pr.get("title") or "").lower()
    for hint in RISKY_TITLE_HINTS:
        if hint in title_lower:
            flags.append(f"Title suggests this PR is not ready or is a revert ('{hint}')")
            break

    touched_sensitive = [
        f["filename"] for f in files
        if any(hint.lower() in f["filename"].lower() for hint in SENSITIVE_PATH_HINTS)
    ]
    if touched_sensitive:
        flags.append(f"Touches sensitive/high-blast-radius paths: {', '.join(touched_sensitive[:5])}")

    single_file_dominant = None
    if files:
        biggest = max(files, key=lambda f: f["additions"] + f["deletions"])
        biggest_share = (biggest["additions"] + biggest["deletions"]) / max(total_lines, 1)
        if len(files) > 1 and biggest_share > 0.8:
            single_file_dominant = biggest["filename"]
            flags.append(
                f"Diff is dominated by a single file ({single_file_dominant}, "
                f"{biggest_share:.0%} of changed lines) — worth checking that's intentional"
            )

    if len(touched_sensitive) >= 2 or total_lines > LARGE_DIFF_LINES * 2:
        risk = "high"
    elif touched_sensitive or total_lines > LARGE_DIFF_LINES or len(flags) >= 2:
        risk = "medium"
    else:
        risk = "low"

    summary = (
        f"PR #{pr.get('number')} ('{pr.get('title')}'): {total_lines} lines across "
        f"{len(files)} file(s), risk={risk}."
    )
    return {"risk": risk, "flags": flags, "summary": summary}
