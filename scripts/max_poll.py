from __future__ import annotations

import time
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.max_auth import get_max_updates, process_max_update


def main() -> None:
    settings = get_settings()
    if not settings.max_bot_username or not settings.max_bot_token:
        raise SystemExit("MAX_BOT_USERNAME and MAX_BOT_TOKEN must be configured")

    marker: int | None = None
    print("MAX polling started. Press Ctrl+C to stop.", flush=True)
    while True:
        try:
            data = get_max_updates(settings, marker=marker)
            marker_value = data.get("marker")
            if marker_value is not None:
                marker = int(marker_value)
            updates = data.get("updates") or []
            for update in updates:
                if isinstance(update, dict):
                    result = process_max_update(settings, update)
                    if result.get("handled"):
                        print(f"MAX login confirmed: {result.get('state')}", flush=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"MAX polling error: {exc}", flush=True)
            delay = 15 if "too.many.requests" in str(exc) or "HTTP 429" in str(exc) else 3
            time.sleep(delay)


if __name__ == "__main__":
    main()
