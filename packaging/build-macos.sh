#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
.venv/bin/python -m unittest discover -s tests -v
PYINSTALLER_CONFIG_DIR="$PWD/build/pyinstaller-cache" .venv/bin/python -m PyInstaller --noconfirm --clean packaging/SJTURunning.spec
