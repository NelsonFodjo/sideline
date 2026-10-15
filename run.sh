#!/usr/bin/env bash
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"

PYTHON="${PY:-}"
if [ -z "$PYTHON" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON=python3
    elif command -v python >/dev/null 2>&1; then
        PYTHON=python
    else
        echo "Sideline needs Python 3.8 or newer. Install Python and try again." >&2
        exit 1
    fi
fi

if ! command -v "$PYTHON" >/dev/null 2>&1 && [ ! -x "$PYTHON" ]; then
    echo "Python executable not found: $PYTHON" >&2
    exit 1
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)'; then
    echo "Sideline needs Python 3.8 or newer: $PYTHON is too old." >&2
    exit 1
fi

VENV="$ROOT/.venv"

find_venv_python() {
    VENV_PYTHON=""
    for candidate in "$VENV/bin/python" "$VENV/Scripts/python.exe" "$VENV/Scripts/python"; do
        # -x is false for a dangling symlink; running it proves the interpreter really works here
        # (a .venv copied from another machine points at a Python that does not exist).
        if [ -x "$candidate" ] && "$candidate" -c 'import sys' >/dev/null 2>&1; then
            VENV_PYTHON="$candidate"
            return
        fi
    done
}

find_venv_python
if [ -z "$VENV_PYTHON" ]; then
    if [ -e "$VENV" ]; then
        echo "The .venv here does not work on this machine (its Python is missing); rebuilding it..."
    else
        echo "Creating Sideline's isolated Python environment..."
    fi
    if ! "$PYTHON" -m venv --clear "$VENV"; then
        echo "Could not create .venv. Install Python's venv/ensurepip support and try again." >&2
        exit 1
    fi
    find_venv_python
fi

if [ -z "$VENV_PYTHON" ] || ! "$VENV_PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)'; then
    echo "The Python in .venv is too old or could not be found. Remove .venv and rerun with Python 3.8 or newer." >&2
    exit 1
fi

REQUIREMENTS_HASH="$("$VENV_PYTHON" -c \
    'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("requirements.txt").read_bytes()).hexdigest())')"
INSTALLED_HASH=""
if [ -f "$VENV/.sideline-requirements.sha256" ]; then
    INSTALLED_HASH="$(<"$VENV/.sideline-requirements.sha256")"
fi

if [ "$REQUIREMENTS_HASH" != "$INSTALLED_HASH" ] || \
   ! "$VENV_PYTHON" -c 'import boto3' >/dev/null 2>&1; then
    echo "Installing Sideline dependencies into .venv (first run or requirements changed)..."
    if ! "$VENV_PYTHON" -m pip install -r requirements.txt; then
        echo "Dependency installation failed. Check your internet connection and pip setup, then retry." >&2
        exit 1
    fi
    printf '%s\n' "$REQUIREMENTS_HASH" > "$VENV/.sideline-requirements.sha256"
fi

exec "$VENV_PYTHON" -m sideline "$@"
