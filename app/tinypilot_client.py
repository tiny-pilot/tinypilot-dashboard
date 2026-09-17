"""HTTP client for TinyPilot devices (Pro 3.2.0+ Automation API key).

Uses a Bearer API key for allowlisted routes (screenshot, version, network,
video settings, ``/state``, latestRelease, update) plus a warmup GET for
cookie affinity.

TLS note: TinyPilot devices typically present a self-signed certificate, so
this client sets ``session.verify = False`` and silences the corresponding
urllib3 warning. The alpha is local-network only; see ``README.md`` for the
security tradeoff. Do not reuse this client for non-TinyPilot hosts.
"""

from typing import Any
from typing import Optional

import requests
import urllib3

# TinyPilot ships with a self-signed TLS certificate, so we cannot verify it
# from the dashboard host. Silence the per-request InsecureRequestWarning that
# urllib3 would otherwise log on every call. This is intentional and scoped to
# the dashboard's TinyPilot client only; see module docstring.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TinyPilotClient:
    """Thin HTTP client for a single TinyPilot device."""

    def __init__(self, base_url: str, *, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.pop('Origin', None)
        # TinyPilot self-signed certs: see module docstring.
        self.session.verify = False

    def _bearer_headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {'Authorization': f'Bearer {self.api_key}'}

    def _raise_for_status(self, response: requests.Response) -> None:
        """Raise an HTTPError, including TinyPilot's error message when present.

        TinyPilot error responses carry ``{"message": "...", "code": ...}``.
        Surfacing that message makes failures much easier to diagnose.
        """
        if response.ok:
            return
        device_message = ''
        try:
            body = response.json()
            device_message = body.get('message') or ''
        except ValueError:
            pass
        detail = f'{response.status_code} {response.reason}'
        if device_message:
            detail = f'{detail}: {device_message}'
        raise requests.HTTPError(detail, response=response)

    def _get_json(self, path: str, *, bearer: bool = False) -> dict[str, Any]:
        warmup = self.session.get(self.base_url, timeout=10)
        warmup.raise_for_status()
        headers = self._bearer_headers() if bearer else {}
        response = self.session.get(
            f'{self.base_url}{path}',
            headers=headers,
            timeout=10,
        )
        self._raise_for_status(response)
        return response.json()

    def _put_json(self, path: str, body: Optional[dict] = None) -> dict[str, Any]:
        warmup = self.session.get(self.base_url, timeout=10)
        warmup.raise_for_status()
        response = self.session.put(
            f'{self.base_url}{path}',
            json=body,
            headers=self._bearer_headers(),
            timeout=30,
        )
        self._raise_for_status(response)
        return response.json() if response.content else {}

    def get_network_status(self):
        return self._get_json('/api/network/status', bearer=True)

    def get_status(self) -> dict[str, Any]:
        return self._get_json('/api/status')

    def get_version(self) -> dict[str, Any]:
        return self._get_json('/api/version', bearer=True)

    def get_video_settings(self) -> dict[str, Any]:
        return self._get_json('/api/settings/video', bearer=True)

    def get_latest_release(self) -> dict[str, Any]:
        return self._get_json('/api/latestRelease', bearer=True)

    def get_update_status(self) -> dict[str, Any]:
        return self._get_json('/api/update', bearer=True)

    def start_update(self, version: str) -> dict[str, Any]:
        return self._put_json('/api/update', {'version': version})

    def get_screenshot(self) -> bytes:
        response = self.session.get(
            f'{self.base_url}/api/v1/screenshot',
            headers=self._bearer_headers(),
            timeout=15,
        )
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            raise ValueError(
                'TinyPilot returned no screenshot image (HTTP 204 or empty body); '
                'often means no video signal from the target.',
            )
        return response.content

    def get_automation_state(self) -> dict[str, Any]:
        """Unofficial Automation API: connected display resolution via result.source.resolution."""
        response = self.session.get(
            f'{self.base_url}/state',
            headers=self._bearer_headers(),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
