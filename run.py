import os

from app import create_app
from waitress import serve

app = create_app()


if __name__ == '__main__':
    # LAN Docker: 0.0.0.0 so compose port mapping works.
    # Cloud sidecar: set DASHBOARD_BIND=127.0.0.1 so the unauthenticated
    # dashboard is loopback-only behind the gateway proxy.
    host = os.environ.get('DASHBOARD_BIND', '0.0.0.0')
    port = int(os.environ.get('DASHBOARD_PORT', '8080'))
    serve(app, host=host, port=port)
