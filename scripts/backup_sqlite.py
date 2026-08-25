from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(os.getenv("TEMICHEVVET_ROOT", "/opt/temichevvet"))
PWA_DIR = ROOT / "pwa"
DATA_DIR = ROOT / "data"
BACKUP_DIR = ROOT / "backups"
S3_ENV = ROOT / "s3.env"
KEEP_DAYS = 14


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def active_pwa_database() -> Path:
    env = load_env(PWA_DIR / ".env")
    configured = env.get("DATABASE_PATH", "./pwa.db").strip()
    path = Path(configured)
    if not path.is_absolute():
        path = PWA_DIR / path
    return path.resolve()


def database_sources() -> list[tuple[str, Path]]:
    sources = [("pwa", active_pwa_database()), ("bot", DATA_DIR / "bot.db")]
    unique: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for label, path in sources:
        resolved = path.resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        unique.append((label, resolved))
    return unique


def backup_db(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    with sqlite3.connect(target) as check:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"integrity_check failed for {target}: {result}")
    gz_target = target.with_suffix(target.suffix + ".gz")
    with target.open("rb") as raw, gzip.open(gz_target, "wb", compresslevel=6) as gz:
        shutil.copyfileobj(raw, gz)
    target.unlink()
    return gz_target


def upload_to_s3(files: list[Path], stamp: str) -> list[str]:
    env = load_env(S3_ENV)
    if not env:
        return []
    required = ["S3_ENDPOINT", "S3_REGION", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"]
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise RuntimeError("missing S3 env keys: " + ", ".join(missing))

    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=env["S3_ENDPOINT"].rstrip("/"),
        region_name=env["S3_REGION"],
        aws_access_key_id=env["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=env["S3_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
    )
    prefix = env.get("S3_BACKUP_PREFIX", "temichevvet/backups").strip("/")
    uploaded: list[str] = []
    for file_path in files:
        key = f"{prefix}/{stamp}/{file_path.name}"
        client.upload_file(
            str(file_path),
            env["S3_BUCKET"],
            key,
            ExtraArgs={"ContentType": "application/gzip"},
        )
        uploaded.append(key)
    return uploaded


def cleanup() -> None:
    cutoff = datetime.now(timezone.utc).timestamp() - KEEP_DAYS * 86400
    for path in BACKUP_DIR.glob("*.db.gz"):
        if path.stat().st_mtime < cutoff:
            path.unlink()


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    files = [
        backup_db(source, BACKUP_DIR / f"{label}_{stamp}.db")
        for label, source in database_sources()
    ]
    uploaded = upload_to_s3(files, stamp)
    cleanup()
    print(f"backup ok: {stamp}; local_files={len(files)}; s3_uploaded={len(uploaded)}")


if __name__ == "__main__":
    main()
