#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-dry-run}"

if [[ "$MODE" != "dry-run" && "$MODE" != "apply" ]]; then
  echo "Usage: $0 [dry-run|apply]" >&2
  exit 2
fi

if [[ "$(id -u)" != "0" ]]; then
  echo "Run as root on the RU server." >&2
  exit 1
fi

NL_HOST="${NL_HOST:-5.129.239.104}"
NL_USER="${NL_USER:-root}"
NL_KEY="${NL_KEY:-/root/.ssh/chto_poest_reverse_tunnel}"
NL_EXPORT_DIR="${NL_EXPORT_DIR:-/root/temichevvet_db_exports}"
NL_PWA_DB="${NL_PWA_DB:-/root/temichevvet_pwa/pwa.db}"
NL_BOT_DB="${NL_BOT_DB:-/root/temichevvet_bot/bot.db}"

RU_ROOT="${RU_ROOT:-/opt/temichevvet}"
RU_DATA_DIR="${RU_DATA_DIR:-$RU_ROOT/data}"
RU_RELEASES_DIR="${RU_RELEASES_DIR:-$RU_ROOT/releases}"
RU_OWNER="${RU_OWNER:-temichevvet:temichevvet}"

STAMP="$(date -u +%Y%m%d_%H%M%S)"
WORK_DIR="$RU_RELEASES_DIR/db-sync-$STAMP"

SSH_OPTS=(
  -i "$NL_KEY"
  -o BatchMode=yes
  -o StrictHostKeyChecking=accept-new
  -o ServerAliveInterval=20
)

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "Missing file: $path" >&2
    exit 1
  fi
}

check_sqlite() {
  local db_path="$1"
  python3 - "$db_path" <<'PY'
import sqlite3
import sys

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
result = conn.execute("PRAGMA integrity_check").fetchone()[0]
if result != "ok":
    raise SystemExit(f"{db_path}: integrity_check failed: {result}")
print(f"{db_path}: ok")
PY
}

require_file "$NL_KEY"
mkdir -p "$WORK_DIR"
chmod 700 "$WORK_DIR"

echo "Creating SQLite backup snapshots on NL server..."
ssh "${SSH_OPTS[@]}" "$NL_USER@$NL_HOST" "
  set -euo pipefail
  mkdir -p '$NL_EXPORT_DIR'
  sqlite3 '$NL_PWA_DB' \".backup '$NL_EXPORT_DIR/pwa_$STAMP.db'\"
  sqlite3 '$NL_BOT_DB' \".backup '$NL_EXPORT_DIR/bot_$STAMP.db'\"
  chmod 600 '$NL_EXPORT_DIR/pwa_$STAMP.db' '$NL_EXPORT_DIR/bot_$STAMP.db'
"

echo "Downloading DB snapshots to $WORK_DIR..."
scp "${SSH_OPTS[@]}" "$NL_USER@$NL_HOST:$NL_EXPORT_DIR/pwa_$STAMP.db" "$WORK_DIR/pwa.db"
scp "${SSH_OPTS[@]}" "$NL_USER@$NL_HOST:$NL_EXPORT_DIR/bot_$STAMP.db" "$WORK_DIR/bot.db"
chmod 600 "$WORK_DIR/pwa.db" "$WORK_DIR/bot.db"

echo "Checking downloaded DB snapshots..."
check_sqlite "$WORK_DIR/pwa.db"
check_sqlite "$WORK_DIR/bot.db"

if [[ "$MODE" == "dry-run" ]]; then
  echo "Dry run completed. No RU database was changed."
  echo "Downloaded snapshots:"
  ls -lh "$WORK_DIR/pwa.db" "$WORK_DIR/bot.db"
  exit 0
fi

if systemctl is-active --quiet temichevvet_bot.service; then
  echo "Refusing to replace databases while RU Telegram bot is active." >&2
  exit 1
fi

echo "Applying DB snapshots to RU staging..."
systemctl stop temichevvet_pwa.service

cp -p "$RU_DATA_DIR/pwa.db" "$WORK_DIR/ru_before_pwa.db"
cp -p "$RU_DATA_DIR/bot.db" "$WORK_DIR/ru_before_bot.db"

install -o "${RU_OWNER%:*}" -g "${RU_OWNER#*:}" -m 0640 "$WORK_DIR/pwa.db" "$RU_DATA_DIR/pwa.db"
install -o "${RU_OWNER%:*}" -g "${RU_OWNER#*:}" -m 0640 "$WORK_DIR/bot.db" "$RU_DATA_DIR/bot.db"

check_sqlite "$RU_DATA_DIR/pwa.db"
check_sqlite "$RU_DATA_DIR/bot.db"

systemctl start temichevvet_pwa.service

echo "Apply completed."
echo "RU PWA restarted. RU Telegram bot remains inactive until explicit cutover."
