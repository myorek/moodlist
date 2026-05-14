from moodlist.types import Track
from moodlist.writer import open_in_foobar, slugify, write_m3u8


def _trk(i, artist="A", title="T", year=2000, path="/p.flac", dur=120):
    return Track(id=i, artist=artist, title=title, year=year,
                 album="", path=path, duration_sec=dur)


def test_slugify_lowercases_hyphens_strips_punctuation():
    assert slugify("Top 80s Metal!") == "top-80s-metal"
    assert slugify("More like Master of Puppets?") == "more-like-master-of-puppets"
    assert slugify("AC／DC live") == "acdc-live"


def test_write_m3u8_emits_extm3u_header_and_extinf_lines(tmp_path):
    tracks = [
        _trk(1, "Metallica", "Enter Sandman", 1991, "/m/enter.flac", 331),
        _trk(2, "Queen", "Bohemian Rhapsody", 1975, "/q/bohemian.flac", 354),
    ]
    out = write_m3u8(tracks, slug="rock-hits", year=2026, out_dir=tmp_path)
    assert out == tmp_path / "2026-rock-hits.m3u8"
    body = out.read_text(encoding="utf-8")
    assert body.startswith("#EXTM3U\n")
    assert "#EXTINF:331,Metallica - Enter Sandman\n/m/enter.flac\n" in body
    assert "#EXTINF:354,Queen - Bohemian Rhapsody\n/q/bohemian.flac\n" in body


def test_write_m3u8_overwrites_existing_file(tmp_path):
    write_m3u8([_trk(1, "A", "X")], slug="s", year=2026, out_dir=tmp_path)
    new = write_m3u8([_trk(2, "B", "Y")], slug="s", year=2026, out_dir=tmp_path)
    assert "B - Y" in new.read_text(encoding="utf-8")
    assert "A - X" not in new.read_text(encoding="utf-8")


def test_open_in_foobar_invokes_open_dash_a(mocker, tmp_path):
    run = mocker.patch("moodlist.writer.subprocess.run")
    p = tmp_path / "p.m3u8"
    p.write_text("#EXTM3U\n")
    open_in_foobar(p, app="foobar2000")
    run.assert_called_once_with(
        ["open", "-a", "foobar2000", str(p)], check=True
    )
