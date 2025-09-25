#!/usr/bin/env bash
set -euo pipefail

# Project root: this script should live in the root
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PY=${PYTHON:-python3}

if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  "$PY" -m venv venv
fi

source "venv/bin/activate"
python -m pip install --upgrade pip
pip install -r requirements.txt

exec python main.py
