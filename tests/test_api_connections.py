from unittest.mock import patch

from app import create_app
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
        'api_key': 'test-api-key',
    }
    create_response = client.post('/api/devices', json=payload)
    assert create_response.status_code == 201
    created = create_response.json['device']
    assert created['friendly_name'] == payload['friendly_name']
    assert created['base_url'] == payload['base_url']
    assert created['api_key_configured'] is True

    list_response = client.get('/api/devices')
    assert list_response.status_code == 200
    assert len(list_response.json['devices']) == 1
    listed = list_response.json['devices'][0]
    assert listed['friendly_name'] == payload['friendly_name']
    assert listed['api_key_configured'] is True


def test_create_device_requires_api_key(client):
    payload = {'friendly_name': 'Bare URL', 'base_url': 'https://192.168.1.71'}
    response = client.post('/api/devices', json=payload)
    assert response.status_code == 400
    assert 'api_key' in response.json['error']


def test_resolution_from_automation_state_accepts_string_dimensions():
    state = {'result': {'source': {'resolution': {'width': '1920', 'height': '1080'}}}}
    assert resolution_from_automation_state(state) == '1920x1080'


def test_resolution_from_automation_state_accepts_pair_list():
    state = {'result': {'source': {'resolution': [3840, 2160]}}}
    assert resolution_from_automation_state(state) == '3840x2160'


def test_resolution_from_automation_state_accepts_dimension_string():
    state = {'result': {'resolution': '1280x720'}}
    assert resolution_from_automation_state(state) == '1280x720'


def test_create_device_rejects_blank_api_key(client):
    payload = {
        'friendly_name': 'Licensed Device',
        'base_url': 'https://192.168.1.88',
        'api_key': '   ',
    }
    response = client.post('/api/devices', json=payload)
    assert response.status_code == 400


def test_delete_device_removes_device_and_related_rows(client):
    payload = {
        'friendly_name': 'Delete Me',
        'base_url': 'https://192.168.1.99',
        'api_key': 'test-api-key',
    }
    create_response = client.post('/api/devices', json=payload)
    device_id = create_response.json['device']['id']
    list_before = client.get('/api/devices')
    assert list_before.json['devices'][0]['api_key_configured'] is True

    delete_response = client.delete(f'/api/devices/{device_id}')
    assert delete_response.status_code == 200
    assert delete_response.json['deleted'] is True

    list_response = client.get('/api/devices')
    assert list_response.status_code == 200
    assert all(device['id'] != device_id for device in list_response.json['devices'])


def test_refresh_screenshot_endpoint(client):
    create_payload = {
        'friendly_name': 'Screenshot Device',
        'base_url': 'https://192.168.1.51',
        'api_key': 'test-api-key',
    }
    create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    with patch('app.api.TinyPilotClient') as client_cls:
        inst = client_cls.return_value
        inst.get_screenshot.return_value = b'jpeg-bytes'
        response = client.post(f'/api/devices/{device_id}/refresh-screenshot')

    assert response.status_code == 200
    assert response.json['screenshot_refreshed'] is True
    assert response.json['screenshot_path'].endswith(f'device-{device_id}-latest.jpg')
    _args, kwargs = client_cls.call_args
    assert kwargs.get('api_key') == 'test-api-key'

    screenshot_response = client.get(f'/api/devices/{device_id}/latest-screenshot')
    assert screenshot_response.status_code == 200
    assert screenshot_response.data == b'jpeg-bytes'


def test_set_screenshot_refresh_interval_endpoint(client):
    create_payload = {
        'friendly_name': 'Interval Device',
        'base_url': 'https://192.168.1.77',
        'api_key': 'test-api-key',
    }
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


def test_index_page_loads(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'TinyPilot Dashboard' in response.data
    assert b'<dashboard-app' in response.data
    assert b'dashboard-app.js' in response.data


def test_device_snapshot_endpoint_returns_collapsed_and_expanded_sections(client):
    create_payload = {
        'friendly_name': 'Office Rack KVM',
        'base_url': 'https://192.168.1.44',
        'api_key': 'test-api-key',
    }
    create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    with patch('app.api.TinyPilotClient') as client_cls:
        tp_client = client_cls.return_value
        tp_client.get_status.return_value = {
            'ok': True,
            'video': {'connectedDeviceResolution': '1920x1080'},
        }
        tp_client.get_version.return_value = {'version': '2.6.5'}
        tp_client.get_network_status.return_value = {
            'interfaces': [
                {
                    'name': 'eth0',
                    'isConnected': True,
                    'ipAddress': '192.168.1.44',
                    'macAddress': 'aa:bb:cc:dd:ee:ff',
                },
                {
                    'name': 'wlan0',
                    'isConnected': False,
                    'ipAddress': None,
                    'macAddress': None,
                },
            ],
        }
        tp_client.get_video_settings.return_value = {'h264Bitrate': 8000, 'streamingMode': 'MJPEG'}
        tp_client.get_automation_state.return_value = {}
        tp_client.get_latest_release.return_value = {
            'version': '2.6.5',
            'kind': 'automatic',
            'data': None,
            'licenseCheckStatus': 'VALID',
        }
        tp_client.get_update_status.return_value = {
            'status': 'NOT_RUNNING',
            'updateError': None,
        }

        snapshot_response = client.get(f'/api/devices/{device_id}/device/snapshot')

    assert snapshot_response.status_code == 200
    payload = snapshot_response.json
    assert payload['source_base_url'] == create_payload['base_url']
    assert payload['collapsed']['software_version'] == '2.6.5'
    assert payload['collapsed']['api_key_status'] == 'configured'
    assert 'connected_device_resolution' not in payload['collapsed']
    assert payload['expanded']['network']['data']['interfaces'][0]['ipAddress'] == '192.168.1.44'
    assert payload['expanded']['connected_device_resolution'] == '1920x1080'
    assert payload['expanded']['software_update']['update_available'] is False
    assert payload['expanded']['software_update']['can_start'] is False
    client_cls.assert_called_once()
    _args, kwargs = client_cls.call_args
    assert kwargs.get('api_key') == 'test-api-key'


def test_device_snapshot_prefers_automation_state_resolution(client):
    create_payload = {
        'friendly_name': 'State Resolution',
        'base_url': 'https://192.168.1.55',
        'api_key': 'test-api-key',
    }
    create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    with patch('app.api.TinyPilotClient') as client_cls:
        tp_client = client_cls.return_value
        tp_client.get_status.return_value = {'ok': True}
        tp_client.get_version.return_value = {'version': '3.0.2'}
        tp_client.get_network_status.return_value = {'interfaces': []}
        tp_client.get_video_settings.return_value = {'h264Bitrate': 900}
        tp_client.get_automation_state.return_value = {
            'result': {'source': {'resolution': {'width': 2560, 'height': 1440}}},
        }
        tp_client.get_latest_release.return_value = {
            'version': '3.1.0',
            'kind': 'automatic',
            'data': None,
            'licenseCheckStatus': 'VALID',
        }
        tp_client.get_update_status.return_value = {
            'status': 'NOT_RUNNING',
            'updateError': None,
        }

        snapshot_response = client.get(f'/api/devices/{device_id}/device/snapshot')

    assert snapshot_response.status_code == 200
    assert 'connected_device_resolution' not in snapshot_response.json['collapsed']
    assert snapshot_response.json['expanded']['connected_device_resolution'] == '2560x1440'
    assert snapshot_response.json['expanded']['software_update']['update_available'] is True
    assert snapshot_response.json['expanded']['software_update']['can_start'] is True
    tp_client.get_automation_state.assert_called_once_with()


def test_latest_screenshot_rejects_paths_outside_screenshots_dir(client, tmp_path):
    create_payload = {
        'friendly_name': 'Path Test',
        'base_url': 'https://192.168.1.80',
        'api_key': 'test-api-key',
    }
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


def test_refresh_screenshot_surfaces_api_errors(client):
    create_payload = {
        'friendly_name': 'Retry Device',
        'base_url': 'https://192.168.1.66',
        'api_key': 'test-api-key',
    }
    create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.get_screenshot.side_effect = Exception(
            '403 Client Error: Forbidden'
        )
        response = client.post(f'/api/devices/{device_id}/refresh-screenshot')

    assert response.status_code == 502
    assert 'failed to refresh screenshot' in response.json['error']


def test_device_snapshot_license_blocked_update_cannot_start(client):
    create_payload = {
        'friendly_name': 'Voyager 2 Unlicensed',
        'base_url': 'https://192.168.1.90',
        'api_key': 'test-api-key',
    }
    create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    with patch('app.api.TinyPilotClient') as client_cls:
        tp_client = client_cls.return_value
        tp_client.get_status.return_value = {'ok': True}
        tp_client.get_version.return_value = {'version': '3.0.0'}
        tp_client.get_network_status.return_value = {'interfaces': []}
        tp_client.get_video_settings.return_value = {}
        tp_client.get_automation_state.return_value = {}
        tp_client.get_latest_release.return_value = {
            'version': '3.2.0',
            'kind': 'automatic',
            'data': None,
            'licenseCheckStatus': 'UNLICENSED',
        }
        tp_client.get_update_status.return_value = {
            'status': 'NOT_RUNNING',
            'updateError': None,
        }
        response = client.get(f'/api/devices/{device_id}/device/snapshot')

    assert response.status_code == 200
    update = response.json['expanded']['software_update']
    assert update['update_available'] is True
    assert update['can_start'] is False


def test_start_device_update_endpoint(client):
    create_payload = {
        'friendly_name': 'Update Target',
        'base_url': 'https://192.168.1.91',
        'api_key': 'test-api-key',
    }
    create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.start_update.return_value = {}
        response = client.put(
            f'/api/devices/{device_id}/device/update',
            json={'version': '3.2.0'},
        )

    assert response.status_code == 200
    assert response.json['update_started'] is True
    client_cls.return_value.start_update.assert_called_once_with('3.2.0')


def test_start_device_update_requires_version(client):
    create_payload = {
        'friendly_name': 'Update Target',
        'base_url': 'https://192.168.1.92',
        'api_key': 'test-api-key',
    }
    create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']
    response = client.put(f'/api/devices/{device_id}/device/update', json={})
    assert response.status_code == 400


def test_get_device_update_status_endpoint(client):
    create_payload = {
        'friendly_name': 'Status Target',
        'base_url': 'https://192.168.1.93',
        'api_key': 'test-api-key',
    }
    create_response = client.post('/api/devices', json=create_payload)
    device_id = create_response.json['device']['id']

    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.get_update_status.return_value = {
            'status': 'IN_PROGRESS',
            'updateError': None,
        }
        response = client.get(f'/api/devices/{device_id}/device/update')

    assert response.status_code == 200
    assert response.json['status'] == 'IN_PROGRESS'
