import json
import sqlite3

from moodlist import cli
from moodlist.wishlist import WishlistDB


def _seed_library(temp_home):
    """Pre-populate library.sqlite + library.cache.json + library.version
       so the CLI doesn't try to scan ~/Music."""
    db = temp_home / "library.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE tracks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist TEXT, title TEXT, album TEXT DEFAULT '',
            year INTEGER, path TEXT UNIQUE, duration_sec INTEGER DEFAULT 0);
        INSERT INTO tracks(artist,title,year,path,duration_sec)
          VALUES ('Metallica','Enter Sandman',1991,'/m/es.flac',331);
        INSERT INTO tracks(artist,title,year,path,duration_sec)
          VALUES ('Queen','Bohemian Rhapsody',1975,'/q/br.flac',354);
    """)
    conn.commit()
    conn.close()
    compact = [
        {"id": 1, "artist": "Metallica", "title": "Enter Sandman", "year": 1991},
        {"id": 2, "artist": "Queen", "title": "Bohemian Rhapsody", "year": 1975},
    ]
    (temp_home / "library.cache.json").write_text(json.dumps(compact))
    (temp_home / "library.version").write_text("ver1")


def _write_config(temp_home, library_root):
    (temp_home / "config.toml").write_text(f"""
[anthropic]
api_key = "sk-test"
model   = "claude-haiku-4-5-20251001"

[library]
root = "{library_root}"
extensions = ["flac"]

[foobar2000]
app = "foobar2000"

[playlist]
default_count = 2
temperature   = 0.4
""")


def test_cache_miss_calls_agent_writes_playlist_stores_cache(temp_home, tmp_path,
                                                             mocker, capsys):
    _seed_library(temp_home)
    _write_config(temp_home, tmp_path / "Music")
    mocker.patch("moodlist.indexer.Indexer.is_stale", return_value=False)
    mocker.patch("moodlist.cli.agent.pick", return_value=mocker.MagicMock(
        picks=[1, 2], reasoning="picked classics",
        wanted_but_missing=[], needs_live=False,
    ))
    open_mock = mocker.patch("moodlist.writer.open_in_foobar")

    exit_code = cli.main(["top rock", "--alfred-json"])
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    item = out["items"][0]
    assert item["arg"].endswith(".m3u8")
    assert "top rock" in item["title"].lower() or "2 tracks" in item["title"]

    # cache row stored
    qcache = sqlite3.connect(temp_home / "query-cache.sqlite")
    row = qcache.execute("SELECT playlist_path FROM query_cache").fetchone()
    assert row is not None
    open_mock.assert_not_called()  # CLI emits JSON, Alfred opens later


def test_cache_hit_skips_agent(temp_home, tmp_path, mocker, capsys):
    _seed_library(temp_home)
    _write_config(temp_home, tmp_path / "Music")
    mocker.patch("moodlist.indexer.Indexer.is_stale", return_value=False)

    # First call: seed cache with a mocked agent response.
    first_pick = mocker.patch("moodlist.cli.agent.pick", return_value=mocker.MagicMock(
        picks=[1, 2], reasoning="r", wanted_but_missing=[], needs_live=False,
    ))
    cli.main(["top rock", "--alfred-json"])
    capsys.readouterr()
    assert first_pick.call_count == 1

    # Second call with same query: must be served from cache, agent not invoked.
    second_pick = mocker.patch("moodlist.cli.agent.pick")
    exit_code = cli.main(["top rock", "--alfred-json"])
    assert exit_code == 0
    second_pick.assert_not_called()
    out = json.loads(capsys.readouterr().out)
    assert "cached" in out["items"][0]["subtitle"].lower()


def test_fresh_flag_bypasses_cache(temp_home, tmp_path, mocker, capsys):
    _seed_library(temp_home)
    _write_config(temp_home, tmp_path / "Music")
    mocker.patch("moodlist.indexer.Indexer.is_stale", return_value=False)
    mocker.patch("moodlist.cli.agent.pick", return_value=mocker.MagicMock(
        picks=[1, 2], reasoning="r", wanted_but_missing=[], needs_live=False,
    ))

    cli.main(["top rock", "--alfred-json"])
    capsys.readouterr()
    pick_mock = mocker.patch("moodlist.cli.agent.pick", return_value=mocker.MagicMock(
        picks=[1, 2], reasoning="r", wanted_but_missing=[], needs_live=False,
    ))
    cli.main(["top rock", "--alfred-json", "--fresh"])
    pick_mock.assert_called_once()


def test_needs_live_branch_emits_helpful_alfred_message(temp_home, tmp_path,
                                                        mocker, capsys):
    _seed_library(temp_home)
    _write_config(temp_home, tmp_path / "Music")
    mocker.patch("moodlist.indexer.Indexer.is_stale", return_value=False)
    mocker.patch("moodlist.cli.agent.pick", return_value=mocker.MagicMock(
        picks=[], reasoning="needs live data",
        wanted_but_missing=[], needs_live=True,
    ))

    cli.main(["today's top rock", "--alfred-json"])
    out = json.loads(capsys.readouterr().out)
    assert out["items"][0]["valid"] is False
    assert "live" in out["items"][0]["title"].lower()


def test_debug_flag_prints_sections_to_stderr(temp_home, tmp_path,
                                                mocker, capsys):
    _seed_library(temp_home)
    _write_config(temp_home, tmp_path / "Music")
    mocker.patch("moodlist.indexer.Indexer.is_stale", return_value=False)
    mocker.patch("moodlist.cli.agent.pick", return_value=mocker.MagicMock(
        picks=[1, 2], reasoning="picked classics",
        wanted_but_missing=["Led Zeppelin - Stairway"],
        needs_live=False,
        raw_picks=[1, 2],
        pick_reasons={1: "first", 2: "second"},
    ))
    mocker.patch("moodlist.writer.open_in_foobar")

    exit_code = cli.main(["top rock", "--debug", "--dry-run"])
    assert exit_code == 0
    err = capsys.readouterr().err
    for marker in [
        "=== config ===",
        "=== library context ===",
        "=== query ===",
        "=== prompt ===",
        "=== haiku call ===",
        "=== haiku response ===",
        "=== validation ===",
        "=== output ===",
    ]:
        assert marker in err, f"missing diagnostic section: {marker}"
    # Per-track reasons should be visible
    assert "first" in err
    assert "second" in err
    # wanted_but_missing should be visible
    assert "Led Zeppelin" in err


def test_debug_flag_keeps_stdout_clean_for_alfred(temp_home, tmp_path,
                                                   mocker, capsys):
    _seed_library(temp_home)
    _write_config(temp_home, tmp_path / "Music")
    mocker.patch("moodlist.indexer.Indexer.is_stale", return_value=False)
    mocker.patch("moodlist.cli.agent.pick", return_value=mocker.MagicMock(
        picks=[1, 2], reasoning="r",
        wanted_but_missing=[],
        needs_live=False,
        raw_picks=[1, 2],
        pick_reasons={},
    ))

    cli.main(["top rock", "--debug", "--alfred-json"])
    out = capsys.readouterr().out
    # Stdout must be parseable JSON, not mixed with debug sections
    parsed = json.loads(out)
    assert "items" in parsed
    assert parsed["items"][0]["arg"].endswith(".m3u8")


def test_debug_flag_passes_debug_true_to_agent(temp_home, tmp_path,
                                                mocker, capsys):
    _seed_library(temp_home)
    _write_config(temp_home, tmp_path / "Music")
    mocker.patch("moodlist.indexer.Indexer.is_stale", return_value=False)
    pick_mock = mocker.patch("moodlist.cli.agent.pick", return_value=mocker.MagicMock(
        picks=[1, 2], reasoning="r",
        wanted_but_missing=[],
        needs_live=False,
        raw_picks=[1, 2],
        pick_reasons={},
    ))

    cli.main(["top rock", "--debug", "--dry-run"])
    pick_mock.assert_called_once()
    assert pick_mock.call_args.kwargs.get("debug") is True


def test_no_debug_flag_passes_debug_false_to_agent(temp_home, tmp_path,
                                                    mocker, capsys):
    _seed_library(temp_home)
    _write_config(temp_home, tmp_path / "Music")
    mocker.patch("moodlist.indexer.Indexer.is_stale", return_value=False)
    pick_mock = mocker.patch("moodlist.cli.agent.pick", return_value=mocker.MagicMock(
        picks=[1, 2], reasoning="r",
        wanted_but_missing=[],
        needs_live=False,
        raw_picks=[1, 2],
        pick_reasons={},
    ))

    cli.main(["another query", "--dry-run"])
    pick_mock.assert_called_once()
    # debug should be False (or absent — both acceptable)
    debug_arg = pick_mock.call_args.kwargs.get("debug", False)
    assert debug_arg is False


def test_wishlist_upsert_runs_on_cache_miss(temp_home, tmp_path, mocker):
    _seed_library(temp_home)
    _write_config(temp_home, tmp_path / "Music")
    mocker.patch("moodlist.indexer.Indexer.is_stale", return_value=False)
    mocker.patch("moodlist.cli.agent.pick", return_value=mocker.MagicMock(
        picks=[1, 2], reasoning="r",
        wanted_but_missing=["Led Zeppelin - Stairway to Heaven",
                            "Pink Floyd - Comfortably Numb"],
        needs_live=False,
        raw_picks=[1, 2],
        pick_reasons={},
    ))

    cli.main(["top rock", "--dry-run"])
    db = WishlistDB(temp_home / "wishlist.sqlite")
    assert db.count() == 2
    names = sorted(e.display_name for e in db.list(limit=None))
    assert names == ["Led Zeppelin - Stairway to Heaven",
                     "Pink Floyd - Comfortably Numb"]


def test_wishlist_skips_tracks_already_in_library(temp_home, tmp_path, mocker):
    """If Haiku suggests a track the user already owns (under any
    spelling), do NOT add it to the wishlist."""
    _seed_library(temp_home)
    _write_config(temp_home, tmp_path / "Music")
    mocker.patch("moodlist.indexer.Indexer.is_stale", return_value=False)
    # _seed_library inserts: Metallica - Enter Sandman, Queen - Bohemian Rhapsody
    mocker.patch("moodlist.cli.agent.pick", return_value=mocker.MagicMock(
        picks=[1, 2], reasoning="r",
        wanted_but_missing=[
            "Metallica – Enter Sandman",          # already owned, em dash
            "Led Zeppelin - Stairway to Heaven",  # not owned
        ],
        needs_live=False,
        raw_picks=[1, 2],
        pick_reasons={},
    ))

    cli.main(["top rock", "--dry-run"])
    db = WishlistDB(temp_home / "wishlist.sqlite")
    names = [e.display_name for e in db.list(limit=None)]
    assert names == ["Led Zeppelin - Stairway to Heaven"]
