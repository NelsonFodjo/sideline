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
VENV_PYTHON=""
if [ -x "$VENV/bin/python" ]; then
    VENV_PYTHON="$VENV/bin/python"
elif [ -x "$VENV/Scripts/python.exe" ]; then
    VENV_PYTHON="$VENV/Scripts/python.exe"
elif [ -x "$VENV/Scripts/python" ]; then
    VENV_PYTHON="$VENV/Scripts/python"
fi

if [ -z "$VENV_PYTHON" ]; then
    echo "Creating Sideline's isolated Python environment..."
    if ! "$PYTHON" -m venv "$VENV"; then
        echo "Could not create .venv. Install Python's venv/ensurepip support and try again." >&2
        exit 1
    fi
    if [ -x "$VENV/bin/python" ]; then
        VENV_PYTHON="$VENV/bin/python"
    elif [ -x "$VENV/Scripts/python.exe" ]; then
        VENV_PYTHON="$VENV/Scripts/python.exe"
    elif [ -x "$VENV/Scripts/python" ]; then
        VENV_PYTHON="$VENV/Scripts/python"
    fi
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
