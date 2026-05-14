from __future__ import annotations

import json
import math

from . import llm
from .types import AgentResult


class AgentError(RuntimeError):
    pass


SYSTEM_PROMPT = """\
You are a music-playlist curator. The user has a fixed local library
represented as a list of [id, artist, title, year] objects. Pick tracks
by INTEGER ID. Never invent IDs that aren't in the list.

- Prefer studio versions over demos/live/B-sides unless the query
  explicitly asks otherwise.
- For "top X" queries, use your knowledge of canonical hits from that
  era/genre. Cross-reference against the library.
- If the query asks about CURRENT charts ("today", "this week",
  "currently trending"), respond with {"needs_live": true, ...}
  instead of picking — do not guess current data.
- Provide a one-line reasoning suitable for showing to the user.
- If you know of canonical tracks that match the query but are NOT in
  this library, list them in `wanted_but_missing` (max 5).

Respond with JSON only, matching this schema:
{
  "picks":              [int],
  "reasoning":          string,
  "wanted_but_missing": [string],
  "needs_live":         boolean
}
"""


def build_user_blocks(library: list[dict], query: str, date_iso: str,
                      desired_count: int = 20) -> list[dict]:
    lib_text = "Library:\n" + json.dumps(library, ensure_ascii=False)
    query_text = (
        f"Query: \"{query}\"\n"
        f"Date: {date_iso}\n"
        f"Desired count: {desired_count}"
    )
    return [
        {"type": "text", "text": lib_text,
         "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": query_text},
    ]


def pick(
    *,
    query: str,
    library: list[dict],
    date_iso: str,
    api_key: str,
    model: str,
    temperature: float,
    desired_count: int = 20,
) -> AgentResult:
    blocks = build_user_blocks(library, query, date_iso, desired_count)
    raw = llm.call(
        api_key=api_key,
        model=model,
        system=SYSTEM_PROMPT,
        user_blocks=blocks,
        temperature=temperature,
    )
    picks: list[int] = list(raw.get("picks", []))
    needs_live = bool(raw.get("needs_live", False))
    reasoning = str(raw.get("reasoning", ""))
    wbm = list(raw.get("wanted_but_missing", []))

    valid_ids = {t["id"] for t in library}
    filtered = [p for p in picks if isinstance(p, int) and p in valid_ids]

    if not needs_live:
        threshold = math.floor(0.5 * min(desired_count, len(library)))
        if len(filtered) < threshold:
            raise AgentError(
                f"too few valid IDs ({len(filtered)}); rejecting playlist"
            )

    return AgentResult(picks=filtered, reasoning=reasoning,
                       wanted_but_missing=wbm, needs_live=needs_live)
