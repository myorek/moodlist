from moodlist.wishlist import normalize_track_name


def test_normalize_lowercases_and_strips_whitespace():
    assert normalize_track_name("  Black Sabbath - Paranoid  ") == "black sabbath paranoid"


def test_normalize_handles_separator_variants():
    keys = {
        normalize_track_name("Black Sabbath - Paranoid"),
        normalize_track_name("Black Sabbath: Paranoid"),
        normalize_track_name("black sabbath – paranoid"),
        normalize_track_name("Black Sabbath -- Paranoid"),
        normalize_track_name("Black Sabbath / Paranoid"),
    }
    assert len(keys) == 1, f"expected one key, got {keys}"


def test_normalize_collapses_whitespace():
    assert normalize_track_name("Black   Sabbath\tParanoid") == "black sabbath paranoid"


def test_normalize_strips_parenthetical_live_demo_remaster_tails():
    base = normalize_track_name("Somebody to Love")
    assert normalize_track_name("Somebody to Love (live)") == base
    assert normalize_track_name("Somebody to Love (Live)") == base
    assert normalize_track_name("Somebody to Love (demo)") == base
    assert normalize_track_name("Somebody to Love (remastered)") == base
    assert normalize_track_name("Somebody to Love (remastered 2011)") == base
    assert normalize_track_name("Somebody to Love (alternate version)") == base
    assert normalize_track_name("Somebody to Love (extended mix)") == base


def test_normalize_strips_feat_suffix():
    base = normalize_track_name("Track Name")
    assert normalize_track_name("Track Name feat. Other Artist") == base
    assert normalize_track_name("Track Name ft. Other Artist") == base
    assert normalize_track_name("Track Name (feat. Other Artist)") == base


def test_normalize_preserves_year_when_inline():
    # Year inside parentheses that ISN'T a version marker stays as digits.
    assert normalize_track_name("For Whom the Bell Tolls (1986)") == "for whom the bell tolls 1986"


def test_normalize_handles_unicode_nfkc():
    # Fullwidth characters normalize to ASCII via NFKC.
    assert normalize_track_name("ＡＣ／ＤＣ - Highway") == "ac dc highway"


def test_normalize_empty_string_returns_empty():
    assert normalize_track_name("") == ""
    assert normalize_track_name("   ") == ""
