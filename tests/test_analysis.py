from devops_assistant.analysis.ci_failure_analysis import analyze_workflow_failure
from devops_assistant.analysis.commit_analysis import analyze_commits
from devops_assistant.analysis.deployment_troubleshooting import troubleshoot_deployment
from devops_assistant.analysis.log_analysis import extract_errors, summarize_categories
from devops_assistant.analysis.pr_review import review_pr

# --- log_analysis -------------------------------------------------------------


def test_extract_errors_finds_oom_and_traceback():
    log = "Step 1 ok\nContainer was OOMKilled\nTraceback (most recent call last):\n  File x"
    findings = extract_errors(log)
    categories = [f["category"] for f in findings]
    assert "oom_killed" in categories
    assert "python_traceback" in categories


def test_summarize_categories_counts_and_orders():
    findings = [{"category": "timeout"}, {"category": "timeout"}, {"category": "oom_killed"}]
    summary = summarize_categories(findings)
    assert list(summary.keys())[0] == "timeout"
    assert summary["timeout"] == 2


# --- ci_failure_analysis --------------------------------------------------------


def test_analyze_workflow_failure_uses_log_evidence():
    run = {"id": 1, "conclusion": "failure"}
    jobs = [{"id": 10, "name": "build", "conclusion": "failure",
             "steps": [{"name": "docker build", "conclusion": "failure"}]}]
    logs_by_job = {10: "error building image: context deadline exceeded"}
    result = analyze_workflow_failure(run, jobs, logs_by_job)
    assert result["run_id"] == 1
    assert result["failed_jobs"][0]["name"] == "build"
    assert "docker_build_failure" in result["likely_causes"] or result["likely_causes"]
    assert result["suggested_next_steps"]


def test_analyze_workflow_failure_without_logs_still_reports_failed_jobs():
    run = {"id": 2, "conclusion": "failure"}
    jobs = [{"id": 20, "name": "test", "conclusion": "failure",
             "steps": [{"name": "pytest", "conclusion": "failure"}]}]
    result = analyze_workflow_failure(run, jobs, logs_by_job=None)
    assert result["failed_jobs"][0]["failed_steps"] == ["pytest"]
    assert result["suggested_next_steps"]  # falls back to a generic next step


# --- commit_analysis -----------------------------------------------------------


def test_analyze_commits_flags_revert_and_fix_streak():
    commits = [
        {"sha": "aaa1111", "message": "fix: retry flaky step"},
        {"sha": "bbb2222", "message": "fix: retry again"},
        {"sha": "ccc3333", "message": "fixup: still broken"},
        {"sha": "ddd4444", "message": "Revert \"add caching\""},
    ]
    result = analyze_commits(commits)
    assert result["fix_streak"] == 3
    assert "ddd4444" in result["reverts"]
    assert any("fix" in flag.lower() for flag in result["flags"])


def test_analyze_commits_clean_history_has_no_flags():
    commits = [{"sha": "aaa1111", "message": "add new feature"}]
    result = analyze_commits(commits)
    assert result["flags"] == []


# --- pr_review -------------------------------------------------------------------


def test_review_pr_flags_large_diff_and_sensitive_paths():
    pr = {
        "number": 5, "title": "Update deploy workflow", "body": "",
        "additions": 400, "deletions": 300, "changed_files": 2,
        "files": [
            {"filename": ".github/workflows/deploy.yml", "additions": 350, "deletions": 300},
            {"filename": "README.md", "additions": 50, "deletions": 0},
        ],
    }
    result = review_pr(pr)
    assert result["risk"] in ("medium", "high")
    assert any("sensitive" in f.lower() for f in result["flags"])
    assert any("no pr description" in f.lower() for f in result["flags"])


def test_review_pr_small_clean_pr_is_low_risk():
    pr = {
        "number": 6, "title": "Fix typo in README", "body": "Fixes a typo.",
        "additions": 1, "deletions": 1, "changed_files": 1,
        "files": [{"filename": "README.md", "additions": 1, "deletions": 1}],
    }
    result = review_pr(pr)
    assert result["risk"] == "low"


# --- deployment_troubleshooting -------------------------------------------------


def test_troubleshoot_deployment_identifies_suspect_pr():
    run = {"id": 1, "conclusion": "failure", "head_sha": "aaa1111aaaa",
           "created_at": "2026-01-02T00:00:00Z"}
    jobs = [{"id": 10, "name": "build", "conclusion": "failure",
             "steps": [{"name": "docker build", "conclusion": "failure"}]}]
    recent_commits = [{"sha": "aaa1111", "message": "fix: bump base image"}]
    recent_prs = [{"number": 42, "merged_at": "2026-01-01T23:00:00Z"}]

    result = troubleshoot_deployment(run, jobs, recent_commits, recent_prs)
    assert result["suspect_pr"] == 42
    assert result["confidence"] in ("low", "medium", "high")
    assert "42" in result["hypothesis"]


def test_troubleshoot_deployment_low_confidence_with_no_signal():
    run = {"id": 2, "conclusion": "failure", "created_at": "2026-01-02T00:00:00Z"}
    jobs = []
    recent_commits = [{"sha": "bbb2222", "message": "add new feature"}]
    result = troubleshoot_deployment(run, jobs, recent_commits, recent_prs=[])
    assert result["confidence"] == "low"
    assert result["suspect_pr"] is None
