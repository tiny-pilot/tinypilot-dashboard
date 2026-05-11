from app import create_app


def test_create_app_returns_app():
    app = create_app()

    assert app is not None
