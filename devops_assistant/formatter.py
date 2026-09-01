"""Render a structured runbook dict as either colored terminal text or Markdown.

Markdown output is what gets piped into $GITHUB_STEP_SUMMARY by the
ask-devops-assistant workflow, so the answer to a `workflow_dispatch` run
shows up formatted directly on the Actions run page.
"""

from __future__ import annotations

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
AMBER = "\033[33m"
RED = "\033[31m"
GREEN = "\033[32m"

SEVERITY_COLOR = {"info": GREEN, "warning": AMBER, "critical": RED}


def _color(text: str, code: str) -> str:
    return f"{code}{text}{RESET}"


def print_structured(question: str, data: dict) -> None:
    sev = data.get("severity", "info")
    sev_color = SEVERITY_COLOR.get(sev, GREEN)

    print()
    print(_color(f"$ ask \"{question}\"", DIM))
    print(
        f"{_color('[' + data.get('category', 'General') + ']', CYAN)} "
        f"{_color('[' + sev.upper() + ']', sev_color)}"
    )

    if data.get("summary"):
        print(f"\n{BOLD}§1 SUMMARY{RESET}")
        print(data["summary"])

    if data.get("root_cause"):
        print(f"\n{BOLD}§2 ROOT CAUSE{RESET}")
        print(_color(data["root_cause"], DIM))

    steps = data.get("steps") or []
    if steps:
        print(f"\n{BOLD}§3 STEPS TO RESOLVE{RESET}")
        for i, step in enumerate(steps, 1):
            print(f"  {_color(str(i) + '.', AMBER)} {step}")

    commands = data.get("commands") or []
    if commands:
        print(f"\n{BOLD}§4 COMMANDS{RESET}")
        for cmd in commands:
            print(f"  {_color(cmd.get('label', ''), DIM)}")
            print(f"  {_color('$', AMBER)} {cmd.get('code', '')}")

    best_practices = data.get("best_practices") or []
    if best_practices:
        print(f"\n{BOLD}§5 BEST PRACTICES{RESET}")
        for bp in best_practices:
            print(f"  {_color('›', AMBER)} {bp}")

    references = data.get("references") or []
    if references:
        print(f"\n{BOLD}§6 REFERENCES{RESET}")
        for i, ref in enumerate(references, 1):
            print(f"  [{i}] {_color(ref, DIM)}")
    print()


def to_markdown(question: str, data: dict) -> str:
    sev = data.get("severity", "info")
    sev_badge = {"info": "🟢 info", "warning": "🟡 warning", "critical": "🔴 critical"}.get(
        sev, sev
    )
    lines = [
        f"## 🛠️ DevOps Assistant — `{question}`",
        "",
        f"**Category:** {data.get('category', 'General')}  ·  **Severity:** {sev_badge}",
        "",
    ]

    if data.get("summary"):
        lines += ["### Summary", data["summary"], ""]

    if data.get("root_cause"):
        lines += ["### Root cause", data["root_cause"], ""]

    steps = data.get("steps") or []
    if steps:
        lines += ["### Steps to resolve"]
        lines += [f"{i}. {s}" for i, s in enumerate(steps, 1)]
        lines.append("")

    commands = data.get("commands") or []
    if commands:
        lines += ["### Commands"]
        for cmd in commands:
            lines.append(f"**{cmd.get('label', '')}**")
            lines.append("```bash")
            lines.append(cmd.get("code", ""))
            lines.append("```")
        lines.append("")

    best_practices = data.get("best_practices") or []
    if best_practices:
        lines += ["### Best practices"]
        lines += [f"- {b}" for b in best_practices]
        lines.append("")

    references = data.get("references") or []
    if references:
        lines += ["### References"]
        lines += [f"{i}. {r}" for i, r in enumerate(references, 1)]
        lines.append("")

    return "\n".join(lines)
