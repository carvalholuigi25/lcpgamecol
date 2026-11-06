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
# Linux/WSL uses its own venv: a venv's pyvenv.cfg can only point at one base
# interpreter, so sharing .venv with Windows breaks one side or the other.
if [ -z "$VENV_DIR" ]; then
    if [ "$(uname -s)" = "Linux" ]; then
        VENV_DIR="$PROJECT_ROOT/.venv-wsl"
    else
        VENV_DIR="$PROJECT_ROOT/.venv"
    fi
fi

# Windows venvs use Scripts/, Linux/macOS venvs use bin/
if [ -f "$VENV_DIR/bin/activate" ]; then
    ACTIVATE="$VENV_DIR/bin/activate"
elif [ -f "$VENV_DIR/Scripts/activate" ]; then
    ACTIVATE="$VENV_DIR/Scripts/activate"
else
    echo "Virtual environment not found at $VENV_DIR" >&2
    echo "Create it with: python3 -m venv $VENV_DIR" >&2
    return 1 2>/dev/null || exit 1
fi

# shellcheck disable=SC1090
source "$ACTIVATE"

# The activate script hardcodes the venv path it was created with, which is
# wrong under WSL (/mnt/c/...) - so set it from the real location
export VIRTUAL_ENV="$VENV_DIR"
export PATH="$(dirname "$ACTIVATE"):$PATH"

# When executed (not sourced), run the given command inside the venv
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    if [ $# -eq 0 ]; then
        echo "Activated $VENV_DIR, but nothing to run (use 'source' to stay activated)." >&2
        exit 0
    fi
    # A Windows venv run from WSL only has python.exe, pip.exe, ...
    if ! command -v "$1" >/dev/null 2>&1 && command -v "$1.exe" >/dev/null 2>&1; then
        set -- "$1.exe" "${@:2}"
    fi
    exec "$@"
fi
