"""Pytest configuration and shared fixtures for tests."""

import pytest

from app import create_app


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / 'dashboard.sqlite'
    key_path = tmp_path / 'secret.key'
    app = create_app({
        'TESTING': True,
        'DATABASE_PATH': str(db_path),
        'SECRET_KEY_PATH': str(key_path),
    })
    return app.test_client()
