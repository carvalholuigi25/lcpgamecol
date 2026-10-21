#!/bin/bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(dirname "$script_dir")"

if [[ -x "$project_root/.venv/bin/python" ]]; then
    PYTHON="$project_root/.venv/bin/python"
elif [[ -x "$project_root/.venv/Scripts/python.exe" ]]; then
    PYTHON="$project_root/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    echo "Error: Python was not found. Install Python or activate a virtual environment." >&2
    exit 127
fi

to_python_path() {
    if [[ "$PYTHON" == *.exe ]]; then
        if command -v wslpath >/dev/null 2>&1; then
            wslpath -w "$1"
        elif command -v cygpath >/dev/null 2>&1; then
            cygpath -w "$1"
        else
            echo "Error: cannot convert shell paths for Windows Python (wslpath/cygpath not found)." >&2
            exit 1
        fi
    else
        printf '%s\n' "$1"
    fi
}

cd "$project_root"
config_path="$(to_python_path "$script_dir/.coveragerc")"
json_path="$(to_python_path "$script_dir/coverage.json")"
html_path="$(to_python_path "$script_dir/coverage-report.html")"

"$PYTHON" -m coverage json --rcfile="$config_path" -o "$json_path"
PYTHON="$PYTHON" bash "$script_dir/coverage-report.sh" "$script_dir/coverage.json" "$script_dir/coverage-report.html"