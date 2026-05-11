from unittest.mock import Mock
from unittest.mock import patch

from app.tinypilot_client import TinyPilotClient


def test_refresh_csrf_parses_meta_tag():
    response = Mock()
    response.text = '<html><head><meta name="csrf-token" content="csrf-xyz"></head></html>'
    response.raise_for_status.return_value = None

    with patch('app.tinypilot_client.requests.Session.get', return_value=response):
        client = TinyPilotClient('https://tp.local')
        csrf = client.refresh_csrf_token()

    assert csrf == 'csrf-xyz'


def test_get_json_retries_once_after_forbidden():
    warmup_ok = Mock(status_code=200)
    warmup_ok.raise_for_status.return_value = None

    api_forbidden = Mock(status_code=403)
    api_forbidden.raise_for_status.return_value = None

    csrf_html = Mock(status_code=200)
    csrf_html.text = '<html><head><meta name="csrf-token" content="csrf-new"></head></html>'
    csrf_html.raise_for_status.return_value = None

    api_success = Mock(status_code=200)
    api_success.raise_for_status.return_value = None
    api_success.json.return_value = {'version': '3.0.2'}

    with patch(
        'app.tinypilot_client.requests.Session.get',
        side_effect=[warmup_ok, api_forbidden, csrf_html, api_success],
    ):
        client = TinyPilotClient('https://tp.local')
        result = client.get_version()

    assert result == {'version': '3.0.2'}
