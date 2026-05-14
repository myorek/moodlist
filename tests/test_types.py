from moodlist.types import Track


def test_track_compact_dict_contains_only_id_artist_title_year():
    t = Track(id=1, artist="Metallica", title="Enter Sandman", year=1991,
              album="Black Album", path="/x.flac", duration_sec=331)
    assert t.compact() == {
        "id": 1,
        "artist": "Metallica",
        "title": "Enter Sandman",
        "year": 1991,
    }


def test_agent_result_default_raw_picks_and_pick_reasons():
    from moodlist.types import AgentResult
    r = AgentResult(picks=[1, 2], reasoning="r",
                    wanted_but_missing=[], needs_live=False)
    assert r.raw_picks == []
    assert r.pick_reasons == {}


def test_agent_result_accepts_raw_picks_and_pick_reasons():
    from moodlist.types import AgentResult
    r = AgentResult(picks=[1, 2], reasoning="r",
                    wanted_but_missing=[], needs_live=False,
                    raw_picks=[1, 2, 99], pick_reasons={1: "why one", 2: "why two"})
    assert r.raw_picks == [1, 2, 99]
    assert r.pick_reasons == {1: "why one", 2: "why two"}
