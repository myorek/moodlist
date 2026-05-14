#!/usr/bin/env bash
# Alfred Script Filter bridge for moodlist.
# {query} contains the user's typed query after the keyword.
set -euo pipefail

MOODLIST_VENV="${HOME}/projects/moodlist/.venv/bin/python"
FRESH_FLAG=""

# `ml!` workflow keyword sets MOODLIST_FRESH=1 in its env vars
if [[ "${MOODLIST_FRESH:-0}" == "1" ]]; then
  FRESH_FLAG="--fresh"
fi

"${MOODLIST_VENV}" -m moodlist.cli "$1" --alfred-json ${FRESH_FLAG}
