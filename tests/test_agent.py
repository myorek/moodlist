import pytest

from moodlist.agent import AgentError, build_user_blocks, pick

LIBRARY = [
    {"id": 1, "artist": "Metallica", "title": "Enter Sandman", "year": 1991},
    {"id": 2, "artist": "Queen", "title": "Bohemian Rhapsody", "year": 1975},
    {"id": 3, "artist": "AC/DC", "title": "Highway to Hell", "year": 1979},
]


def test_build_user_blocks_marks_library_with_cache_control():
    blocks = build_user_blocks(library=LIBRARY, query="top rock", date_iso="2026-05-14")
    assert len(blocks) == 2
    assert blocks[0]["type"] == "text"
    assert "Library:" in blocks[0]["text"]
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert "top rock" in blocks[1]["text"]
    assert "2026-05-14" in blocks[1]["text"]
    assert "cache_control" not in blocks[1]


def test_pick_returns_validated_ids(mocker):
    mocker.patch("moodlist.agent.llm.call", return_value={
        "picks": [1, 3], "reasoning": "two rock classics",
        "wanted_but_missing": [], "needs_live": False,
    })
    result = pick(query="top rock", library=LIBRARY, date_iso="2026-05-14",
                  api_key="k", model="m", temperature=0.4)
    assert result.picks == [1, 3]
    assert result.needs_live is False


def test_pick_drops_invalid_ids(mocker):
    mocker.patch("moodlist.agent.llm.call", return_value={
        "picks": [1, 99, 3], "reasoning": "r",
        "wanted_but_missing": [], "needs_live": False,
    })
    result = pick(query="q", library=LIBRARY, date_iso="2026-05-14",
                  api_key="k", model="m", temperature=0.4)
    assert result.picks == [1, 3]


def test_pick_raises_when_too_few_valid_ids(mocker):
    mocker.patch("moodlist.agent.llm.call", return_value={
        "picks": [99, 100], "reasoning": "r",
        "wanted_but_missing": [], "needs_live": False,
    })
    with pytest.raises(AgentError, match="too few valid"):
        pick(query="q", library=LIBRARY, date_iso="2026-05-14",
             api_key="k", model="m", temperature=0.4, desired_count=2)


def test_pick_needs_live_branch(mocker):
    mocker.patch("moodlist.agent.llm.call", return_value={
        "picks": [], "reasoning": "live data required",
        "wanted_but_missing": [], "needs_live": True,
    })
    result = pick(query="today's top rock", library=LIBRARY,
                  date_iso="2026-05-14", api_key="k", model="m", temperature=0.4)
    assert result.needs_live is True
    assert result.picks == []


def test_system_prompt_includes_count_override_instruction():
    from moodlist.agent import SYSTEM_PROMPT
    assert "If the user's query specifies a number of tracks" in SYSTEM_PROMPT


def test_user_blocks_say_default_count_not_desired_count():
    from moodlist.agent import build_user_blocks
    blocks = build_user_blocks(
        library=[{"id": 1, "artist": "A", "title": "T", "year": 2000}],
        query="top 10 rock",
        date_iso="2026-05-14",
        desired_count=20,
    )
    query_text = blocks[1]["text"]
    assert "Default count: 20" in query_text
    assert "Desired count" not in query_text
