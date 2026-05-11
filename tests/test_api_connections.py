from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.auth_store import encrypt_secret
from app.resolution import resolution_from_automation_state


def test_schema_bootstrap_creates_tables(tmp_path):
    db_path = tmp_path / "dashboard.sqlite"
    app = create_app({"DATABASE_PATH": str(db_path)})

    with app.app_context():
        from app.db import list_tables
        tables = set(list_tables())

    assert {"devices", "device_auth", "device_runtime_state"} <= tables


def test_list_devices_endpoint(client):
    response = client.get('/api/devices')
    assert response.status_code == 200
    assert response.json == {'devices': []}


def test_create_device_persists_and_lists_device(client):
    payload = {
        'friendly_name': 'Office Rack KVM',
        'base_url': 'https://192.168.1.44',
        'automation_license_key': 'license-123',
    }
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.refresh_automation_token.return_value = 'token-from-license'
        create_response = client.post('/api/devices', json=payload)
    assert create_response.status_code == 201
    client_cls.assert_called()
    _args, kwargs = client_cls.call_args
    assert kwargs.get('http_basic') is None
    created = create_response.json['device']
    assert created['friendly_name'] == payload['friendly_name']
    assert created['base_url'] == payload['base_url']

    list_response = client.get('/api/devices')
    assert list_response.status_code == 200
    assert len(list_response.json['devices']) == 1
    listed = list_response.json['devices'][0]
    assert listed['friendly_name'] == payload['friendly_name']
    assert listed['automation_token_configured'] is True


def test_create_device_fetches_token_without_license_payload_when_tinypilot_succeeds(client):
    payload = {'friendly_name': 'Bare URL', 'base_url': 'https://192.168.1.71'}
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.refresh_automation_token.return_value = 'from-device'
        response = client.post('/api/devices', json=payload)
    assert response.status_code == 201
    assert response.json['device']['automation_token_refreshed'] is True
    listed = client.get('/api/devices').json['devices'][0]
    assert listed['automation_token_configured'] is True


def test_resolution_from_automation_state_accepts_string_dimensions():
    state = {'result': {'source': {'resolution': {'width': '1920', 'height': '1080'}}}}
    assert resolution_from_automation_state(state) == '1920x1080'


def test_resolution_from_automation_state_accepts_pair_list():
    state = {'result': {'source': {'resolution': [3840, 2160]}}}
    assert resolution_from_automation_state(state) == '3840x2160'


def test_resolution_from_automation_state_accepts_dimension_string():
    state = {'result': {'resolution': '1280x720'}}
    assert resolution_from_automation_state(state) == '1280x720'


def test_create_device_attempts_automation_token_refresh_when_license_present(client):
    payload = {
        'friendly_name': 'Licensed Device',
        'base_url': 'https://192.168.1.88',
        'automation_license_key': 'license-xyz',
    }
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.refresh_automation_token.return_value = 'token-xyz'
        response = client.post('/api/devices', json=payload)

    assert response.status_code == 201
    assert response.json['device']['automation_token_refreshed'] is True


def test_delete_device_removes_device_and_related_rows(client):
    payload = {
        'friendly_name': 'Delete Me',
        'base_url': 'https://192.168.1.99',
    }
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.refresh_automation_token.side_effect = RuntimeError('no TinyPilot in tests')
        create_response = client.post('/api/devices', json=payload)
    device_id = create_response.json['device']['id']
    list_before = client.get('/api/devices')
    assert list_before.json['devices'][0]['automation_token_configured'] is False

    delete_response = client.delete(f'/api/devices/{device_id}')
    assert delete_response.status_code == 200
    assert delete_response.json['deleted'] is True

    list_response = client.get('/api/devices')
    assert list_response.status_code == 200
    assert all(device['id'] != device_id for device in list_response.json['devices'])


def test_refresh_automation_endpoint(client):
    create_payload = {
        'friendly_name': 'Token Device',
        'base_url': 'https://192.168.1.50',
    }
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.refresh_automation_token.side_effect = [
            RuntimeError('no TinyPilot on create'),
            'token-xyz',
        ]
        create_response = client.post('/api/devices', json=create_payload)
        device_id = create_response.json['device']['id']
        response = client.post(f'/api/devices/{device_id}/automation/refresh-token')

    assert response.status_code == 200
    assert response.json['automation_token_refreshed'] is True

    list_response = client.get('/api/devices')
    listed = next(d for d in list_response.json['devices'] if d['id'] == device_id)
    assert listed['automation_token_configured'] is True


def test_refresh_screenshot_endpoint(client):
    create_payload = {
        'friendly_name': 'Screenshot Device',
        'base_url': 'https://192.168.1.51',
    }
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.refresh_automation_token.side_effect = RuntimeError('no TinyPilot in tests')
        create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    with patch('app.api.TinyPilotClient') as client_cls:
        inst = client_cls.return_value
        inst.refresh_automation_token.return_value = 'token-xyz'
        inst.get_screenshot.return_value = b'jpeg-bytes'
        response = client.post(f'/api/devices/{device_id}/refresh-screenshot')

    assert response.status_code == 200
    assert response.json['screenshot_refreshed'] is True
    assert response.json['screenshot_path'].endswith(f'device-{device_id}-latest.jpg')

    screenshot_response = client.get(f'/api/devices/{device_id}/latest-screenshot')
    assert screenshot_response.status_code == 200
    assert screenshot_response.data == b'jpeg-bytes'


def test_set_screenshot_refresh_interval_endpoint(client):
    create_payload = {
        'friendly_name': 'Interval Device',
        'base_url': 'https://192.168.1.77',
    }
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.refresh_automation_token.side_effect = RuntimeError('no TinyPilot in tests')
        create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    response = client.post(
        f'/api/devices/{device_id}/screenshot-refresh-config',
        json={'interval_minutes': 5},
    )
    assert response.status_code == 200
    assert response.json['screenshot_refresh_interval_minutes'] == 5

    list_response = client.get('/api/devices')
    device = next(row for row in list_response.json['devices'] if row['id'] == device_id)
    assert device['screenshot_refresh_interval_minutes'] == 5


def test_refresh_csrf_endpoint(client):
    response = client.post('/api/devices/1/device/refresh-csrf')
    assert response.status_code in (200, 404)


def test_index_page_loads(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'TinyPilot Dashboard' in response.data
    assert b'<dashboard-app' in response.data
    assert b'dashboard-app.js' in response.data


def test_refresh_csrf_and_device_metrics_endpoint(client):
    create_payload = {
        'friendly_name': 'Office Rack KVM',
        'base_url': 'https://192.168.1.44',
    }
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.refresh_automation_token.side_effect = RuntimeError('no TinyPilot in tests')
        create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    with patch('app.api.TinyPilotClient') as client_cls:
        tp_client = client_cls.return_value
        tp_client.refresh_csrf_token.return_value = 'csrf-abc'
        tp_client.get_network_status.return_value = {'interfaces': [{'name': 'eth0'}]}

        csrf_response = client.post(f'/api/devices/{device_id}/device/refresh-csrf')
        assert csrf_response.status_code == 200
        assert csrf_response.json['csrf_refreshed'] is True

        metrics_response = client.get(f'/api/devices/{device_id}/device/metrics')
        assert metrics_response.status_code == 200
        assert metrics_response.json['metrics'] == {'interfaces': [{'name': 'eth0'}]}
        assert metrics_response.json['source_base_url'] == create_payload['base_url']


def test_device_snapshot_endpoint_returns_collapsed_and_expanded_sections(client):
    create_payload = {
        'friendly_name': 'Office Rack KVM',
        'base_url': 'https://192.168.1.44',
    }
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.refresh_automation_token.side_effect = RuntimeError('no TinyPilot in tests')
        create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    with patch('app.api.TinyPilotClient') as client_cls:
        tp_client = client_cls.return_value
        tp_client.refresh_automation_token.return_value = 'tok'
        tp_client.get_status.return_value = {'ok': True}
        tp_client.get_auth_status.return_value = {'isAuthenticated': True, 'username': 'admin'}
        tp_client.get_version.return_value = {'version': '2.6.5'}
        tp_client.get_network_status.return_value = {
            'interfaces': [{'name': 'eth0', 'isConnected': True, 'ipAddress': '192.168.1.44'}]
        }
        tp_client.get_requires_https.return_value = {'requiresHttps': True}
        tp_client.get_video_settings.return_value = {'h264Bitrate': 8000, 'streamingMode': 'MJPEG'}
        tp_client.get_status.return_value = {
            'ok': True,
            'video': {'connectedDeviceResolution': '1920x1080'},
        }

        snapshot_response = client.get(f'/api/devices/{device_id}/device/snapshot')

    assert snapshot_response.status_code == 200
    payload = snapshot_response.json
    assert payload['source_base_url'] == create_payload['base_url']
    assert payload['collapsed']['software_version'] == '2.6.5'
    assert payload['collapsed']['web_session_status'] == 'connected'
    assert 'connected_device_resolution' not in payload['collapsed']
    assert payload['expanded']['network']['interfaces'][0]['name'] == 'eth0'
    assert payload['expanded']['connected_device_resolution'] == '1920x1080'


def test_device_snapshot_prefers_automation_state_resolution(client):
    create_payload = {
        'friendly_name': 'State Resolution',
        'base_url': 'https://192.168.1.55',
    }
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.refresh_automation_token.side_effect = RuntimeError('no TinyPilot in tests')
        create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    with client.application.app_context():
        key_path = Path(client.application.config['SECRET_KEY_PATH'])
        encrypted_token = encrypt_secret(key_path, 'token-abc')
        from app.db import get_db
        db = get_db()
        db.execute(
            """
            UPDATE device_auth
            SET encrypted_automation_token = ?
            WHERE device_id = ?
            """,
            (encrypted_token, device_id),
        )
        db.commit()

    with patch('app.api.TinyPilotClient') as client_cls:
        tp_client = client_cls.return_value
        tp_client.refresh_automation_token.return_value = 'tok'
        tp_client.get_status.return_value = {'ok': True}
        tp_client.get_auth_status.return_value = {}
        tp_client.get_version.return_value = {'version': '3.0.2'}
        tp_client.get_network_status.return_value = {'interfaces': []}
        tp_client.get_requires_https.return_value = {'requiresHttps': False}
        tp_client.get_video_settings.return_value = {'h264Bitrate': 900}
        tp_client.get_automation_state.return_value = {
            'result': {'source': {'resolution': {'width': 2560, 'height': 1440}}},
        }

        snapshot_response = client.get(f'/api/devices/{device_id}/device/snapshot')

    assert snapshot_response.status_code == 200
    assert 'connected_device_resolution' not in snapshot_response.json['collapsed']
    assert snapshot_response.json['expanded']['connected_device_resolution'] == '2560x1440'
    tp_client.get_automation_state.assert_called_once()


def test_latest_screenshot_rejects_paths_outside_screenshots_dir(client, tmp_path):
    create_payload = {
        'friendly_name': 'Path Test',
        'base_url': 'https://192.168.1.80',
    }
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.refresh_automation_token.side_effect = RuntimeError(
            'no TinyPilot in tests'
        )
        create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    rogue_path = tmp_path / 'rogue.jpg'
    rogue_path.write_bytes(b'should-not-be-served')

    with client.application.app_context():
        from app.db import get_db
        db = get_db()
        db.execute(
            """
            UPDATE device_runtime_state
            SET latest_screenshot_path = ?
            WHERE device_id = ?
            """,
            (str(rogue_path), device_id),
        )
        db.commit()

    response = client.get(f'/api/devices/{device_id}/latest-screenshot')

    assert response.status_code == 404
    assert response.data != b'should-not-be-served'


def test_refresh_screenshot_retries_after_401_by_refreshing_token(client):
    create_payload = {
        'friendly_name': 'Retry Device',
        'base_url': 'https://192.168.1.66',
    }
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.refresh_automation_token.side_effect = RuntimeError('no TinyPilot in tests')
        create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    with patch('app.api.TinyPilotClient') as client_cls:
        tp_client = client_cls.return_value
        tp_client.refresh_automation_token.side_effect = ['first-token', 'second-token']
        tp_client.get_screenshot.side_effect = [
            Exception('401 Client Error: Unauthorized for url'),
            b'jpeg-bytes',
        ]
        response = client.post(f'/api/devices/{device_id}/refresh-screenshot')

    assert response.status_code == 200
    assert response.json['screenshot_refreshed'] is True
