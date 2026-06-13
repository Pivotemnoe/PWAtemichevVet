#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${TEMICHEVVET_APP_DIR:-/opt/temichevvet/pwa}"
APP_URL="${TEMICHEVVET_APP_URL:-http://127.0.0.1:8081}"
ENV_FILE="${TEMICHEVVET_ENV_FILE:-${APP_DIR}/.env}"

SECRET="$("${APP_DIR}/.venv/bin/python" -c "from pathlib import Path
secret = ''
for line in Path('${ENV_FILE}').read_text(encoding='utf-8').splitlines():
    if line.startswith('MONITORING_API_SECRET='):
        secret = line.split('=', 1)[1].strip()
        break
print(secret)
")"

if [ -z "${SECRET}" ]; then
  echo "MONITORING_API_SECRET is not configured" >&2
  exit 1
fi

curl -fsS --max-time 25 -X POST "${APP_URL}/api/internal/push/followups/send?limit=50" \
  -H "X-Temichevvet-Monitoring-Secret: ${SECRET}" >/dev/null
