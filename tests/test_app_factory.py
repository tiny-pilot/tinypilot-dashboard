from pathlib import Path

from app import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_create_app_returns_app():
    app = create_app()

    assert app is not None


def test_run_uses_waitress_with_bind_override():
    source = (ROOT / 'run.py').read_text(encoding='utf-8')
    assert 'from waitress import serve' in source
    assert 'app.run(' not in source
    assert 'DASHBOARD_BIND' in source
    assert 'DASHBOARD_PORT' in source
