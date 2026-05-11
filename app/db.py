"""SQLite connection management and schema bootstrap.

The dashboard keeps one SQLite file per install (``data/dashboard.sqlite`` by
default). Connections are cached on the Flask ``g`` object and closed in
``app.teardown_appcontext``. Schema is created lazily on app startup so a fresh
checkout works without a separate migration step.
"""

import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db() -> sqlite3.Connection:
    """Return the per-request SQLite connection, creating it on demand."""
    if 'db' not in g:
        db_path = Path(current_app.config['DATABASE_PATH'])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_=None) -> None:
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db() -> None:
    """Create or upgrade tables required by the dashboard."""
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            friendly_name TEXT NOT NULL,
            base_url TEXT NOT NULL,
            software_version TEXT,
            role TEXT,
            last_seen_at TEXT,
            last_status TEXT
        );

        CREATE TABLE IF NOT EXISTS device_auth (
            device_id INTEGER PRIMARY KEY,
            encrypted_automation_license_key BLOB,
            encrypted_automation_token BLOB,
            automation_token_refreshed_at TEXT,
            encrypted_web_username BLOB,
            encrypted_web_password BLOB,
            encrypted_csrf_token BLOB,
            csrf_refreshed_at TEXT,
            FOREIGN KEY(device_id) REFERENCES devices(id)
        );

        CREATE TABLE IF NOT EXISTS device_runtime_state (
            device_id INTEGER PRIMARY KEY,
            latest_screenshot_path TEXT,
            latest_screenshot_captured_at TEXT,
            latest_screenshot_error TEXT,
            screenshot_refresh_interval_minutes INTEGER NOT NULL DEFAULT 0,
            last_connection_check_at TEXT,
            last_connection_check_error TEXT,
            FOREIGN KEY(device_id) REFERENCES devices(id)
        );
        """
    )
    _ensure_column(
        db,
        table='device_runtime_state',
        column='screenshot_refresh_interval_minutes',
        column_def='INTEGER NOT NULL DEFAULT 0',
    )
    db.commit()


def list_tables() -> list[str]:
    """Return all user table names in the dashboard SQLite database."""
    rows = get_db().execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return [row['name'] for row in rows]


def _ensure_column(
    db: sqlite3.Connection,
    table: str,
    column: str,
    column_def: str,
) -> None:
    """Add ``column`` to ``table`` if it does not already exist.

    ``table``, ``column``, and ``column_def`` come from constants in this
    module, never from user input, so the f-string ``ALTER TABLE`` is safe.
    """
    existing = db.execute(f"PRAGMA table_info({table})").fetchall()
    existing_names = {row['name'] for row in existing}
    if column in existing_names:
        return
    db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
