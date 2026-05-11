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
from app.resolution import connected_resolution_from_web_ui
from app.resolution import resolution_from_automation_state
from app.snapshot_service import write_latest_screenshot
from app.tinypilot_client import TinyPilotClient

api_blueprint = Blueprint('api', __name__, url_prefix='/api')


@api_blueprint.get('/version')
def get_version():
    """Report the running dashboard version (useful for bug reports)."""
    return jsonify({'version': current_app.config['DASHBOARD_VERSION']})

_SQL_DEVICE_INNER_AUTH = """
    SELECT
        devices.base_url,
        device_auth.encrypted_web_username,
        device_auth.encrypted_web_password
    FROM devices
    JOIN device_auth ON device_auth.device_id = devices.id
    WHERE devices.id = ?
"""


def _device_row_with_web_auth(device_id: int):
    """Return device URL and encrypted Web UI auth fields, or None if the row is missing."""
    return get_db().execute(_SQL_DEVICE_INNER_AUTH, (device_id,)).fetchone()


def _persist_automation_token(db, key_path: Path, device_id: int, token: str) -> None:
    db.execute(
        """
        UPDATE device_auth
        SET encrypted_automation_token = ?, automation_token_refreshed_at = ?
        WHERE device_id = ?
        """,
        (
            encrypt_secret(key_path, token),
            datetime.now(timezone.utc).isoformat(),
            device_id,
        ),
    )


def _http_basic_from_auth_row(key_path: Path, auth_row) -> Optional[tuple[str, str]]:
    """Decode stored Web UI HTTP Basic credentials, or None if none are configured."""
    if auth_row is None:
        return None
    if (
        auth_row['encrypted_web_username'] is None
        and auth_row['encrypted_web_password'] is None
    ):
        return None
    username = ''
    password = ''
    if auth_row['encrypted_web_username'] is not None:
        username = decrypt_secret(key_path, auth_row['encrypted_web_username'])
    if auth_row['encrypted_web_password'] is not None:
        password = decrypt_secret(key_path, auth_row['encrypted_web_password'])
    return (username, password)


def _attempt_automation_token_refresh(db, device_id: int, base_url: str):
    """
    Fetch and store an Automation API token. TinyPilot expects the Automation
    license to be activated on the device; POST /api/v1/auth typically needs no
    body. We always try once on create so devices with Automation already enabled
    get a token even when the dashboard does not store a license key.
    """
    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    auth_row = db.execute(
        """
        SELECT encrypted_web_username, encrypted_web_password
        FROM device_auth
        WHERE device_id = ?
        """,
        (device_id,),
    ).fetchone()
    http_basic = _http_basic_from_auth_row(key_path, auth_row)
    client = TinyPilotClient(base_url, http_basic=http_basic)
    try:
        automation_token = client.refresh_automation_token()
    except Exception as err:  # pylint: disable=broad-exception-caught
        return False, str(err)
    _persist_automation_token(db, key_path, device_id, automation_token)
    return True, None


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
            END AS automation_token_configured
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
            'automation_token_configured': bool(row['automation_token_configured']),
        }
        for row in rows
    ]
    return jsonify({'devices': devices})


@api_blueprint.post('/devices')
def create_device():
    payload = request.get_json(silent=True) or {}
    friendly_name = (payload.get('friendly_name') or '').strip()
    base_url = (payload.get('base_url') or '').strip()

    if not friendly_name or not base_url:
        return jsonify({'error': 'friendly_name and base_url are required'}), 400

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

    encrypted_automation_license_key = None
    if payload.get('automation_license_key'):
        encrypted_automation_license_key = encrypt_secret(
            key_path,
            payload['automation_license_key'],
        )

    encrypted_web_username = None
    if payload.get('web_username'):
        encrypted_web_username = encrypt_secret(key_path, payload['web_username'])

    encrypted_web_password = None
    if payload.get('web_password'):
        encrypted_web_password = encrypt_secret(key_path, payload['web_password'])

    db.execute(
        """
        INSERT INTO device_auth (
            device_id,
            encrypted_automation_license_key,
            encrypted_web_username,
            encrypted_web_password
        ) VALUES (?, ?, ?, ?)
        """,
        (
            device_id,
            encrypted_automation_license_key,
            encrypted_web_username,
            encrypted_web_password,
        ),
    )
    db.execute(
        """
        INSERT INTO device_runtime_state (device_id)
        VALUES (?)
        """,
        (device_id,),
    )

    automation_token_refreshed, automation_error = _attempt_automation_token_refresh(
        db=db,
        device_id=device_id,
        base_url=base_url,
    )
    db.commit()

    return jsonify(
        {
            'device': {
                'id': device_id,
                'friendly_name': friendly_name,
                'base_url': base_url,
                'automation_token_refreshed': automation_token_refreshed,
                'automation_error': automation_error,
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


@api_blueprint.post('/devices/<int:device_id>/automation/refresh-token')
def refresh_automation_token(device_id: int):
    row = _device_row_with_web_auth(device_id)
    if row is None:
        return jsonify({'error': 'device not found'}), 404
    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    http_basic = _http_basic_from_auth_row(key_path, row)
    client = TinyPilotClient(row['base_url'], http_basic=http_basic)
    try:
        automation_token = client.refresh_automation_token()
    except Exception as err:  # pylint: disable=broad-exception-caught
        return jsonify({'error': f'failed to refresh automation token: {err}'}), 502

    db = get_db()
    _persist_automation_token(db, key_path, device_id, automation_token)
    db.commit()
    return jsonify({'device_id': device_id, 'automation_token_refreshed': True})


@api_blueprint.post('/devices/<int:device_id>/refresh-screenshot')
def refresh_screenshot(device_id: int):
    row = _device_row_with_web_auth(device_id)
    if row is None:
        return jsonify({'error': 'device not found'}), 404

    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    http_basic = _http_basic_from_auth_row(key_path, row)
    client = TinyPilotClient(row['base_url'], http_basic=http_basic)
    db = get_db()

    try:
        fresh_token = client.refresh_automation_token()
    except Exception as err:  # pylint: disable=broad-exception-caught
        return jsonify({'error': f'failed to refresh automation token: {err}'}), 502

    _persist_automation_token(db, key_path, device_id, fresh_token)
    db.commit()

    screenshot = None
    try:
        screenshot = client.get_screenshot(fresh_token)
    except Exception as err:  # pylint: disable=broad-exception-caught
        if '401' not in str(err):
            return jsonify({'error': f'failed to refresh screenshot: {err}'}), 502
        try:
            fresh_token = client.refresh_automation_token()
            _persist_automation_token(db, key_path, device_id, fresh_token)
            db.commit()
            screenshot = client.get_screenshot(fresh_token)
        except Exception as retry_err:  # pylint: disable=broad-exception-caught
            return jsonify(
                {'error': f'failed to refresh screenshot after token retry: {retry_err}'}
            ), 502

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


@api_blueprint.post('/devices/<int:device_id>/device/refresh-csrf')
def refresh_csrf_token(device_id: int):
    row = _device_row_with_web_auth(device_id)
    if row is None:
        return jsonify({'error': 'device not found'}), 404

    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    http_basic = _http_basic_from_auth_row(key_path, row)
    client = TinyPilotClient(row['base_url'], http_basic=http_basic)
    try:
        csrf_token = client.refresh_csrf_token()
    except Exception as err:  # pylint: disable=broad-exception-caught
        return jsonify({'error': f'failed to refresh csrf token: {err}'}), 502

    encrypted_csrf_token = encrypt_secret(key_path, csrf_token)
    db = get_db()
    db.execute(
        """
        UPDATE device_auth
        SET encrypted_csrf_token = ?
        WHERE device_id = ?
        """,
        (encrypted_csrf_token, device_id),
    )
    db.commit()
    return jsonify({'device_id': device_id, 'csrf_refreshed': True})


@api_blueprint.get('/devices/<int:device_id>/device/metrics')
def get_device_metrics(device_id: int):
    row = _device_row_with_web_auth(device_id)
    if row is None:
        return jsonify({'error': 'device not found'}), 404

    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    http_basic = _http_basic_from_auth_row(key_path, row)
    client = TinyPilotClient(row['base_url'], http_basic=http_basic)
    try:
        client.refresh_csrf_token()
        metrics = client.get_network_status()
    except Exception as err:  # pylint: disable=broad-exception-caught
        return jsonify({'error': f'failed to fetch device metrics: {err}'}), 502
    return jsonify(
        {
            'device_id': device_id,
            'source_base_url': row['base_url'],
            'metrics': metrics,
        }
    )


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
            device_auth.encrypted_automation_token,
            device_auth.encrypted_web_username,
            device_auth.encrypted_web_password
        FROM devices
        LEFT JOIN device_auth ON device_auth.device_id = devices.id
        WHERE devices.id = ?
        """,
        (device_id,),
    ).fetchone()
    if row is None:
        return jsonify({'error': 'device not found'}), 404

    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    http_basic = _http_basic_from_auth_row(key_path, row)
    client = TinyPilotClient(row['base_url'], http_basic=http_basic)

    automation_token_plain = None
    automation_token_error = None
    db = get_db()
    try:
        automation_token_plain = client.refresh_automation_token()
        _persist_automation_token(db, key_path, row['id'], automation_token_plain)
        db.commit()
    except Exception as err:  # pylint: disable=broad-exception-caught
        automation_token_error = str(err)

    status, status_error = _safe_fetch(client.get_status)
    auth_status, auth_error = _safe_fetch(client.get_auth_status)
    version, version_error = _safe_fetch(client.get_version)
    network, network_error = _safe_fetch(client.get_network_status)
    requires_https, https_error = _safe_fetch(client.get_requires_https)
    video, video_error = _safe_fetch(client.get_video_settings)

    # Unofficial `GET /state` uses the same Automation bearer; refresh token above
    # so resolution tracks the latest session.
    automation_state = None
    automation_state_error = automation_token_error
    if automation_token_plain:
        automation_state, automation_state_error = _safe_fetch(
            lambda token=automation_token_plain: client.get_automation_state(token)
        )

    last_error = (
        status_error
        or auth_error
        or version_error
        or network_error
        or https_error
        or video_error
        or automation_state_error
    )

    online = any(
        error is None
        for error in (
            status_error,
            auth_error,
            version_error,
            network_error,
            https_error,
            video_error,
        )
    )

    connected_resolution = (
        resolution_from_automation_state(automation_state)
        or connected_resolution_from_web_ui(video, status)
    )

    collapsed = {
        'friendly_name': row['friendly_name'],
        'device_url': row['base_url'],
        'online': online,
        'software_version': (version or {}).get('version', 'unknown'),
        'web_session_status': 'connected' if auth_status and not auth_error else 'unknown',
        'management_role': (auth_status or {}).get('role') or 'unknown',
        'last_checked': datetime.now(timezone.utc).isoformat(),
        'csrf_status': 'unknown',
        'automation_api_status': 'configured' if automation_token_plain else 'not_configured',
    }

    expanded = {
        'reachability': {'status': status, 'error': status_error},
        'web_session': {'status': auth_status, 'error': auth_error},
        'version': {'status': version, 'error': version_error},
        'network': {'interfaces': (network or {}).get('interfaces', []), 'error': network_error},
        'https_requirement': {'status': requires_https, 'error': https_error},
        'video_settings': {'status': video, 'error': video_error},
        'connected_device_resolution': connected_resolution,
        'last_management_error': last_error,
    }

    return jsonify(
        {
            'device_id': row['id'],
            'source_base_url': row['base_url'],
            'collapsed': collapsed,
            'expanded': expanded,
        }
    )
