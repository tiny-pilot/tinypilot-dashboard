"""Unit tests for TinyPilotClient Bearer API helpers."""

from unittest.mock import MagicMock

import pytest
from app.tinypilot_client import TinyPilotClient


@pytest.fixture
def client():
    return TinyPilotClient('https://device.local', api_key='test-key')


def make_response(json_data=None, status_code=200, content=b'{}', ok=True):
    r = MagicMock()
    r.status_code = status_code
    r.ok = ok and status_code < 400
    r.reason = 'OK' if r.ok else 'Error'
    r.json.return_value = json_data or {}
    r.content = content
    r.raise_for_status = MagicMock()
    r.text = '<html></html>'
    return r


def test_probe_status_is_one_direct_get(client):
    api_response = make_response({})
    mock_session = MagicMock()
    mock_session.get.return_value = api_response
    client.session = mock_session

    client.probe_status()

    assert mock_session.get.call_count == 1
    args, kwargs = mock_session.get.call_args
    assert args[0].endswith('/api/status')
    assert kwargs['timeout'] == (3, 10)
    assert 'Authorization' not in kwargs.get('headers', {})


def test_get_version_sends_bearer_header(client):
    warmup = make_response()
    api_response = make_response({'version': '3.2.0'})
    mock_session = MagicMock()
    mock_session.get.side_effect = [warmup, api_response]
    client.session = mock_session

    result = client.get_version()

    assert result['version'] == '3.2.0'
    warmup_kwargs = mock_session.get.call_args_list[0][1]
    assert warmup_kwargs['timeout'] == (3, 10)
    _args, kwargs = mock_session.get.call_args_list[1]
    assert kwargs['headers']['Authorization'] == 'Bearer test-key'
    assert kwargs['timeout'] == (3, 10)


def test_get_screenshot_uses_bearer_and_returns_bytes(client):
    api_response = make_response(content=b'jpeg-bytes')
    mock_session = MagicMock()
    mock_session.get.return_value = api_response
    client.session = mock_session

    result = client.get_screenshot()

    assert result == b'jpeg-bytes'
    _args, kwargs = mock_session.get.call_args
    assert kwargs['headers']['Authorization'] == 'Bearer test-key'
    assert _args[0].endswith('/api/v1/screenshot')
    assert kwargs['timeout'] == (3, 15)


def test_get_lan_monitor_events_sends_bearer_header(client):
    warmup = make_response()
    api_response = make_response({'events': []})
    mock_session = MagicMock()
    mock_session.get.side_effect = [warmup, api_response]
    client.session = mock_session

    result = client.get_lan_monitor_events()

    assert result == {'events': []}
    _args, kwargs = mock_session.get.call_args_list[1]
    assert kwargs['headers']['Authorization'] == 'Bearer test-key'
    assert _args[0].endswith('/api/lanMonitor/events?limit=100')


def test_get_lan_monitor_devices_filters_monitored(client):
    warmup = make_response()
    api_response = make_response({'devices': []})
    mock_session = MagicMock()
    mock_session.get.side_effect = [warmup, api_response]
    client.session = mock_session

    result = client.get_lan_monitor_devices()

    assert result == {'devices': []}
    _args, kwargs = mock_session.get.call_args_list[1]
    assert kwargs['headers']['Authorization'] == 'Bearer test-key'
    assert _args[0].endswith('/api/lanMonitor/devices?monitored=true')


def test_get_lan_monitor_status_sends_bearer_header(client):
    warmup = make_response()
    api_response = make_response({'enabled': True})
    mock_session = MagicMock()
    mock_session.get.side_effect = [warmup, api_response]
    client.session = mock_session

    result = client.get_lan_monitor_status()

    assert result == {'enabled': True}
    _args, kwargs = mock_session.get.call_args_list[1]
    assert kwargs['headers']['Authorization'] == 'Bearer test-key'
    assert _args[0].endswith('/api/lanMonitor/status')


def test_get_latest_release_uses_bearer(client):
    warmup = make_response()
    api_response = make_response(
        {
            'version': '3.2.0',
            'kind': 'automatic',
            'data': None,
            'licenseCheckStatus': 'VALID',
        }
    )
    mock_session = MagicMock()
    mock_session.get.side_effect = [warmup, api_response]
    client.session = mock_session

    result = client.get_latest_release()

    assert result['version'] == '3.2.0'
    _args, kwargs = mock_session.get.call_args_list[1]
    assert kwargs['headers']['Authorization'] == 'Bearer test-key'
    assert _args[0].endswith('/api/latestRelease')


def test_start_update_puts_version_with_bearer(client):
    warmup = make_response()
    put_response = make_response(content=b'')
    mock_session = MagicMock()
    mock_session.get.return_value = warmup
    mock_session.put.return_value = put_response
    client.session = mock_session

    client.start_update('3.2.0')

    _args, kwargs = mock_session.put.call_args
    assert _args[0].endswith('/api/update')
    assert kwargs['json'] == {'version': '3.2.0'}
    assert kwargs['headers']['Authorization'] == 'Bearer test-key'
