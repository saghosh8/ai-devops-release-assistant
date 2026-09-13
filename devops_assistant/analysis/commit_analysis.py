"""commit_analysis.py — Day 17: commit-history analysis as a distinct,
testable function.

Looks for patterns in a list of recent commit messages that correlate with
instability: reverts, repeated "fix"/"hotfix" chains (a sign something
wasn't actually fixed the first time), and force-push-shaped history. Purely
string/heuristic-based — no LLM call, no network access.
"""

from __future__ import annotations

import re

REVERT_RE = re.compile(r"\brevert\b", re.IGNORECASE)
FIX_RE = re.compile(r"\b(fix|hotfix|fixup|bugfix)\b", re.IGNORECASE)
WIP_RE = re.compile(r"\b(wip|temp|do not merge)\b", re.IGNORECASE)


def analyze_commits(commits: list[dict]) -> dict:
    """Summarize risk signals across a list of recent commits.

    Args:
        commits: shape returned by github_tools.list_recent_commits — each
            needs at least "sha" and "message", most-recent-first.

    Returns:
        {
          "reverts": [sha, ...],
          "fix_streak": int,   # consecutive most-recent commits matching FIX_RE
          "wip_commits": [sha, ...],
          "flags": [str],
          "summary": str,
        }
    """
    reverts = [c["sha"] for c in commits if REVERT_RE.search(c.get("message", ""))]
    wip_commits = [c["sha"] for c in commits if WIP_RE.search(c.get("message", ""))]

    fix_streak = 0
    for c in commits:  # commits are most-recent-first
        if FIX_RE.search(c.get("message", "")):
            fix_streak += 1
        else:
            break

    flags: list[str] = []
    if reverts:
        flags.append(f"{len(reverts)} revert commit(s) in recent history: {', '.join(reverts)}")
    if fix_streak >= 3:
        flags.append(
            f"{fix_streak} consecutive 'fix'-style commits — the underlying issue may not "
            f"actually be fixed yet, just patched repeatedly"
        )
    if wip_commits:
        flags.append(f"WIP/temp commit(s) present on the branch: {', '.join(wip_commits)}")

    summary = (
        f"{len(commits)} commit(s) reviewed: {len(reverts)} revert(s), "
        f"fix-streak={fix_streak}, {len(wip_commits)} WIP commit(s)."
    )
    return {
        "reverts": reverts,
        "fix_streak": fix_streak,
        "wip_commits": wip_commits,
        "flags": flags,
        "summary": summary,
    }
