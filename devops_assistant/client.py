"""Thin wrapper around the Google Gen AI SDK (Gemini).

Switched from the Anthropic API to Gemini because Google AI Studio issues a
genuinely free API key (aistudio.google.com/apikey) with no billing/credit
card required, unlike the Anthropic API which has no free tier at all. The
project's *concepts* (Day 3-6) are provider-agnostic; only this file and
tools.py are Gemini-specific.

Demonstrates, deliberately explicitly (Day 4):
  - auth via environment variable, with a clear failure message if it's missing
  - a real request/response call
  - streaming
  - rate-limit / overload handling with backoff
  - explicit error handling instead of letting exceptions leak to the user

Model strings are current as of writing this project. If Google ships new
model names later, update DEFAULT_MODEL / AVAILABLE_MODELS here — see
https://ai.google.dev/gemini-api/docs/models for the current list and
https://ai.google.dev/gemini-api/docs/rate-limits for current free-tier limits.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Callable, Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from .prompts import (
    DEFAULT_QUESTION_TEMPLATE,
    REFINE_SYSTEM_PROMPT,
    SYSTEM_PROMPT_STREAM,
    SYSTEM_PROMPT_STRUCTURED,
    few_shot_messages,
)
from .tools import get_utc_time

# Day 5: model selection — quality vs. cost vs. latency is a real, visible tradeoff
# here, both currently free-tier eligible. Flash is the balanced default; Flash-Lite
# trades some quality for speed and a higher free-tier rate limit.
DEFAULT_MODEL = "gemini-3.5-flash"
AVAILABLE_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]

# Day 2: temperature — lower is more deterministic (good for a structured runbook
# you want to be reproducible), higher is more varied. Exposed as a CLI flag rather
# than hardcoded so the effect is something you can actually see, not just read about.
DEFAULT_TEMPERATURE = 0.3

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2

RUNBOOK_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "category": {"type": "string"},
        "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
        "root_cause": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}},
        "commands": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "code": {"type": "string"}},
                "required": ["label", "code"],
            },
        },
        "best_practices": {"type": "array", "items": {"type": "string"}},
        "references": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "category", "severity"],
}


class AssistantError(Exception):
    """Raised for any failure we want the CLI to report cleanly, without a stack trace."""


def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise AssistantError(
            "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey "
            "(no billing required), then export it locally, or add it as a repository secret "
            "named GEMINI_API_KEY if you're running this via GitHub Actions."
        )
    return genai.Client(api_key=api_key)


def _to_contents(messages: list[dict]) -> list:
    """Convert our internal [{role, content}] list into Gemini's Content objects.

    Internal role names ("user" / "assistant") map to Gemini's ("user" / "model").
    """
    contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
    return contents


def _with_retries(fn: Callable):
    """Call fn(), retrying on rate limits / transient overload with backoff."""
    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except genai_errors.ClientError as e:
            code = getattr(e, "code", None)
            if code == 429 and attempt < MAX_RETRIES - 1:
                last_error = e
                wait = BASE_BACKOFF_SECONDS * (2 ** attempt)
                print(f"  (rate limited — retrying in {wait}s...)", file=sys.stderr)
                time.sleep(wait)
                continue
            raise AssistantError(f"API request error ({code}): {e}") from e
        except genai_errors.ServerError as e:
            code = getattr(e, "code", None)
            if attempt < MAX_RETRIES - 1:
                last_error = e
                wait = BASE_BACKOFF_SECONDS * (2 ** attempt)
                print(f"  (API unavailable — retrying in {wait}s...)", file=sys.stderr)
                time.sleep(wait)
                continue
            raise AssistantError(f"API server error ({code}): {e}") from e
        except Exception as e:  # network errors, SDK-level issues, etc.
            raise AssistantError(f"Could not complete the request: {e}") from e
    raise AssistantError(f"Gave up after {MAX_RETRIES} attempts: {last_error}")


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise AssistantError("Model response did not contain a JSON object.")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as e:
        raise AssistantError(f"Model response was not valid JSON: {e}") from e


def ask_structured(
    question: str,
    model: str = DEFAULT_MODEL,
    context_messages: Optional[list] = None,
    max_tokens: int = 1024,
    temperature: float = DEFAULT_TEMPERATURE,
    use_few_shot: bool = True,
) -> dict:
    """Ask a question, get back a parsed structured runbook dict. (Day 3 + Day 4)

    Uses Gemini's native JSON mode (response_mime_type + response_schema) rather
    than asking nicely in the prompt and hoping — the API enforces the shape.

    Message order demonstrates two Day 3 techniques stacked deliberately:
      1. few-shot example(s) first, if enabled — shows the model the pattern
      2. prior context turns, if any (Day 6 memory / --continue)
      3. the actual question, rendered through the shared prompt template
    """
    client = get_client()
    messages: list = []
    if use_few_shot:
        messages.extend(few_shot_messages())
    messages.extend(context_messages or [])
    messages.append({"role": "user", "content": DEFAULT_QUESTION_TEMPLATE.render(question)})

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT_STRUCTURED,
        temperature=temperature,
        max_output_tokens=max_tokens,
        response_mime_type="application/json",
        response_schema=RUNBOOK_RESPONSE_SCHEMA,
    )

    def _call():
        return client.models.generate_content(model=model, contents=_to_contents(messages), config=config)

    response = _with_retries(_call)
    return _extract_json(response.text)


def refine_question(question: str, model: str = DEFAULT_MODEL) -> str:
    """Step 1 of a prompt chain (Day 3): rewrite a vague question precisely.

    The return value is meant to be passed straight into ask_structured() as
    its `question` argument — that hand-off is the chain.
    """
    client = get_client()
    config = types.GenerateContentConfig(
        system_instruction=REFINE_SYSTEM_PROMPT, temperature=0.2, max_output_tokens=200
    )

    def _call():
        return client.models.generate_content(
            model=model, contents=[types.Part.from_text(text=question)], config=config
        )

    response = _with_retries(_call)
    return response.text.strip().strip('"')


def ask_structured_chained(
    question: str, model: str = DEFAULT_MODEL, temperature: float = DEFAULT_TEMPERATURE
) -> tuple[str, dict]:
    """Full two-step chain (Day 3: prompt chaining): refine, then answer.

    Returns (refined_question, structured_answer) so callers can show both steps.
    """
    refined = refine_question(question, model=model)
    answer = ask_structured(refined, model=model, temperature=temperature)
    return refined, answer


def ask_streaming(
    question: str, model: str = DEFAULT_MODEL, temperature: float = DEFAULT_TEMPERATURE, on_token=None
) -> str:
    """Ask a question, streaming tokens live as they arrive. (Day 4)

    on_token defaults to printing to stdout as text arrives; pass a different
    callable to capture the stream instead (e.g. for tests).
    """
    on_token = on_token or (lambda t: print(t, end="", flush=True))
    client = get_client()
    config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT_STREAM, temperature=temperature)
    full_text = []

    def _call():
        for chunk in client.models.generate_content_stream(
            model=model, contents=[types.Part.from_text(text=question)], config=config
        ):
            if chunk.text:
                on_token(chunk.text)
                full_text.append(chunk.text)
        return "".join(full_text)

    return _with_retries(_call)


def ask_with_tools(question: str, model: str = DEFAULT_MODEL) -> str:
    """Ask a question, letting the model call the demo tool if it needs to. (Day 6)

    Automatic function calling is only supported via the Chat API in current
    SDK versions (direct Models.generate_content AFC is deprecated) — so this
    uses client.chats.create(...).send_message(...) rather than a raw
    generate_content call. The SDK still handles the whole request/execute/
    respond loop internally; we just hand it the plain Python function.
    """
    client = get_client()
    config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT_STREAM, tools=[get_utc_time])
    chat = client.chats.create(model=model, config=config)

    def _call():
        return chat.send_message(question)

    response = _with_retries(_call)
    return response.text
