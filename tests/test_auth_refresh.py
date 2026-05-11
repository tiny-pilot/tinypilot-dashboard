from unittest.mock import Mock
from unittest.mock import patch

from app.tinypilot_client import TinyPilotClient


def test_refresh_automation_token_calls_auth_endpoint_without_body():
    response = Mock()
    response.json.return_value = {'token': 'new-token'}
    response.raise_for_status.return_value = None

    with patch('app.tinypilot_client.requests.Session.post', return_value=response) as post_mock:
        client = TinyPilotClient('https://tp.local')
        token = client.refresh_automation_token()

    assert token == 'new-token'
    post_mock.assert_called_once_with(
        'https://tp.local/api/v1/auth',
        timeout=10,
    )
