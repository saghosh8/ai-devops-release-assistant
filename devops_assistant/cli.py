"""Command-line entrypoint.

    python -m devops_assistant ask "why is my pod stuck in CrashLoopBackOff?"
    python -m devops_assistant ask "..." --model claude-haiku-4-5-20251001
    python -m devops_assistant ask "..." --markdown
    python -m devops_assistant ask "..." --continue
    python -m devops_assistant stream "..."
    python -m devops_assistant tools-demo "what time is it in UTC right now?"
    python -m devops_assistant history
"""

from __future__ import annotations

import argparse
import sys

from . import client, memory
from .formatter import print_structured, to_markdown
from .prompts import flag_suspicious_input


def _warn_if_suspicious(question: str) -> None:
    warning = flag_suspicious_input(question)
    if warning:
        print(f"warning: {warning}", file=sys.stderr)


def cmd_ask(args: argparse.Namespace) -> int:
    _warn_if_suspicious(args.question)
    try:
        context = memory.build_context_messages(turns=1) if args.continue_ else None
        data = client.ask_structured(
            args.question, model=args.model, context_messages=context, temperature=args.temperature
        )
    except client.AssistantError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.markdown:
        print(to_markdown(args.question, data))
    else:
        print_structured(args.question, data)

    memory.append_history(args.question, data.get("summary", ""))
    return 0


def cmd_stream(args: argparse.Namespace) -> int:
    _warn_if_suspicious(args.question)
    try:
        print(f"$ ask \"{args.question}\" (streaming)\n")
        client.ask_streaming(args.question, model=args.model, temperature=args.temperature)
        print("\n")
    except client.AssistantError as e:
        print(f"\nerror: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_chain_demo(args: argparse.Namespace) -> int:
    """Day 3: prompt chaining, made visible — shows the refined question that
    the raw one gets turned into before it ever reaches the structured prompt."""
    _warn_if_suspicious(args.question)
    try:
        refined, data = client.ask_structured_chained(args.question, model=args.model)
    except client.AssistantError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"\n$ ask \"{args.question}\" (chained)")
    print(f"  → step 1 refined to: \"{refined}\"\n")
    print_structured(refined, data)
    memory.append_history(args.question, data.get("summary", ""))
    return 0


def cmd_tools_demo(args: argparse.Namespace) -> int:
    try:
        answer = client.ask_with_tools(args.question, model=args.model)
    except client.AssistantError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"\n$ ask \"{args.question}\" (tools enabled)\n\n{answer}\n")
    return 0


def cmd_history(_args: argparse.Namespace) -> int:
    history = memory.load_history()
    if not history:
        print("No previous queries yet.")
        return 0
    for i, entry in enumerate(history, 1):
        print(f"{i}. {entry['question']}")
        if entry.get("summary"):
            print(f"   {entry['summary']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devops-assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    ask_p = sub.add_parser("ask", help="Ask a question, get a structured runbook back")
    ask_p.add_argument("question")
    ask_p.add_argument("--model", default=client.DEFAULT_MODEL, choices=client.AVAILABLE_MODELS)
    ask_p.add_argument(
        "--temperature", type=float, default=client.DEFAULT_TEMPERATURE,
        help="0.0 = deterministic, 1.0 = more varied (default: %(default)s)",
    )
    ask_p.add_argument("--markdown", action="store_true", help="Print Markdown instead of ANSI")
    ask_p.add_argument(
        "--continue", dest="continue_", action="store_true",
        help="Fold the last saved exchange in as context (follow-up questions)",
    )
    ask_p.set_defaults(func=cmd_ask)

    stream_p = sub.add_parser("stream", help="Ask a question, streaming the raw answer live")
    stream_p.add_argument("question")
    stream_p.add_argument("--model", default=client.DEFAULT_MODEL, choices=client.AVAILABLE_MODELS)
    stream_p.add_argument("--temperature", type=float, default=client.DEFAULT_TEMPERATURE)
    stream_p.set_defaults(func=cmd_stream)

    chain_p = sub.add_parser(
        "chain-demo", help="Refine the question, then answer it (prompt chaining demo)"
    )
    chain_p.add_argument("question")
    chain_p.add_argument("--model", default=client.DEFAULT_MODEL, choices=client.AVAILABLE_MODELS)
    chain_p.set_defaults(func=cmd_chain_demo)

    tools_p = sub.add_parser("tools-demo", help="Ask a question with tool-use enabled")
    tools_p.add_argument("question")
    tools_p.add_argument("--model", default=client.DEFAULT_MODEL, choices=client.AVAILABLE_MODELS)
    tools_p.set_defaults(func=cmd_tools_demo)

    history_p = sub.add_parser("history", help="Show recently asked questions")
    history_p.set_defaults(func=cmd_history)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
