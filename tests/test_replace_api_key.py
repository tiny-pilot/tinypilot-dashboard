"""Replace API key endpoint."""

from unittest.mock import patch


def test_replace_api_key_updates_secret_without_echo(client):
    create = client.post('/api/devices', json={
        'friendly_name': 'Rack',
        'base_url': 'https://192.168.1.9',
        'api_key': 'old-key',
    })
    device_id = create.json['device']['id']
    response = client.put(
        f'/api/devices/{device_id}/api-key',
        json={'api_key': 'new-key'},
    )
    assert response.status_code == 200
    assert response.json == {
        'device_id': device_id,
        'api_key_configured': True,
    }
    body = response.get_data(as_text=True)
    assert 'new-key' not in body
    assert 'old-key' not in body

    with patch('app.api.TinyPilotClient') as client_cls:
        tp = client_cls.return_value
        tp.get_status.return_value = {'ok': True}
        tp.get_version.return_value = {'version': '3.2.0'}
        tp.get_network_status.return_value = {'interfaces': []}
        tp.get_video_settings.return_value = {}
        tp.get_automation_state.return_value = {}
        tp.get_latest_release.return_value = {
            'version': '3.2.0',
            'kind': 'automatic',
            'data': None,
            'licenseCheckStatus': 'VALID',
        }
        tp.get_update_status.return_value = {
            'status': 'NOT_RUNNING',
            'updateError': None,
        }
        snap = client.get(f'/api/devices/{device_id}/device/snapshot')

    assert snap.status_code == 200
    _args, kwargs = client_cls.call_args
    assert kwargs.get('api_key') == 'new-key'


def test_replace_api_key_rejects_blank(client):
    create = client.post('/api/devices', json={
        'friendly_name': 'Rack',
        'base_url': 'https://192.168.1.10',
        'api_key': 'old-key',
    })
    device_id = create.json['device']['id']
    response = client.put(
        f'/api/devices/{device_id}/api-key',
        json={'api_key': '   '},
    )
    assert response.status_code == 400


def test_replace_api_key_rejects_non_string(client):
    create = client.post('/api/devices', json={
        'friendly_name': 'Rack',
        'base_url': 'https://192.168.1.11',
        'api_key': 'old-key',
    })
    device_id = create.json['device']['id']
    response = client.put(
        f'/api/devices/{device_id}/api-key',
        json={'api_key': 12345},
    )
    assert response.status_code == 400
    assert response.json['error'] == 'api_key is required'


def test_replace_api_key_unknown_device(client):
    response = client.put('/api/devices/9999/api-key', json={'api_key': 'x'})
    assert response.status_code == 404
