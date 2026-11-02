#!/usr/bin/env bash
# Activate the project's Python virtual environment.
#
# Usage:
#   source scripts/activate.sh            # activate in the current shell
#   bash scripts/activate.sh <command>    # run a command inside the venv
#
# Example:
#   bash scripts/activate.sh python -m uvicorn main:app --reload --env-file config.env

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"

# Windows venvs use Scripts/, Linux/macOS venvs use bin/
if [ -f "$VENV_DIR/bin/activate" ]; then
    ACTIVATE="$VENV_DIR/bin/activate"
elif [ -f "$VENV_DIR/Scripts/activate" ]; then
    ACTIVATE="$VENV_DIR/Scripts/activate"
else
    echo "Virtual environment not found at $VENV_DIR" >&2
    echo "Create it with: python -m venv .venv" >&2
    return 1 2>/dev/null || exit 1
fi

# shellcheck disable=SC1090
source "$ACTIVATE"

# When executed (not sourced), run the given command inside the venv
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    if [ $# -eq 0 ]; then
        echo "Activated $VENV_DIR, but nothing to run (use 'source' to stay activated)." >&2
        exit 0
    fi
    exec "$@"
fi
