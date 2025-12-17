#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python3 is required. Install python3 before running this script." >&2
  exit 1
fi

if ! command -v pip3 >/dev/null 2>&1; then
  echo "pip3 is required. Install pip3 before running this script." >&2
  exit 1
fi

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo "All dependencies installed."
