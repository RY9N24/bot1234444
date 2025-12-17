#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

run_apt() {
  if [ "${EUID:-$(id -u)}" -ne 0 ] && command_exists sudo; then
    sudo apt-get "$@"
  else
    apt-get "$@"
  fi
}

ensure_apt_packages() {
  if ! command_exists apt-get; then
    echo "apt-get is required to install missing dependencies. Please install python3 and pip3 manually." >&2
    exit 1
  fi

  echo "Updating package index..."
  run_apt update -y
  echo "Installing required system packages..."
  run_apt install -y python3 python3-pip python3-venv screen
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

cd "$SCRIPT_DIR"
python3 -m pip install --upgrade pip
python3 -m pip install -r "$SCRIPT_DIR/requirements.txt"

echo "All dependencies installed."
