"""HTTP tests for /api/assistant (BYOK assistant backend)."""

from unittest.mock import patch

import pytest
from app.assistant.agent import clear_session_data_for_tests
from app.assistant.agent import has_grant
from app.assistant.agent import set_grant


def test_assistant_config_disabled_without_api_key(client):
    response = client.get('/api/assistant/config')
    assert response.status_code == 200
    assert response.json['enabled'] is False


def test_chat_returns_503_when_assistant_not_configured(client):
    response = client.post(
        '/api/assistant/1/chat',
        json={'message': 'Hello'},
    )
    assert response.status_code == 503
    assert response.json['error'] == 'assistant_not_configured'


@pytest.fixture
def assistant_enabled(client, monkeypatch):
    monkeypatch.setenv('ASSISTANT_API_KEY', 'test-key-sk')


@pytest.fixture
def assistant_device(client, assistant_enabled):
    create = client.post(
        '/api/devices',
        json={
            'friendly_name': 'Assistant device',
            'base_url': 'https://192.168.1.60',
            'api_key': 'device-api-key',
        },
    )
    assert create.status_code == 201
    return create.json['device']['id']


def test_assistant_config_when_key_set(client, assistant_enabled):
    response = client.get('/api/assistant/config')
    assert response.status_code == 200
    body = response.json
    assert body['enabled'] is True
    assert body['model'] == 'gpt-4o'
    assert body['max_steps'] == 20


def test_assistant_config_put_instructions(client, assistant_enabled):
    put = client.put(
        '/api/assistant/config',
        json={'instructions': 'Treat this host as production.'},
    )
    assert put.status_code == 200
    assert put.json['instructions'] == 'Treat this host as production.'

    get = client.get('/api/assistant/config')
    assert get.json['instructions'] == 'Treat this host as production.'


def test_bootstrap_404_without_device(client, assistant_enabled):
    response = client.post('/api/assistant/99/bootstrap')
    assert response.status_code == 404
    assert response.json['error'] == 'device_not_found'


def test_bootstrap_resets_grant(client, assistant_enabled):
    create = client.post(
        '/api/devices',
        json={
            'friendly_name': 'Assistant host',
            'base_url': 'https://192.168.1.50',
            'api_key': 'device-api-key',
        },
    )
    assert create.status_code == 201
    device_id = create.json['device']['id']
    session = f'device-{device_id}'

    with client.application.app_context():
        clear_session_data_for_tests()
        set_grant(session, True)

    fake_jpeg = b'\xff\xd8\xff\xd9'
    with patch(
        'app.device_client.TinyPilotClient.get_screenshot',
        return_value=fake_jpeg,
    ):
        response = client.post(f'/api/assistant/{device_id}/bootstrap')

    assert response.status_code == 200
    body = response.json
    assert body['ok'] is True
    assert body['grant_allowed'] is False

    with client.application.app_context():
        assert has_grant(session) is False


def test_still_returns_503_when_assistant_disabled(client):
    response = client.get('/api/assistant/1/still')
    assert response.status_code == 503
    assert response.json['error'] == 'assistant_not_configured'


def test_assistant_page_redirects_when_disabled(client):
    response = client.get('/assistant/1')
    assert response.status_code == 302
    assert response.location.endswith('/')


def test_assistant_page_renders_when_enabled(client, assistant_enabled):
    response = client.get('/assistant/1')
    assert response.status_code == 200
    assert b'assistant-shell' in response.data
    assert b'assistant.js' in response.data


def test_grant_endpoint_persists_allowed(client, assistant_device):
    device_id = assistant_device
    session = f'device-{device_id}'

    on = client.post(
        f'/api/assistant/{device_id}/grant',
        json={'allowed': True},
    )
    assert on.status_code == 200
    assert on.json['ok'] is True
    assert on.json['allowed'] is True

    with client.application.app_context():
        assert has_grant(session) is True

    off = client.post(
        f'/api/assistant/{device_id}/grant',
        json={'allowed': False},
    )
    assert off.json['allowed'] is False
    with client.application.app_context():
        assert has_grant(session) is False


def test_stop_endpoint_returns_ok(client, assistant_device):
    response = client.post(f'/api/assistant/{assistant_device}/stop')
    assert response.status_code == 200
    assert response.json == {'ok': True, 'stopped': True}


def test_still_returns_jpeg_after_bootstrap(client, assistant_device):
    fake_jpeg = b'\xff\xd8\xff\xd9'
    with patch(
        'app.device_client.TinyPilotClient.get_screenshot',
        return_value=fake_jpeg,
    ):
        boot = client.post(f'/api/assistant/{assistant_device}/bootstrap')
    assert boot.status_code == 200

    still = client.get(f'/api/assistant/{assistant_device}/still')
    assert still.status_code == 200
    assert still.mimetype == 'image/jpeg'
    assert still.data == fake_jpeg


def test_still_204_when_no_context(client, assistant_device):
    session = f'device-{assistant_device}'
    with client.application.app_context():
        clear_session_data_for_tests()
    response = client.get(f'/api/assistant/{assistant_device}/still')
    assert response.status_code == 204
    with client.application.app_context():
        assert has_grant(session) is False


def test_chat_streams_ndjson_events(client, assistant_device):
    def fake_turn(**_kwargs):
        yield {'type': 'text', 'text': 'Hello'}
        yield {'type': 'done'}

    with patch('app.assistant.routes.run_agent_turn', side_effect=fake_turn):
        response = client.post(
            f'/api/assistant/{assistant_device}/chat',
            json={'message': 'Hi'},
        )

    assert response.status_code == 200
    assert response.mimetype == 'application/x-ndjson'
    lines = [line for line in response.data.decode().splitlines() if line]
    assert len(lines) == 2
    assert '"type":"text"' in lines[0]
    assert '"type":"done"' in lines[1]
