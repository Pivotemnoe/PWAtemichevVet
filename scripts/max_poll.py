from __future__ import annotations

import time

from app.config import get_settings
from app.max_auth import get_max_updates, process_max_update


def main() -> None:
    settings = get_settings()
    if not settings.max_bot_username or not settings.max_bot_token:
        raise SystemExit("MAX_BOT_USERNAME and MAX_BOT_TOKEN must be configured")

    marker: int | None = None
    print("MAX polling started. Press Ctrl+C to stop.")
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
                        print(f"MAX login confirmed: {result.get('state')}")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"MAX polling error: {exc}")
            delay = 15 if "too.many.requests" in str(exc) or "HTTP 429" in str(exc) else 3
            time.sleep(delay)


if __name__ == "__main__":
    main()
