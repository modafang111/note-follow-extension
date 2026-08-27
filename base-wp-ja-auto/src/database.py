"""SQLite による処理履歴と翻訳キャッシュ。削除APIは持たない。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from config import settings

JOB_COLUMNS = [
    "id",
    "plugin_slug",
    "plugin_name",
    "plugin_version",
    "wordpress_url",
    "download_url",
    "translation_date",
    "output_zip",
    "base_product_id",
    "base_product_url",
    "status",
    "stage",
    "is_update",
    "created_at",
    "updated_at",
    "error_message",
    "work_dir",
    "log_path",
]


def _connect(path: Path | None = None) -> sqlite3.Connection:
    settings.ensure_directories()
    db_path = path or settings.db_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_slug TEXT NOT NULL,
                plugin_name TEXT,
                plugin_version TEXT NOT NULL,
                wordpress_url TEXT,
                download_url TEXT,
                translation_date TEXT,
                output_zip TEXT,
                base_product_id TEXT,
                base_product_url TEXT,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                is_update INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error_message TEXT,
                work_dir TEXT,
                log_path TEXT,
                UNIQUE(plugin_slug, plugin_version)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS translation_cache (
                cache_key TEXT PRIMARY KEY,
                msgid TEXT NOT NULL,
                msgctxt TEXT,
                msgstr TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def get_job(slug: str, version: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE plugin_slug = ? AND plugin_version = ?",
            (slug, version),
        ).fetchone()
        return dict(row) if row else None


def latest_job_for_slug(slug: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM jobs
            WHERE plugin_slug = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (slug,),
        ).fetchone()
        return dict(row) if row else None


def upsert_job(slug: str, version: str, **fields: Any) -> dict[str, Any]:
    now = _now()
    existing = get_job(slug, version)
    payload = {k: v for k, v in fields.items() if k in JOB_COLUMNS and k != "id"}
    with get_conn() as conn:
        if existing is None:
            payload.setdefault("plugin_slug", slug)
            payload.setdefault("plugin_version", version)
            payload.setdefault("status", "started")
            payload.setdefault("stage", "started")
            payload.setdefault("created_at", now)
            payload["updated_at"] = now
            columns = ", ".join(payload.keys())
            placeholders = ", ".join(["?"] * len(payload))
            conn.execute(
                f"INSERT INTO jobs ({columns}) VALUES ({placeholders})",
                list(payload.values()),
            )
        else:
            payload["updated_at"] = now
            assignments = ", ".join(f"{k} = ?" for k in payload)
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE plugin_slug = ? AND plugin_version = ?",
                [*payload.values(), slug, version],
            )
    job = get_job(slug, version)
    assert job is not None
    return job


def mark_error(slug: str, version: str, stage: str, message: str) -> None:
    upsert_job(
        slug,
        version,
        status="error",
        stage=stage,
        error_message=message[:4000],
    )


def cache_get(cache_key: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT msgstr FROM translation_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        return row["msgstr"] if row else None


def cache_put(
    cache_key: str,
    msgid: str,
    msgstr: str,
    *,
    msgctxt: str = "",
    provider: str = "",
    model: str = "",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO translation_cache
            (cache_key, msgid, msgctxt, msgstr, provider, model, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cache_key, msgid, msgctxt, msgstr, provider, model, _now()),
        )


def successfully_registered(slug: str, version: str) -> bool:
    job = get_job(slug, version)
    if not job:
        return False
    return job["status"] in {"completed", "base_registered"} and bool(job.get("base_product_id"))
