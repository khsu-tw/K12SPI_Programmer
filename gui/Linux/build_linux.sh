#!/usr/bin/env bash
# Build the GUI into a standalone Ubuntu/Linux executable (run on Ubuntu, or via build_linux_docker.bat on Windows).
# Output: gui/Linux/dist/K1V2SPI_Programmer   Work files: gui/Linux/build
# Needs: python3, python3-venv, python3-tk, binutils (apt install python3-venv python3-tk binutils)
set -e
cd "$(dirname "$0")/../.."
VENV="${MX25_BUILD_VENV:-/tmp/mx25_build_venv}"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check -q -r gui/requirements-dev.txt
"$VENV/bin/python" -m PyInstaller --noconfirm --onefile --windowed --name K1V2SPI_Programmer \
    --distpath gui/Linux/dist --workpath gui/Linux/build --specpath gui/Linux/build gui/mx25s1633_gui.py
echo
echo "Done:  $PWD/gui/Linux/dist/K1V2SPI_Programmer"
