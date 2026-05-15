from __future__ import annotations

import re
import unicodedata

# Tail patterns we treat as version markers and strip before final normalization.
# Order matters: longer/more specific first so partial matches don't preempt them.
_VERSION_TAIL_RE = re.compile(
    r"""
    \s*
    \(?                                   # optional opening paren
    (?:
        feat\.?\s.+                      |  # "feat. X" or "feat X"
        ft\.?\s.+                        |  # "ft. X"
        live                             |
        demo                             |
        b-?side                          |
        alternate\s+version              |
        extended\s+(?:mix|version)       |
        remaster(?:ed)?(?:\s+\d{4})?     |
        remix
    )
    \)?                                   # optional closing paren
    \s*$                                  # must be at end of string
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Punctuation to replace with a space before whitespace-collapse.
# Includes ASCII punctuation plus en/em dashes, fullwidth slash.
_PUNCT_RE = re.compile(r"""[.,;:"''`!?()\[\]{}\-—–/\\|]""")


def normalize_track_name(s: str) -> str:
    """Canonical key for a track name.

    Steps:
      1. NFKC unicode normalization (fullwidth → ASCII, ligatures, etc.)
      2. Strip version-marker tails like "(live)", "(remastered)",
         "feat. X" — these denote different cuts of the same recording.
      3. Replace punctuation with whitespace.
      4. Lowercase.
      5. Collapse all whitespace runs to a single space.
      6. Strip leading/trailing whitespace.
    """
    s = unicodedata.normalize("NFKC", s)
    # Iteratively strip version tails (a track may have stacked tails)
    while True:
        new = _VERSION_TAIL_RE.sub("", s).rstrip()
        if new == s:
            break
        s = new
    s = _PUNCT_RE.sub(" ", s)
    s = s.lower()
    s = " ".join(s.split())
    return s
