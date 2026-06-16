"""Unit tests for TinyPilotClient virtual media methods."""

from unittest.mock import MagicMock

import pytest

from app.tinypilot_client import TinyPilotClient


@pytest.fixture
def client():
    return TinyPilotClient('https://device.local')


def make_response(json_data=None, status_code=200, content=b'{}'):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_data or {}
    r.content = content
    r.raise_for_status = MagicMock()
    r.text = '<html></html>'
    return r


def test_get_mass_storage_returns_backing_files_and_mount_mode(client):
    warmup = make_response()
    api_response = make_response({
        'backingFiles': [{'name': 'ubuntu.iso', 'mounted': True, 'loadedBytes': 1000, 'totalBytes': 1000}],
        'intermediateFiles': [],
        'mountMode': 'CDROM',
    })
    mock_session = MagicMock()
    mock_session.get.side_effect = [warmup, api_response]
    client.session = mock_session

    result = client.get_mass_storage()

    assert result['mountMode'] == 'CDROM'
    assert result['backingFiles'][0]['name'] == 'ubuntu.iso'


def test_get_mass_storage_filename_from_url_returns_filename(client):
    warmup = make_response()
    api_response = make_response({'fileName': 'ubuntu-24.04.iso'})
    mock_session = MagicMock()
    mock_session.get.side_effect = [warmup, api_response]
    client.session = mock_session

    result = client.get_mass_storage_filename_from_url('https://example.com/ubuntu.iso')

    assert result == 'ubuntu-24.04.iso'


def test_fetch_mass_storage_from_url_calls_correct_endpoint(client):
    warmup = make_response()
    put_response = make_response()
    mock_session = MagicMock()
    mock_session.get.return_value = warmup
    mock_session.put.return_value = put_response
    client.session = mock_session

    client.fetch_mass_storage_from_url('ubuntu.iso', 'https://example.com/ubuntu.iso')

    call_args = mock_session.put.call_args
    assert 'backingFiles/ubuntu.iso/fetchFromUrl' in call_args[0][0]
    assert call_args[1]['json'] == {'url': 'https://example.com/ubuntu.iso'}


def test_mount_mass_storage_sends_correct_path_and_mode(client):
    warmup = make_response()
    put_response = make_response({'success': True})
    mock_session = MagicMock()
    mock_session.get.return_value = warmup
    mock_session.put.return_value = put_response
    client.session = mock_session

    client.mount_mass_storage('ubuntu.iso', 'CDROM')

    call_args = mock_session.put.call_args
    assert 'massStorage/mount/ubuntu.iso' in call_args[0][0]
    assert call_args[1]['params']['mode'] == 'CDROM'


def test_eject_mass_storage_calls_eject_endpoint(client):
    warmup = make_response()
    put_response = make_response(content=b'')
    mock_session = MagicMock()
    mock_session.get.return_value = warmup
    mock_session.put.return_value = put_response
    client.session = mock_session

    client.eject_mass_storage()

    call_args = mock_session.put.call_args
    assert 'massStorage/eject' in call_args[0][0]


def test_put_json_retries_with_fresh_csrf_on_401(client):
    warmup = make_response()
    warmup.text = '<meta name="csrf-token" content="tok1" />'
    first_put = make_response(status_code=401, content=b'')
    first_put.raise_for_status = MagicMock()  # Don't raise on 401 — retry handles it.
    retry_warmup = make_response()
    retry_warmup.text = '<meta name="csrf-token" content="tok2" />'
    retry_put = make_response({'ok': True})

    mock_session = MagicMock()
    mock_session.get.side_effect = [warmup, retry_warmup]
    mock_session.put.side_effect = [first_put, retry_put]
    client.session = mock_session

    result = client._put_json('/api/massStorage/eject')

    assert mock_session.put.call_count == 2
    _args, second_kwargs = mock_session.put.call_args_list[1]
    assert second_kwargs['headers'].get('X-CSRFToken') == 'tok2'
    assert result == {'ok': True}
