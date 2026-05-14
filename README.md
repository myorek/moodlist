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

## Alfred workflow setup

The Alfred workflow is built by hand once; the resulting
`moodlist.alfredworkflow` is committed to the `alfred/` directory.

1. Open Alfred Preferences → Workflows → `+` → Blank Workflow.
   - Name: `moodlist`. Bundle id: `com.myorek.moodlist`.

2. Add **three Script Filter** inputs:

   | Keyword         | env var          | Script body                                                    |
   | --------------- | ---------------- | -------------------------------------------------------------- |
   | `ml`            | `MOODLIST_FRESH=0` | `~/projects/moodlist/alfred/script-filter.sh "$1"`           |
   | `ml!`           | `MOODLIST_FRESH=1` | `~/projects/moodlist/alfred/script-filter.sh "$1"`           |
   | `ml-reindex`    | -                | `~/projects/moodlist/.venv/bin/python -m moodlist.cli --reindex --alfred-json` |

   For each: set "Script Filter argument" to required, language to
   `/bin/bash`, "with output" to `Alfred filters results`.

3. Add an **Open File** output. Wire each Script Filter's main output
   into Open File. Configure Open File to use `foobar2000` as the
   application.

4. From Alfred's workflow menu, **Export…** the workflow into
   `~/projects/moodlist/alfred/moodlist.alfredworkflow` and commit it.

5. Smoke test in Alfred:
   - `ml top 80s metal` → expect a result row, hit Enter, foobar opens
     a 20-track playlist.
   - `ml-reindex` → expect a row with the new track count.
