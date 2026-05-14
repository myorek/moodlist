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
- If the user's query specifies a number of tracks (e.g. "top 10",
  "5 songs", "a dozen tracks"), honor that number. Otherwise return
  the default count given below.
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


DEBUG_SUFFIX = """

DIAGNOSTIC MODE — include per-track reasons:

Additionally, return a `pick_reasons` field in your JSON: an object
keyed by each picked id (as a string), mapped to a one-sentence
explanation of why that specific track fits the query. Keep each
reason under 100 characters. Example:

  "pick_reasons": {
    "42": "Defining 1979 hard-rock single, anchors any rock canon",
    "17": "Most accessible Metallica track; 80s metal bedrock"
  }

The overall `reasoning` field stays as-is (one-line summary).
"""


def build_user_blocks(library: list[dict], query: str, date_iso: str,
                      desired_count: int = 20) -> list[dict]:
    lib_text = "Library:\n" + json.dumps(library, ensure_ascii=False)
    query_text = (
        f"Query: \"{query}\"\n"
        f"Date: {date_iso}\n"
        f"Default count: {desired_count}"
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
    debug: bool = False,
) -> AgentResult:
    blocks = build_user_blocks(library, query, date_iso, desired_count)
    system = SYSTEM_PROMPT + DEBUG_SUFFIX if debug else SYSTEM_PROMPT
    raw = llm.call(
        api_key=api_key,
        model=model,
        system=system,
        user_blocks=blocks,
        temperature=temperature,
    )
    raw_picks_list: list[int] = [
        p for p in raw.get("picks", []) if isinstance(p, int)
    ]
    needs_live = bool(raw.get("needs_live", False))
    reasoning = str(raw.get("reasoning", ""))
    wbm = list(raw.get("wanted_but_missing", []))

    valid_ids = {t["id"] for t in library}
    filtered = [p for p in raw_picks_list if p in valid_ids]

    pick_reasons: dict[int, str] = {}
    if debug:
        raw_reasons = raw.get("pick_reasons", {})
        if isinstance(raw_reasons, dict):
            for key, val in raw_reasons.items():
                try:
                    pick_reasons[int(key)] = str(val)
                except (TypeError, ValueError):
                    continue

    if not needs_live:
        # Reject only when most of Haiku's picks are unknown IDs (hallucination
        # guard). Anchored to raw_picks length, not desired_count, so small
        # counts honored from the query ("top 5") don't trigger a false alarm.
        if raw_picks_list:
            threshold = max(1, math.ceil(0.5 * len(raw_picks_list)))
            if len(filtered) < threshold:
                raise AgentError(
                    f"too few valid IDs ({len(filtered)} of "
                    f"{len(raw_picks_list)}); rejecting playlist"
                )
        else:
            raise AgentError("agent returned no picks; rejecting playlist")

    return AgentResult(
        picks=filtered,
        reasoning=reasoning,
        wanted_but_missing=wbm,
        needs_live=needs_live,
        raw_picks=raw_picks_list,
        pick_reasons=pick_reasons,
    )
