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


def test_pick_in_debug_mode_appends_suffix_to_system_prompt(mocker):
    from moodlist.agent import pick
    captured = {}

    def fake_llm_call(**kwargs):
        captured.update(kwargs)
        return {
            "picks": [1],
            "reasoning": "r",
            "wanted_but_missing": [],
            "needs_live": False,
            "pick_reasons": {"1": "because"},
        }

    mocker.patch("moodlist.agent.llm.call", side_effect=fake_llm_call)
    pick(
        query="q",
        library=[
            {"id": 1, "artist": "A", "title": "T1", "year": 2000},
            {"id": 2, "artist": "B", "title": "T2", "year": 2001},
        ],
        date_iso="2026-05-14",
        api_key="k", model="m", temperature=0.4,
        desired_count=2,
        debug=True,
    )
    assert "DIAGNOSTIC MODE" in captured["system"]


def test_pick_in_debug_mode_parses_pick_reasons(mocker):
    from moodlist.agent import pick
    mocker.patch("moodlist.agent.llm.call", return_value={
        "picks": [1, 2],
        "reasoning": "overall",
        "wanted_but_missing": [],
        "needs_live": False,
        "pick_reasons": {"1": "first reason", "2": "second reason"},
    })
    result = pick(
        query="q",
        library=[
            {"id": 1, "artist": "A", "title": "T1", "year": 2000},
            {"id": 2, "artist": "B", "title": "T2", "year": 2001},
        ],
        date_iso="2026-05-14",
        api_key="k", model="m", temperature=0.4,
        desired_count=2,
        debug=True,
    )
    assert result.pick_reasons == {1: "first reason", 2: "second reason"}
    assert result.raw_picks == [1, 2]


def test_pick_in_normal_mode_ignores_pick_reasons_field(mocker):
    from moodlist.agent import pick
    mocker.patch("moodlist.agent.llm.call", return_value={
        "picks": [1, 2],
        "reasoning": "r",
        "wanted_but_missing": [],
        "needs_live": False,
        "pick_reasons": {"1": "should be ignored"},
    })
    result = pick(
        query="q",
        library=[
            {"id": 1, "artist": "A", "title": "T1", "year": 2000},
            {"id": 2, "artist": "B", "title": "T2", "year": 2001},
        ],
        date_iso="2026-05-14",
        api_key="k", model="m", temperature=0.4,
        desired_count=2,
        debug=False,
    )
    assert result.pick_reasons == {}


def test_pick_sets_raw_picks_to_pre_validation_list(mocker):
    from moodlist.agent import pick
    mocker.patch("moodlist.agent.llm.call", return_value={
        "picks": [1, 99, 2],
        "reasoning": "r",
        "wanted_but_missing": [],
        "needs_live": False,
    })
    result = pick(
        query="q",
        library=[
            {"id": 1, "artist": "A", "title": "T1", "year": 2000},
            {"id": 2, "artist": "B", "title": "T2", "year": 2001},
        ],
        date_iso="2026-05-14",
        api_key="k", model="m", temperature=0.4,
        desired_count=2,
    )
    assert result.picks == [1, 2]
    assert result.raw_picks == [1, 99, 2]


def test_pick_accepts_small_count_from_query(mocker):
    """When the user's query asks for a small count (e.g. 'top 5'),
    Haiku returns that many picks; the threshold guard must not reject
    them just because desired_count default is larger."""
    mocker.patch("moodlist.agent.llm.call", return_value={
        "picks": [1, 2, 3, 4, 5],
        "reasoning": "five metal classics",
        "wanted_but_missing": [],
        "needs_live": False,
    })
    library = [
        {"id": i, "artist": f"A{i}", "title": f"T{i}", "year": 2000}
        for i in range(1, 11)
    ]
    result = pick(
        query="top 5 metal songs",
        library=library,
        date_iso="2026-05-14",
        api_key="k", model="m", temperature=0.4,
        desired_count=20,  # default; Haiku honored the query's "5"
    )
    assert result.picks == [1, 2, 3, 4, 5]


def test_pick_raises_when_agent_returns_empty_picks(mocker):
    """An empty picks list (no needs_live) should still raise."""
    mocker.patch("moodlist.agent.llm.call", return_value={
        "picks": [],
        "reasoning": "nothing matched",
        "wanted_but_missing": [],
        "needs_live": False,
    })
    with pytest.raises(AgentError, match="no picks"):
        pick(
            query="something obscure",
            library=[
                {"id": 1, "artist": "A", "title": "T1", "year": 2000},
            ],
            date_iso="2026-05-14",
            api_key="k", model="m", temperature=0.4,
            desired_count=20,
        )


def test_system_prompt_mentions_wanted_albums_field():
    from moodlist.agent import SYSTEM_PROMPT
    assert "wanted_albums" in SYSTEM_PROMPT


def test_wanted_albums_parsed_from_response(mocker):
    from moodlist.agent import pick
    from moodlist.types import WantedAlbum
    mocker.patch("moodlist.agent.llm.call", return_value={
        "picks": [1, 2],
        "reasoning": "r",
        "wanted_but_missing": ["Led Zeppelin - Whole Lotta Love"],
        "needs_live": False,
        "wanted_albums": [
            {"artist": "Led Zeppelin", "artist_ja": "レッド・ツェッペリン",
             "album": "Led Zeppelin II", "year": 1969},
        ],
    })
    result = pick(
        query="top rock",
        library=[
            {"id": 1, "artist": "A", "title": "T1", "year": 2000},
            {"id": 2, "artist": "B", "title": "T2", "year": 2001},
        ],
        date_iso="2026-05-15",
        api_key="k", model="m", temperature=0.4,
        desired_count=2,
    )
    assert len(result.wanted_albums) == 1
    assert isinstance(result.wanted_albums[0], WantedAlbum)
    assert result.wanted_albums[0].artist == "Led Zeppelin"
    assert result.wanted_albums[0].artist_ja == "レッド・ツェッペリン"
    assert result.wanted_albums[0].album == "Led Zeppelin II"
    assert result.wanted_albums[0].year == 1969


def test_wanted_albums_empty_when_field_missing(mocker):
    from moodlist.agent import pick
    mocker.patch("moodlist.agent.llm.call", return_value={
        "picks": [1, 2],
        "reasoning": "r",
        "wanted_but_missing": [],
        "needs_live": False,
        # no "wanted_albums" key
    })
    result = pick(
        query="q",
        library=[
            {"id": 1, "artist": "A", "title": "T1", "year": 2000},
            {"id": 2, "artist": "B", "title": "T2", "year": 2001},
        ],
        date_iso="2026-05-15",
        api_key="k", model="m", temperature=0.4,
        desired_count=2,
    )
    assert result.wanted_albums == []


def test_wanted_albums_skips_malformed_entries(mocker):
    from moodlist.agent import pick
    mocker.patch("moodlist.agent.llm.call", return_value={
        "picks": [1, 2],
        "reasoning": "r",
        "wanted_but_missing": [],
        "needs_live": False,
        "wanted_albums": [
            {"artist": "Good", "artist_ja": None, "album": "OK", "year": 2000},
            "this is not a dict",
            {"album": "Missing artist"},
            {"artist": "Only artist"},
            {"artist": "Bad year", "artist_ja": None,
             "album": "X", "year": "not a number"},
        ],
    })
    result = pick(
        query="q",
        library=[
            {"id": 1, "artist": "A", "title": "T1", "year": 2000},
            {"id": 2, "artist": "B", "title": "T2", "year": 2001},
        ],
        date_iso="2026-05-15",
        api_key="k", model="m", temperature=0.4,
        desired_count=2,
    )
    # Only the first entry is well-formed. The "Bad year" entry has
    # required fields but year=non-int — accepted, year coerced to None.
    assert len(result.wanted_albums) == 2
    albums = sorted(result.wanted_albums, key=lambda a: a.album)
    assert albums[0].album == "OK"
    assert albums[0].year == 2000
    assert albums[1].album == "X"
    assert albums[1].year is None
