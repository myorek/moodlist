import json
import shutil
import time
from pathlib import Path

from mutagen.flac import FLAC

from moodlist.indexer import Indexer


def _tagged_flac(src: Path, dst: Path, **tags) -> Path:
    """Copy `src` to `dst` and apply tags via mutagen."""
    shutil.copy(src, dst)
    f = FLAC(str(dst))
    for k, v in tags.items():
        f[k.upper()] = str(v)
    f.save()
    return dst


def test_indexer_builds_sqlite_from_flac_files(temp_home, sample_flac, tmp_path):
    music = tmp_path / "Music"
    (music / "Metallica").mkdir(parents=True)
    _tagged_flac(sample_flac, music / "Metallica" / "01-enter-sandman.flac",
                 artist="Metallica", title="Enter Sandman",
                 album="Black Album", date="1991", tracknumber="1")

    ix = Indexer(library_root=music, moodlist_dir=temp_home)
    ix.build()

    tracks = ix.load_compact()
    assert len(tracks) == 1
    assert tracks[0]["artist"] == "Metallica"
    assert tracks[0]["title"] == "Enter Sandman"
    assert tracks[0]["year"] == 1991
    assert isinstance(tracks[0]["id"], int)


def test_library_version_changes_when_content_changes(temp_home, sample_flac, tmp_path):
    music = tmp_path / "Music"
    (music / "A").mkdir(parents=True)
    _tagged_flac(sample_flac, music / "A" / "a.flac",
                 artist="A", title="A1", date="2000")

    ix = Indexer(library_root=music, moodlist_dir=temp_home)
    ix.build()
    v1 = ix.library_version()

    (music / "B").mkdir(parents=True)
    _tagged_flac(sample_flac, music / "B" / "b.flac",
                 artist="B", title="B1", date="2001")
    ix.build()
    v2 = ix.library_version()
    assert v1 != v2
    assert len(v1) == 12 and len(v2) == 12


def test_is_stale_detects_new_artist_folder(temp_home, sample_flac, tmp_path):
    music = tmp_path / "Music"
    (music / "X").mkdir(parents=True)
    _tagged_flac(sample_flac, music / "X" / "x.flac",
                 artist="X", title="X1", date="1999")

    ix = Indexer(library_root=music, moodlist_dir=temp_home)
    ix.build()
    assert ix.is_stale() is False

    time.sleep(0.05)
    (music / "Y").mkdir()
    _tagged_flac(sample_flac, music / "Y" / "y.flac",
                 artist="Y", title="Y1", date="1999")
    assert ix.is_stale() is True


def test_indexer_handles_missing_year_tag(temp_home, sample_flac, tmp_path):
    music = tmp_path / "Music"
    music.mkdir()
    _tagged_flac(sample_flac, music / "z.flac",
                 artist="Z", title="No Year")
    ix = Indexer(library_root=music, moodlist_dir=temp_home)
    ix.build()
    assert ix.load_compact()[0]["year"] is None


def test_indexer_handles_unicode_artist(temp_home, sample_flac, tmp_path):
    music = tmp_path / "Music"
    music.mkdir()
    _tagged_flac(sample_flac, music / "u.flac",
                 artist="AC／DC", title="Highway to Hell", date="1979")
    ix = Indexer(library_root=music, moodlist_dir=temp_home)
    ix.build()
    assert ix.load_compact()[0]["artist"] == "AC／DC"


def test_library_cache_json_is_written(temp_home, sample_flac, tmp_path):
    music = tmp_path / "Music"
    music.mkdir()
    _tagged_flac(sample_flac, music / "a.flac",
                 artist="A", title="A1", date="2000")
    ix = Indexer(library_root=music, moodlist_dir=temp_home)
    ix.build()
    payload = json.loads((temp_home / "library.cache.json").read_text())
    assert payload[0]["artist"] == "A"
