from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Track:
    id: int
    artist: str
    title: str
    year: int | None
    album: str
    path: str
    duration_sec: int

    def compact(self) -> dict[str, Any]:
        """Minimal fields sent to the LLM. Year may be None."""
        return {
            "id": self.id,
            "artist": self.artist,
            "title": self.title,
            "year": self.year,
        }


@dataclass(frozen=True)
class WantedAlbum:
    artist: str
    artist_ja: str | None
    album: str
    year: int | None


@dataclass(frozen=True)
class AgentResult:
    picks: list[int]
    reasoning: str
    wanted_but_missing: list[str]
    needs_live: bool
    raw_picks: list[int] = field(default_factory=list)
    pick_reasons: dict[int, str] = field(default_factory=dict)
    wanted_albums: list[WantedAlbum] = field(default_factory=list)
