"""Schema cleanup: drop unused columns and clear leftover screenshot files."""

import sqlite3
from pathlib import Path

from app import create_app
from app.db import get_db
from app.db import init_db

DROPPED = {
    'devices': {'last_seen_at', 'last_status', 'role'},
    'device_auth': {
        'encrypted_automation_license_key',
        'encrypted_web_username',
        'encrypted_web_password',
        'encrypted_csrf_token',
        'csrf_refreshed_at',
    },
    'device_runtime_state': {
        'latest_screenshot_path',
        'latest_screenshot_captured_at',
        'latest_screenshot_error',
        'last_connection_check_at',
        'last_connection_check_error',
    },
}


def _columns(db, table):
    return {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}


def test_init_db_drops_legacy_columns_and_is_idempotent(tmp_path):
    db_path = tmp_path / 'dashboard.sqlite'
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE devices (
            id INTEGER PRIMARY KEY,
            friendly_name TEXT NOT NULL,
            base_url TEXT NOT NULL,
            software_version TEXT,
            role TEXT,
            last_seen_at TEXT,
            last_status TEXT
        );
        CREATE TABLE device_auth (
            device_id INTEGER PRIMARY KEY,
            encrypted_automation_license_key BLOB,
            encrypted_automation_token BLOB,
            automation_token_refreshed_at TEXT,
            encrypted_web_username BLOB,
            encrypted_web_password BLOB,
            encrypted_csrf_token BLOB,
            csrf_refreshed_at TEXT
        );
        CREATE TABLE device_runtime_state (
            device_id INTEGER PRIMARY KEY,
            latest_screenshot_path TEXT,
            latest_screenshot_captured_at TEXT,
            latest_screenshot_error TEXT,
            screenshot_refresh_interval_minutes INTEGER NOT NULL DEFAULT 0,
            last_connection_check_at TEXT,
            last_connection_check_error TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    shots = tmp_path / 'screenshots'
    shots.mkdir()
    (shots / 'device-1-latest.jpg').write_bytes(b'x')
    (shots / 'device-1-latest.jpg.enc').write_bytes(b'y')

    app = create_app({
        'TESTING': True,
        'DATABASE_PATH': str(db_path),
        'SECRET_KEY_PATH': str(tmp_path / 'secret.key'),
    })
    with app.app_context():
        for table, cols in DROPPED.items():
            assert cols.isdisjoint(_columns(get_db(), table))
        init_db()
        for table, cols in DROPPED.items():
            assert cols.isdisjoint(_columns(get_db(), table))
    assert list(shots.glob('*')) == []


def test_fresh_schema_omits_dropped_columns(tmp_path):
    db_path = tmp_path / 'dashboard.sqlite'
    app = create_app({
        'TESTING': True,
        'DATABASE_PATH': str(db_path),
        'SECRET_KEY_PATH': str(tmp_path / 'secret.key'),
    })
    with app.app_context():
        for table, cols in DROPPED.items():
            assert cols.isdisjoint(_columns(get_db(), table))
        assert 'screenshot_refresh_interval_minutes' in _columns(
            get_db(), 'device_runtime_state'
        )
        assert 'encrypted_automation_token' in _columns(get_db(), 'device_auth')
