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


def test_wanted_album_carries_artist_album_and_optional_fields():
    from moodlist.types import WantedAlbum
    a = WantedAlbum(
        artist="Led Zeppelin",
        artist_ja="レッド・ツェッペリン",
        album="Led Zeppelin II",
        year=1969,
    )
    assert a.artist == "Led Zeppelin"
    assert a.artist_ja == "レッド・ツェッペリン"
    assert a.album == "Led Zeppelin II"
    assert a.year == 1969


def test_wanted_album_accepts_none_for_japanese_and_year():
    from moodlist.types import WantedAlbum
    a = WantedAlbum(artist="AC/DC", artist_ja=None, album="Back in Black",
                    year=None)
    assert a.artist_ja is None
    assert a.year is None


def test_agent_result_default_wanted_albums_is_empty_list():
    from moodlist.types import AgentResult
    r = AgentResult(picks=[1], reasoning="r", wanted_but_missing=[],
                    needs_live=False)
    assert r.wanted_albums == []


def test_agent_result_accepts_wanted_albums():
    from moodlist.types import AgentResult, WantedAlbum
    r = AgentResult(
        picks=[1], reasoning="r", wanted_but_missing=[], needs_live=False,
        wanted_albums=[WantedAlbum(artist="A", artist_ja=None,
                                   album="X", year=None)],
    )
    assert len(r.wanted_albums) == 1
    assert r.wanted_albums[0].album == "X"
