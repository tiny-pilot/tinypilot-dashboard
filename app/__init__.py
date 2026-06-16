"""Flask application factory for the TinyPilot Dashboard."""

from pathlib import Path

from flask import Flask
from flask import render_template
from flask import send_from_directory

from app.api import api_blueprint
from app.db import close_db, init_db

# Public product version. Version bands signal lifecycle stage to customers:
#   0.1.x  -> alpha
#   0.5.x  -> beta
#   1.0.0  -> first stable release
# Bump this on every customer-visible release.
__version__ = '0.1.1'


def create_app(test_config=None):
    """Build and configure the Flask app used by ``run.py`` and tests."""
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE_PATH='data/dashboard.sqlite',
        SECRET_KEY_PATH='data/secret.key',
        DASHBOARD_VERSION=__version__,
    )
    app.config.from_prefixed_env()
    if test_config:
        app.config.update(test_config)

    with app.app_context():
        init_db()

    app.register_blueprint(api_blueprint)
    app.teardown_appcontext(close_db)

    @app.context_processor
    def inject_dashboard_version():
        return {'dashboard_version': app.config['DASHBOARD_VERSION']}

    @app.after_request
    def prevent_html_caching(response):
        ctype = response.headers.get('Content-Type', '')
        base = ctype.split(';')[0].strip().lower()
        if base == 'text/html':
            response.headers['Cache-Control'] = 'no-store, max-age=0'
            response.headers['Pragma'] = 'no-cache'
        return response

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/favicon.ico')
    def favicon():
        return send_from_directory(
            Path(app.static_folder) / 'img',
            'favicon.png',
            mimetype='image/png',
        )

    return app
