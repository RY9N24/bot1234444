#!/usr/bin/env bash
set -euo pipefail

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

ensure_apt_packages() {
  if ! command_exists apt-get; then
    echo "apt-get is required to install missing dependencies. Please install python3 and pip3 manually." >&2
    exit 1
  fi

  echo "Updating package index..."
  apt-get update -y
  echo "Installing required system packages..."
  apt-get install -y python3 python3-pip python3-venv
}

if ! command_exists python3 || ! command_exists pip3; then
  ensure_apt_packages
fi

# Re-check to confirm installation succeeded
if ! command_exists python3; then
  echo "Python3 is required but could not be installed automatically." >&2
  exit 1
fi

if ! command_exists pip3; then
  echo "pip3 is required but could not be installed automatically." >&2
  exit 1
fi

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo "All dependencies installed."
