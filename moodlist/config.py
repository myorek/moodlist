from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    api_key: str
    model: str
    library_root: Path
    extensions: list[str]
    foobar_app: str
    default_count: int
    temperature: float
    moodlist_dir: Path


def load_config(path: Path | None = None) -> Config:
    cfg_path = path or (Path.home() / ".moodlist" / "config.toml")
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"config not found at {cfg_path}; copy config.example.toml there"
        )
    with cfg_path.open("rb") as f:
        data = tomllib.load(f)
    try:
        api_key = data["anthropic"]["api_key"]
    except KeyError as e:
        raise ValueError("anthropic.api_key missing from config") from e
    return Config(
        api_key=api_key,
        model=data["anthropic"].get("model", "claude-haiku-4-5-20251001"),
        library_root=Path(data["library"]["root"]).expanduser(),
        extensions=list(data["library"].get("extensions", ["flac"])),
        foobar_app=data.get("foobar2000", {}).get("app", "foobar2000"),
        default_count=int(data.get("playlist", {}).get("default_count", 20)),
        temperature=float(data.get("playlist", {}).get("temperature", 0.4)),
        moodlist_dir=cfg_path.parent,
    )
