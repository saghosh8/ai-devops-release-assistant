from devops_assistant.formatter import to_markdown

SAMPLE = {
    "summary": "Your pod is failing its readiness probe.",
    "category": "Kubernetes",
    "severity": "warning",
    "root_cause": "The app takes longer to boot than the probe's initialDelaySeconds.",
    "steps": ["Check pod events", "Increase initialDelaySeconds", "Redeploy"],
    "commands": [{"label": "Check events", "code": "kubectl describe pod <name>"}],
    "best_practices": ["Set generous readiness probe delays for JVM apps"],
    "references": ["Kubernetes probes documentation"],
}


def test_to_markdown_includes_all_sections():
    md = to_markdown("why is my pod crashing?", SAMPLE)
    assert "### Summary" in md
    assert "### Root cause" in md
    assert "### Steps to resolve" in md
    assert "kubectl describe pod" in md
    assert "### Best practices" in md
    assert "### References" in md
    assert "🟡 warning" in md


def test_to_markdown_skips_empty_sections():
    minimal = {"summary": "Out of scope.", "category": "Out of scope", "severity": "info"}
    md = to_markdown("what's the weather?", minimal)
    assert "### Summary" in md
    assert "### Steps to resolve" not in md
    assert "### Commands" not in md
