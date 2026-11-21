"""LAN Monitor alert preference and poll proxy."""

from unittest.mock import MagicMock
from unittest.mock import patch

import requests
from app.db import get_db


def _create(client, name='Rack'):
    response = client.post('/api/devices', json={
        'friendly_name': name,
        'base_url': 'https://192.168.1.40',
        'api_key': 'test-api-key',
    })
    assert response.status_code == 201
    return response.json['device']['id']


def test_new_device_does_not_receive_lan_monitor_alerts(client):
    device_id = _create(client)
    listed = client.get('/api/devices')
    device = next(item for item in listed.json['devices'] if item['id'] == device_id)
    assert device['lan_monitor_alerts'] is False


def test_lan_monitor_alerts_flag_round_trip(client):
    device_id = _create(client)
    saved = client.put(
        f'/api/devices/{device_id}/lan-monitor-alerts',
        json={'enabled': True},
    )
    assert saved.status_code == 200
    assert saved.json == {'device_id': device_id, 'lan_monitor_alerts': True}
    listed = client.get('/api/devices')
    device = next(item for item in listed.json['devices'] if item['id'] == device_id)
    assert device['lan_monitor_alerts'] is True

    rejected = client.put(
        f'/api/devices/{device_id}/lan-monitor-alerts',
        json={'enabled': 'yes'},
    )
    assert rejected.status_code == 400


def test_lan_monitor_poll_trims_fields(client):
    device_id = _create(client)
    with patch('app.api.TinyPilotClient') as client_cls:
        inst = client_cls.return_value
        inst.get_lan_monitor_events.return_value = {'events': [
            {
                'id': 3,
                'type': 'DEVICE_OFFLINE',
                'deviceId': 'fw',
                'timestamp': 't3',
                'payload': {'secret': 'no'},
            },
            {'type': 'DEVICE_DISCOVERED'},
        ]}
        inst.get_lan_monitor_devices.return_value = {'devices': [{
            'id': 'fw',
            'displayLabel': 'Firewall',
            'ipAddress': '10.0.0.1',
        }]}
        response = client.get(f'/api/devices/{device_id}/lan-monitor')

    assert response.status_code == 200
    assert response.json == {
        'ok': True,
        'events': [{
            'id': 3,
            'type': 'DEVICE_OFFLINE',
            'deviceId': 'fw',
            'timestamp': 't3',
        }],
        'monitored': [{'id': 'fw', 'displayLabel': 'Firewall'}],
    }


def test_lan_monitor_disabled_is_quiet(client):
    device_id = _create(client)
    error = requests.HTTPError('unavailable')
    error.response = MagicMock(status_code=503)
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.get_lan_monitor_events.side_effect = error
        response = client.get(f'/api/devices/{device_id}/lan-monitor')
    assert response.status_code == 200
    assert response.json == {'ok': False}


def test_lan_monitor_unknown_device(client):
    response = client.get('/api/devices/999/lan-monitor')
    assert response.status_code == 404


def test_lan_monitor_requires_api_key(client):
    device_id = _create(client)
    with client.application.app_context():
        get_db().execute(
            """
            UPDATE device_auth
            SET encrypted_automation_token = NULL
            WHERE device_id = ?
            """,
            (device_id,),
        )
        get_db().commit()
    response = client.get(f'/api/devices/{device_id}/lan-monitor')
    assert response.status_code == 400


def _status(client, device_id, **kwargs):
    with patch('app.api.TinyPilotClient') as client_cls:
        client_cls.return_value.get_lan_monitor_status.side_effect = None
        client_cls.return_value.get_lan_monitor_status.return_value = kwargs.get('body')
        if 'error' in kwargs:
            client_cls.return_value.get_lan_monitor_status.side_effect = kwargs['error']
        return client.get(f'/api/devices/{device_id}/lan-monitor-status')


def test_lan_monitor_status_reports_enabled(client):
    device_id = _create(client)
    response = _status(client, device_id, body={
        'enabled': True,
        'interfaces': [{'name': 'eth0'}],
    })
    assert response.status_code == 200
    assert response.json == {'ok': True, 'enabled': True}


def test_lan_monitor_status_reports_off(client):
    device_id = _create(client)
    response = _status(client, device_id, body={'enabled': False})
    assert response.json == {'ok': True, 'enabled': False}


def test_lan_monitor_status_missing_and_unreachable(client):
    device_id = _create(client)
    missing = requests.HTTPError('missing')
    missing.response = MagicMock(status_code=404)
    response = _status(client, device_id, error=missing)
    assert response.json == {'ok': False, 'reason': 'missing'}
    response = _status(client, device_id, error=requests.ConnectionError('down'))
    assert response.json == {'ok': False, 'reason': 'unreachable'}
