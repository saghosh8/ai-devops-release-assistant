"""A single, deliberately small tool-calling example (Day 6: Tools).

Gemini's SDK supports *automatic* function calling: hand it a plain Python
function with type hints and a docstring, and the SDK extracts the schema,
calls it when the model asks, and feeds the result back — no manual loop
needed. `get_utc_time` is safe, deterministic, and needs no network access,
so the demo works the same everywhere.
"""

from datetime import datetime, timezone


def get_utc_time() -> str:
    """Get the current UTC date and time.

    Useful when a DevOps answer needs to reason about 'now' — e.g.
    certificate expiry, log timestamps, or cron schedules.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
