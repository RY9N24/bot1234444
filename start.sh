#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION_NAME="telegram_notification_bot"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python3"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/bot.log"
TOKEN_FILE="$SCRIPT_DIR/TELEGRAM_TOKEN.txt"
ACTION="${1:-start}"

check_token() {
  if [ ! -s "$TOKEN_FILE" ]; then
    echo "Файл с токеном ($TOKEN_FILE) отсутствует или пуст. Добавьте токен и повторите запуск." >&2
    exit 1
  fi
  local token
  token=$(head -n 1 "$TOKEN_FILE" | tr -d '\r\n')
  if [[ "$token" == PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE* ]]; then
    echo "В файле $TOKEN_FILE оставлен плейсхолдер. Укажите реальный Telegram Bot API токен." >&2
    exit 1
  fi
}

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

is_session_running() {
  screen -list | grep -q "\\.${SESSION_NAME}\\b"
}

print_status() {
  if is_session_running; then
    echo "Screen session '${SESSION_NAME}' is running. Attach with: screen -r ${SESSION_NAME}"
    if [ -f "$LOG_FILE" ]; then
      echo "Последние строки лога:"
      tail -n 20 "$LOG_FILE"
    fi
    return 0
  fi

  echo "Сессия '${SESSION_NAME}' не найдена." >&2
  if [ -f "$LOG_FILE" ]; then
    echo "Последние строки лога:"
    tail -n 50 "$LOG_FILE" || true
  else
    echo "Лог-файл отсутствует. Запустите ./start.sh для создания." >&2
  fi
  return 1
}

if [ "$ACTION" = "status" ]; then
  print_status
  exit $?
fi

check_token

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
mkdir -p "$LOG_DIR"
echo "Starting bot in screen session '${SESSION_NAME}'..."
# tee сохраняет лог в файл и одновременно выводит в screen, чтобы при screen -x было видно отладку
screen -dmS "$SESSION_NAME" bash -c "cd '$SCRIPT_DIR' && set -o pipefail && exec '$PYTHON_BIN' -m bot.bot_app 2>&1 | tee -a '$LOG_FILE'"
sleep 1

if screen -list | grep -q "\.${SESSION_NAME}\b"; then
  echo "Bot started in screen session '${SESSION_NAME}'. Detach/attach with: screen -r ${SESSION_NAME}"
  echo "Логи: $LOG_FILE"
else
  echo "Не удалось запустить сессию screen '${SESSION_NAME}'. Проверяем лог запуска..." >&2
  if [ -f "$LOG_FILE" ]; then
    echo "Последние строки лога:" >&2
    tail -n 50 "$LOG_FILE" >&2 || true
  else
    echo "Лог-файл не создан. Проверьте наличие пакета screen и прав на /run/screen." >&2
  fi
  exit 1
fi
