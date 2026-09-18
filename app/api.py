"""HTTP API blueprint for the TinyPilot Dashboard.

All routes live under the ``/api`` prefix and return JSON (except
``/api/devices/<id>/latest-screenshot`` which streams an image). Database
access goes through ``app.db.get_db``; secrets are read or written through
``app.auth_store`` so they are encrypted at rest.

Resolution parsing lives in ``app.resolution`` to keep this file focused on
request handling.
"""

from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Optional

from flask import Blueprint
from flask import current_app
from flask import jsonify
from flask import request
from flask import send_file

from app.auth_store import encrypt_secret
from app.auth_store import decrypt_secret
from app.db import get_db
from app.device_update import can_start_update
from app.device_update import update_available
from app.resolution import connected_resolution_from_web_ui
from app.resolution import resolution_from_automation_state
from app.snapshot_service import write_latest_screenshot
from app.tinypilot_client import TinyPilotClient

api_blueprint = Blueprint('api', __name__, url_prefix='/api')


@api_blueprint.get('/version')
def get_version():
    """Report the running dashboard version (useful for bug reports)."""
    return jsonify({'version': current_app.config['DASHBOARD_VERSION']})

_SQL_DEVICE_AUTH = """
    SELECT
        devices.base_url,
        device_auth.encrypted_automation_token
    FROM devices
    JOIN device_auth ON device_auth.device_id = devices.id
    WHERE devices.id = ?
"""


def _device_row(device_id: int):
    """Return device URL and encrypted API key, or None if the row is missing."""
    return get_db().execute(_SQL_DEVICE_AUTH, (device_id,)).fetchone()


def _api_key_from_auth_row(key_path: Path, auth_row) -> Optional[str]:
    """Decrypt the stored Automation API key, or None if missing."""
    if auth_row is None or auth_row['encrypted_automation_token'] is None:
        return None
    return decrypt_secret(key_path, auth_row['encrypted_automation_token'])


def _client_with_api_key(device_id: int):
    """Return (TinyPilotClient, None) or (None, (jsonify_response, status))."""
    row = _device_row(device_id)
    if row is None:
        return None, (jsonify({'error': 'device not found'}), 404)
    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    api_key = _api_key_from_auth_row(key_path, row)
    if not api_key:
        return None, (
            jsonify(
                {
                    'error': (
                        'api key not configured; add the device again with an '
                        'API key from System → Automation'
                    )
                }
            ),
            400,
        )
    return TinyPilotClient(row['base_url'], api_key=api_key), None


@api_blueprint.get('/devices')
def list_devices():
    rows = get_db().execute(
        """
        SELECT
            devices.id,
            devices.friendly_name,
            devices.base_url,
            device_runtime_state.latest_screenshot_captured_at,
            device_runtime_state.screenshot_refresh_interval_minutes,
            CASE
                WHEN device_auth.encrypted_automation_token IS NOT NULL THEN 1
                ELSE 0
            END AS api_key_configured
        FROM devices
        LEFT JOIN device_runtime_state ON device_runtime_state.device_id = devices.id
        LEFT JOIN device_auth ON device_auth.device_id = devices.id
        ORDER BY devices.id ASC
        """
    ).fetchall()
    devices = [
        {
            'id': row['id'],
            'friendly_name': row['friendly_name'],
            'base_url': row['base_url'],
            'latest_screenshot_captured_at': row['latest_screenshot_captured_at'],
            'screenshot_refresh_interval_minutes': row['screenshot_refresh_interval_minutes'] or 0,
            'api_key_configured': bool(row['api_key_configured']),
        }
        for row in rows
    ]
    return jsonify({'devices': devices})


@api_blueprint.post('/devices')
def create_device():
    payload = request.get_json(silent=True) or {}
    friendly_name = (payload.get('friendly_name') or '').strip()
    base_url = (payload.get('base_url') or '').strip()
    api_key = (payload.get('api_key') or '').strip()

    if not friendly_name or not base_url or not api_key:
        return jsonify(
            {'error': 'friendly_name, base_url, and api_key are required'}
        ), 400

    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO devices (friendly_name, base_url)
        VALUES (?, ?)
        """,
        (friendly_name, base_url),
    )
    device_id = cursor.lastrowid

    # Store the persistent Automation API key in encrypted_automation_token
    # (same Bearer secret shape as the former ephemeral token).
    db.execute(
        """
        INSERT INTO device_auth (
            device_id,
            encrypted_automation_token,
            automation_token_refreshed_at
        ) VALUES (?, ?, ?)
        """,
        (
            device_id,
            encrypt_secret(key_path, api_key),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db.execute(
        """
        INSERT INTO device_runtime_state (device_id)
        VALUES (?)
        """,
        (device_id,),
    )
    db.commit()

    return jsonify(
        {
            'device': {
                'id': device_id,
                'friendly_name': friendly_name,
                'base_url': base_url,
                'api_key_configured': True,
            }
        }
    ), 201


@api_blueprint.delete('/devices/<int:device_id>')
def delete_device(device_id: int):
    db = get_db()
    existing = db.execute(
        """
        SELECT id
        FROM devices
        WHERE id = ?
        """,
        (device_id,),
    ).fetchone()
    if existing is None:
        return jsonify({'error': 'device not found'}), 404

    db.execute(
        """
        DELETE FROM device_runtime_state
        WHERE device_id = ?
        """,
        (device_id,),
    )
    db.execute(
        """
        DELETE FROM device_auth
        WHERE device_id = ?
        """,
        (device_id,),
    )
    db.execute(
        """
        DELETE FROM devices
        WHERE id = ?
        """,
        (device_id,),
    )
    db.commit()
    return jsonify({'deleted': True, 'device_id': device_id})


@api_blueprint.post('/devices/<int:device_id>/refresh-screenshot')
def refresh_screenshot(device_id: int):
    client, err = _client_with_api_key(device_id)
    if err is not None:
        return err

    try:
        screenshot = client.get_screenshot()
    except Exception as err:  # pylint: disable=broad-exception-caught
        return jsonify({'error': f'failed to refresh screenshot: {err}'}), 502

    db = get_db()
    data_root = Path(current_app.config['DATABASE_PATH']).resolve().parent
    screenshot_path = write_latest_screenshot(data_root / 'screenshots', device_id, screenshot)
    captured_at = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        UPDATE device_runtime_state
        SET latest_screenshot_path = ?, latest_screenshot_captured_at = ?, latest_screenshot_error = NULL
        WHERE device_id = ?
        """,
        (
            str(screenshot_path),
            captured_at,
            device_id,
        ),
    )
    db.commit()
    return jsonify(
        {
            'device_id': device_id,
            'screenshot_refreshed': True,
            'screenshot_path': str(screenshot_path),
            'captured_at': captured_at,
        }
    )


@api_blueprint.post('/devices/<int:device_id>/screenshot-refresh-config')
def set_screenshot_refresh_config(device_id: int):
    payload = request.get_json(silent=True) or {}
    interval = payload.get('interval_minutes')
    if not isinstance(interval, int):
        return jsonify({'error': 'interval_minutes must be an integer'}), 400
    if interval < 0 or interval > 120:
        return jsonify({'error': 'interval_minutes must be between 0 and 120'}), 400

    db = get_db()
    existing = db.execute(
        """
        SELECT id
        FROM devices
        WHERE id = ?
        """,
        (device_id,),
    ).fetchone()
    if existing is None:
        return jsonify({'error': 'device not found'}), 404

    db.execute(
        """
        UPDATE device_runtime_state
        SET screenshot_refresh_interval_minutes = ?
        WHERE device_id = ?
        """,
        (interval, device_id),
    )
    db.commit()
    return jsonify(
        {
            'device_id': device_id,
            'screenshot_refresh_interval_minutes': interval,
        }
    )


@api_blueprint.get('/devices/<int:device_id>/latest-screenshot')
def get_latest_screenshot(device_id: int):
    row = get_db().execute(
        """
        SELECT latest_screenshot_path
        FROM device_runtime_state
        WHERE device_id = ?
        """,
        (device_id,),
    ).fetchone()
    if row is None or not row['latest_screenshot_path']:
        return jsonify({'error': 'screenshot not available'}), 404

    screenshot_path = Path(row['latest_screenshot_path']).resolve()
    screenshots_root = (
        Path(current_app.config['DATABASE_PATH']).resolve().parent / 'screenshots'
    ).resolve()
    # Defense-in-depth: the stored path is dashboard-controlled, but reject
    # anything that resolves outside the screenshots directory so a tampered
    # database row cannot expose arbitrary files via send_file.
    try:
        screenshot_path.relative_to(screenshots_root)
    except ValueError:
        return jsonify({'error': 'screenshot path is outside data directory'}), 404
    if not screenshot_path.is_file():
        return jsonify({'error': 'screenshot file missing'}), 404
    return send_file(screenshot_path, mimetype='image/jpeg')


def _safe_fetch(fetcher):
    try:
        return fetcher(), None
    except Exception as err:  # pylint: disable=broad-exception-caught
        return None, str(err)


@api_blueprint.get('/devices/<int:device_id>/device/snapshot')
def get_device_snapshot(device_id: int):
    row = get_db().execute(
        """
        SELECT
            devices.id,
            devices.friendly_name,
            devices.base_url,
            device_auth.encrypted_automation_token
        FROM devices
        LEFT JOIN device_auth ON device_auth.device_id = devices.id
        WHERE devices.id = ?
        """,
        (device_id,),
    ).fetchone()
    if row is None:
        return jsonify({'error': 'device not found'}), 404

    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    api_key = _api_key_from_auth_row(key_path, row)
    if not api_key:
        return jsonify(
            {
                'error': (
                    'api key not configured; add the device again with an '
                    'API key from System → Automation'
                )
            }
        ), 400

    client = TinyPilotClient(row['base_url'], api_key=api_key)

    # API-key allowlist (Pro 3.2.0+): version, network, video, /state, screenshot,
    # latestRelease, update status/start.
    status, status_error = _safe_fetch(client.get_status)
    version, version_error = _safe_fetch(client.get_version)
    network, network_error = _safe_fetch(client.get_network_status)
    video, video_error = _safe_fetch(client.get_video_settings)
    automation_state, automation_state_error = _safe_fetch(client.get_automation_state)
    latest_release, latest_release_error = _safe_fetch(client.get_latest_release)
    update_job, update_job_error = _safe_fetch(client.get_update_status)

    last_error = (
        status_error
        or version_error
        or network_error
        or video_error
        or automation_state_error
    )

    online = any(
        error is None
        for error in (
            status_error,
            version_error,
            network_error,
            video_error,
            automation_state_error,
        )
    )

    connected_resolution = (
        resolution_from_automation_state(automation_state)
        or connected_resolution_from_web_ui(video, status)
    )

    current_version = (version or {}).get('version')
    latest_version = (latest_release or {}).get('version')
    license_check_status = (latest_release or {}).get('licenseCheckStatus')

    collapsed = {
        'friendly_name': row['friendly_name'],
        'device_url': row['base_url'],
        'online': online,
        'software_version': current_version or 'unknown',
        'last_checked': datetime.now(timezone.utc).isoformat(),
        'api_key_status': 'configured',
    }

    expanded = {
        'reachability': {'status': status, 'error': status_error},
        'version': {'status': version, 'error': version_error},
        'network': {'data': network or {}, 'error': network_error},
        'video_settings': {'status': video, 'error': video_error},
        'automation_state': {'status': automation_state, 'error': automation_state_error},
        'connected_device_resolution': connected_resolution,
        'last_management_error': last_error,
        'software_update': {
            'latest': latest_release,
            'latest_error': latest_release_error,
            'job': update_job,
            'job_error': update_job_error,
            'update_available': update_available(current_version, latest_version),
            'can_start': can_start_update(
                current_version, latest_version, license_check_status
            ),
        },
    }

    return jsonify(
        {
            'device_id': row['id'],
            'source_base_url': row['base_url'],
            'collapsed': collapsed,
            'expanded': expanded,
        }
    )


@api_blueprint.get('/devices/<int:device_id>/device/update')
def get_device_update_status(device_id: int):
    client, err = _client_with_api_key(device_id)
    if err is not None:
        return err
    try:
        result = client.get_update_status()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return jsonify({'error': f'failed to fetch update status: {exc}'}), 502
    return jsonify(result)


@api_blueprint.put('/devices/<int:device_id>/device/update')
def start_device_update(device_id: int):
    client, err = _client_with_api_key(device_id)
    if err is not None:
        return err
    payload = request.get_json(silent=True) or {}
    version = (payload.get('version') or '').strip()
    if not version:
        return jsonify({'error': 'version is required'}), 400
    try:
        client.start_update(version)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return jsonify({'error': f'failed to start update: {exc}'}), 502
    return jsonify({'device_id': device_id, 'update_started': True, 'version': version})
