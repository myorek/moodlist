from __future__ import annotations

import json
import re
import time
from typing import Any

from anthropic import Anthropic, APIConnectionError, APIStatusError


class ProviderError(RuntimeError):
    pass


class MalformedJSONError(RuntimeError):
    pass


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    candidates = []
    if text.startswith("{"):
        candidates.append(text)
    m = _JSON_FENCE_RE.search(text)
    if m:
        candidates.append(m.group(1))
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(text[first:last + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    raise MalformedJSONError(f"could not extract JSON from: {text[:200]}")


def call(
    *,
    api_key: str,
    model: str,
    system: str,
    user_blocks: list[dict],
    temperature: float,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    client = Anthropic(api_key=api_key)

    def _attempt():
        return client.messages.create(
            model=model,
            system=system,
            messages=[{"role": "user", "content": user_blocks}],
            temperature=temperature,
            max_tokens=max_tokens,
        )

    try:
        msg = _attempt()
    except (APIStatusError, APIConnectionError) as e:
        status = getattr(e, "status_code", None)
        if isinstance(e, APIStatusError) and status and 500 <= int(status) < 600:
            time.sleep(0.5)
            msg = _attempt()
        else:
            raise ProviderError(str(e)) from e

    text = "".join(b.text for b in msg.content if hasattr(b, "text"))
    return _extract_json(text)
