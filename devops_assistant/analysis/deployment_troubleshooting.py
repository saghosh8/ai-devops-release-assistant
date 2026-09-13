"""deployment_troubleshooting.py — Day 17: deployment troubleshooting as a
distinct, testable function.

The "top of the funnel" analysis function: ties ci_failure_analysis +
commit_analysis + PR context together into a single root-cause hypothesis,
by correlating the failing run's head commit against recent commits/PRs.
This is deliberately the most opinionated module in analysis/ — it's the one
that actually points at "here's probably why", not just "here's what
happened" — so its hypothesis is always returned alongside its evidence and
a confidence label, never as a bare assertion.
"""

from __future__ import annotations

from devops_assistant.analysis.ci_failure_analysis import analyze_workflow_failure
from devops_assistant.analysis.commit_analysis import analyze_commits


def troubleshoot_deployment(
    run: dict,
    jobs: list[dict],
    recent_commits: list[dict],
    recent_prs: list[dict] | None = None,
    logs_by_job: dict[int, str] | None = None,
) -> dict:
    """Produce a root-cause hypothesis for a failed deployment run.

    Args:
        run, jobs, logs_by_job: same shapes as ci_failure_analysis.
        recent_commits: shape returned by github_tools.list_recent_commits,
            most-recent-first.
        recent_prs: optional shape returned by github_tools.list_pull_requests
            (state="all"), used to name a likely-responsible PR if the head
            commit matches one that was just merged.

    Returns:
        {
          "ci_analysis": {...},           # from analyze_workflow_failure
          "commit_analysis": {...},       # from analyze_commits
          "suspect_commit": str | None,
          "suspect_pr": int | None,
          "confidence": "low"|"medium"|"high",
          "hypothesis": str,
        }
    """
    recent_prs = recent_prs or []
    ci = analyze_workflow_failure(run, jobs, logs_by_job)
    commit_summary = analyze_commits(recent_commits)

    head_sha = (run.get("head_sha") or "")[:7]
    suspect_commit = head_sha or (recent_commits[0]["sha"] if recent_commits else None)

    suspect_pr = None
    for pr in recent_prs:
        # A merged PR whose merge time is the closest preceding the run's
        # creation time is the most likely proximate cause — timestamp
        # comparison is done as ISO-8601 string comparison, which is valid
        # since GitHub returns UTC "YYYY-MM-DDTHH:MM:SSZ" timestamps.
        if pr.get("merged_at") and run.get("created_at") and pr["merged_at"] <= run["created_at"]:
            suspect_pr = pr["number"]
            break

    reasons = []
    confidence = "low"

    if commit_summary["reverts"]:
        reasons.append("recent revert commit(s) suggest an unstable branch state")
        confidence = "medium"
    if commit_summary["fix_streak"] >= 3:
        reasons.append("a streak of 'fix' commits suggests the root cause wasn't resolved earlier")
        confidence = "medium"
    if ci["likely_causes"]:
        reasons.append(f"log evidence points to: {', '.join(ci['likely_causes'])}")
        confidence = "high" if ci["evidence"] else confidence
    if suspect_pr is not None:
        reasons.append(f"PR #{suspect_pr} merged immediately before this run")
        if confidence == "low":
            confidence = "medium"

    if reasons:
        hypothesis = (
            f"Likely cause: {'; '.join(reasons)}. "
            f"Suspect commit: {suspect_commit or 'unknown'}"
            + (f", suspect PR: #{suspect_pr}." if suspect_pr else ".")
        )
    else:
        hypothesis = (
            "No strong correlating signal found in commit history, PR timing, or logs — "
            "treat this as likely infra/flake rather than a code regression until proven otherwise."
        )

    return {
        "ci_analysis": ci,
        "commit_analysis": commit_summary,
        "suspect_commit": suspect_commit,
        "suspect_pr": suspect_pr,
        "confidence": confidence,
        "hypothesis": hypothesis,
    }
