import shutil
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
