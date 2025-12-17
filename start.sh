#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION_NAME="telegram_notification_bot"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python3"

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

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Не найден виртуальный интерпретатор $PYTHON_BIN. Сначала выполните ./install.sh" >&2
  exit 1
fi

if ! command_exists screen; then
  if command_exists apt-get; then
    echo "Installing screen for background execution..."
    run_apt update -y
    run_apt install -y screen
  else
    echo "screen is required but apt-get is unavailable; please install screen manually." >&2
    exit 1
  fi
fi

if screen -list | grep -q "\.${SESSION_NAME}\b"; then
  echo "Screen session '${SESSION_NAME}' is already running. Attach with: screen -r ${SESSION_NAME}"
  exit 0
fi

cd "$SCRIPT_DIR"
screen -dmS "$SESSION_NAME" bash -c "cd '$SCRIPT_DIR' && '$PYTHON_BIN' -m bot.bot_app"
echo "Bot started in screen session '${SESSION_NAME}'. Detach/attach with: screen -r ${SESSION_NAME}"
