"""
analysis/ — Day 17 (PR review, commit analysis, CI/CD failure analysis, log
analysis, deployment troubleshooting) as distinct, testable functions.

Deliberately plain functions over plain dicts/lists in, structured dicts out —
no GitHub API calls happen inside this package. github_tools.py fetches the
data; agent.py wires the two together. That split is what makes every function
here testable with a handful of fixture dicts and no network access.
"""
