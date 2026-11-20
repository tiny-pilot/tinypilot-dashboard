"""HTTP tests for /api/assistant (BYOK assistant backend)."""

import pytest


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


def test_assistant_page_redirects_when_disabled(client):
    response = client.get('/assistant/1')
    assert response.status_code == 302
    assert response.location.endswith('/')


def test_assistant_page_renders_when_enabled(client, assistant_enabled):
    response = client.get('/assistant/1')
    assert response.status_code == 200
    assert b'assistant-shell' in response.data
    assert b'assistant.js' in response.data