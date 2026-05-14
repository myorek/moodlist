from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path

from .types import Track


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s-]+", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    s = re.sub(r"-+", "-", s)
    return s


def write_m3u8(tracks: list[Track], slug: str, year: int, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{year}-{slug}.m3u8"
    lines = ["#EXTM3U"]
    for t in tracks:
        lines.append(f"#EXTINF:{t.duration_sec},{t.artist} - {t.title}")
        lines.append(t.path)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def open_in_foobar(playlist: Path, app: str = "foobar2000") -> None:
    subprocess.run(["open", "-a", app, str(playlist)], check=True)
