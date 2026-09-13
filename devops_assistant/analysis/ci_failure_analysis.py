"""ci_failure_analysis.py — Day 17: CI/CD failure analysis as a distinct,
testable function.

Combines a workflow run's job/step conclusions with (optional) per-job log
text into one structured explanation. Categorization is driven entirely by
log_analysis.extract_errors, so this module stays a thin combiner — the
regex work lives in exactly one place.
"""

from __future__ import annotations

from devops_assistant.analysis.log_analysis import extract_errors, summarize_categories

_CATEGORY_NEXT_STEPS = {
    "oom_killed": "Increase the job/container memory limit, or reduce memory usage "
                  "(e.g. stream large files instead of loading them fully).",
    "timeout": "Increase the step/job timeout, or investigate why the operation is "
               "slower than usual (network, contended resources, larger input).",
    "permission_denied": "Check the token/credential scopes used by this workflow "
                          "(repo secrets, GITHUB_TOKEN permissions block).",
    "connection_error": "Likely a transient network/infra issue — check the target "
                         "service's status; consider adding a retry.",
    "dependency_install_failure": "Pin the failing dependency to a known-good version; "
                                   "check for a lockfile drift or registry outage.",
    "docker_build_failure": "Check the Dockerfile path/context and that the base image "
                             "tag still exists.",
    "test_failure": "A test is failing — check whether it's a real regression from the "
                     "most recent commit(s) or a flaky/pre-existing test.",
    "python_traceback": "An unhandled exception occurred — read the traceback for the "
                         "exact line and exception type.",
    "generic_error": "Read the surrounding log lines for the specific tool/step that "
                      "reported the error.",
    "non_zero_exit": "A command exited non-zero — check which step it was and run it "
                      "locally to reproduce.",
}


def analyze_workflow_failure(
    run: dict, jobs: list[dict], logs_by_job: dict[int, str] | None = None
) -> dict:
    """Explain why a workflow run failed.

    Args:
        run: shape returned by github_tools.get_workflow_run.
        jobs: shape returned by github_tools.get_workflow_run_jobs.
        logs_by_job: optional {job_id: raw_log_text} for failed jobs, from
            github_tools.get_job_logs. If omitted, the analysis is limited to
            job/step conclusions (still useful, just less specific).

    Returns:
        {
          "run_id": int, "conclusion": str,
          "failed_jobs": [{"id", "name", "failed_steps": [...]}],
          "evidence": [{"category", "line", "line_number", "job"}],
          "likely_causes": [str],   # category names, most-evidenced first
          "suggested_next_steps": [str],
          "summary": str,
        }
    """
    logs_by_job = logs_by_job or {}
    failed_jobs = []
    evidence: list[dict] = []

    for job in jobs:
        if job.get("conclusion") not in ("failure", "timed_out", "cancelled"):
            continue
        failed_steps = [s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"]
        failed_jobs.append({"id": job["id"], "name": job["name"], "failed_steps": failed_steps})

        log_text = logs_by_job.get(job["id"])
        if log_text:
            for finding in extract_errors(log_text):
                evidence.append({**finding, "job": job["name"]})

    categories = summarize_categories(evidence)
    likely_causes = list(categories.keys())
    suggested_next_steps = [
        _CATEGORY_NEXT_STEPS[c] for c in likely_causes if c in _CATEGORY_NEXT_STEPS
    ]
    if not suggested_next_steps:
        suggested_next_steps = [
            "No log text was available to categorize the failure automatically — "
            "open the failed job's logs directly in the Actions UI."
        ]

    job_desc = ", ".join(f"{j['name']} ({', '.join(j['failed_steps']) or 'unknown step'})"
                          for j in failed_jobs) or "no job details available"
    summary = f"Run #{run.get('id')} concluded '{run.get('conclusion')}'. Failed job(s): {job_desc}."

    return {
        "run_id": run.get("id"),
        "conclusion": run.get("conclusion"),
        "failed_jobs": failed_jobs,
        "evidence": evidence,
        "likely_causes": likely_causes,
        "suggested_next_steps": suggested_next_steps,
        "summary": summary,
    }
