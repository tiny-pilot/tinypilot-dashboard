"""Tests for the /api/version endpoint."""

from app import __version__


def test_version_endpoint_reports_module_version(client):
    response = client.get('/api/version')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {'version': __version__}


def test_version_is_semver_like():
    parts = __version__.split('.')
    assert len(parts) == 3, f'expected MAJOR.MINOR.PATCH, got {__version__!r}'
    assert all(part.isdigit() for part in parts), (
        f'expected numeric version parts, got {__version__!r}'
    )
