#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
VENV="${MX25_VENV:-.venv}"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check -r requirements.txt
echo "Done. Python interpreter: $VENV/bin/python"
