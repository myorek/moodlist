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
