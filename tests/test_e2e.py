"""End-to-end: hits the real Anthropic API. Opt-in via `pytest -m e2e`."""
import os

import pytest

from moodlist import agent

LIBRARY = [
    {"id": 1, "artist": "Metallica", "title": "Enter Sandman", "year": 1991},
    {"id": 2, "artist": "Metallica", "title": "Master of Puppets", "year": 1986},
    {"id": 3, "artist": "Queen", "title": "Bohemian Rhapsody", "year": 1975},
    {"id": 4, "artist": "AC/DC", "title": "Highway to Hell", "year": 1979},
    {"id": 5, "artist": "Iron Maiden", "title": "The Trooper", "year": 1983},
    {"id": 6, "artist": "Madonna", "title": "Like a Prayer", "year": 1989},
]


@pytest.mark.e2e
def test_pick_returns_metal_for_metal_query():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    result = agent.pick(
        query="80s metal",
        library=LIBRARY,
        date_iso="2026-05-14",
        api_key=api_key,
        model="claude-haiku-4-5-20251001",
        temperature=0.4,
        desired_count=3,
    )
    assert len(result.picks) >= 1
    # at least one of the metal tracks (1, 2, 5) made it in
    assert {1, 2, 5} & set(result.picks)
