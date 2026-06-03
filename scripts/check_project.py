from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


REQUIRED_FILES = (
    "README.md",
    ".env.example",
    "requirements.txt",
    "app/main.py",
    "app/db.py",
    "web/index.html",
    "web/styles.css",
    "web/app.js",
    "web/manifest.webmanifest",
    "web/sw.js",
    "web/assets/icon.svg",
)


def main() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {', '.join(missing)}")

    manifest = (ROOT / "web/manifest.webmanifest").read_text(encoding="utf-8")
    if "TemichevVet" not in manifest:
        raise SystemExit("manifest does not contain app name")

    js = (ROOT / "web/app.js").read_text(encoding="utf-8")
    for endpoint in ("/api/auth/email/start", "/api/auth/email/verify", "/api/auth/${provider}/start"):
        if endpoint not in js:
            raise SystemExit(f"frontend does not reference {endpoint}")

    print("pwa project check ok")


if __name__ == "__main__":
    main()
