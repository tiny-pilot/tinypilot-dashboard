"""Load a TinyPilotClient for a dashboard device row."""

from pathlib import Path
from typing import Optional

from flask import current_app

from app.auth_store import decrypt_secret
from app.db import get_db
from app.tinypilot_client import TinyPilotClient

_SQL_DEVICE_AUTH = """
    SELECT
        devices.base_url,
        device_auth.encrypted_automation_token
    FROM devices
    JOIN device_auth ON device_auth.device_id = devices.id
    WHERE devices.id = ?
"""


def device_auth_row(device_id: int):
    """Return device URL and encrypted API key, or None if the row is missing."""
    return get_db().execute(_SQL_DEVICE_AUTH, (device_id,)).fetchone()


def api_key_from_auth_row(key_path: Path, auth_row) -> Optional[str]:
    """Decrypt the stored Automation API key, or None if missing."""
    if auth_row is None or auth_row['encrypted_automation_token'] is None:
        return None
    return decrypt_secret(key_path, auth_row['encrypted_automation_token'])


def tinypilot_client_for_device(device_id: int) -> Optional[TinyPilotClient]:
    """Return a client when the device exists and has an API key configured."""
    row = device_auth_row(device_id)
    if row is None:
        return None
    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    api_key = api_key_from_auth_row(key_path, row)
    if not api_key:
        return None
    return TinyPilotClient(row['base_url'], api_key=api_key)
