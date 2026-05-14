# moodlist

Mood-based playlist builder for foobar2000 on macOS.

See `docs/superpowers/specs/2026-05-14-moodlist-design.md` for the design.

## Quickstart

1. `uv venv && source .venv/bin/activate`
2. `uv pip install -e ".[dev]"`
3. `cp config.example.toml ~/.moodlist/config.toml` (edit & add API key)
4. `moodlist --reindex`
5. `moodlist "top 80s metal"`

## Tests

`pytest`              — unit tests (no network)
`pytest -m e2e`       — end-to-end (real Anthropic API; needs key)
