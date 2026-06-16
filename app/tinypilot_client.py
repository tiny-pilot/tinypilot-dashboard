"""HTTP client for TinyPilot devices.

This client wraps three groups of TinyPilot endpoints:

* **Documented Automation REST API** (``/api/v1/*``, Bearer token) — limited to
  what the official docs cover (auth, screenshot, keystroke, mouse, paste).
* **Device management / metrics** — TinyPilot Web UI JSON routes (``/api/*``)
  reached through the same ``requests.Session`` (after an optional warmup GET).
* **Unofficial** — ``GET /state`` (Bearer same as Automation) is used only as
  an optional fallback to discover the connected display resolution.

If TinyPilot (or its reverse proxy) requires HTTP Basic authentication, pass
``http_basic=(username, password)`` so every request on the session carries
those credentials.

TLS note: TinyPilot devices typically present a self-signed certificate, so
this client sets ``session.verify = False`` and silences the corresponding
urllib3 warning. The alpha is local-network only; see ``README.md`` for the
security tradeoff. Do not reuse this client for non-TinyPilot hosts.
"""

import re
from typing import Any
from typing import Optional
from typing import Tuple

import requests
import urllib3

# TinyPilot ships with a self-signed TLS certificate, so we cannot verify it
# from the dashboard host. Silence the per-request InsecureRequestWarning that
# urllib3 would otherwise log on every call. This is intentional and scoped to
# the dashboard's TinyPilot client only; see module docstring.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TinyPilotClient:
    """Thin HTTP client for a single TinyPilot device."""

    def __init__(
        self,
        base_url: str,
        *,
        http_basic: Optional[Tuple[str, str]] = None,
    ):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.pop('Origin', None)
        # TinyPilot self-signed certs: see module docstring.
        self.session.verify = False
        if http_basic is not None:
            self.session.auth = http_basic

    def refresh_automation_token(self) -> str:
        response = self.session.post(
            f'{self.base_url}/api/v1/auth',
            timeout=10,
        )
        response.raise_for_status()
        return response.json()['token']

    def refresh_csrf_token(self) -> str:
        response = self.session.get(self.base_url, timeout=10)
        response.raise_for_status()
        csrf_match = re.search(
            r'<meta\s+name="csrf-token"\s+content="([^"]+)"\s*/?>',
            response.text,
        )
        if csrf_match:
            return csrf_match.group(1)
        if self.session.cookies.get('session'):
            # Some TinyPilot versions expose session + CSRF server-side without a meta tag.
            return 'session-cookie'
        raise ValueError('csrf-token meta tag not found')

    def get_network_status(self):
        warmup = self.session.get(self.base_url, timeout=10)
        warmup.raise_for_status()
        response = self.session.get(f'{self.base_url}/api/network/status', timeout=10)
        response.raise_for_status()
        return response.json()

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

    def _get_json(self, path: str) -> dict[str, Any]:
        warmup = self.session.get(self.base_url, timeout=10)
        warmup.raise_for_status()
        response = self.session.get(f'{self.base_url}{path}', timeout=10)
        if response.status_code in (401, 403):
            # Automatically recover from stale session/csrf by reloading the WebUI token once.
            self.refresh_csrf_token()
            response = self.session.get(f'{self.base_url}{path}', timeout=10)
        self._raise_for_status(response)
        return response.json()

    def _put_json(
        self,
        path: str,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Send a PUT request with CSRF header. Retries once on 401/403."""
        warmup = self.session.get(self.base_url, timeout=10)
        warmup.raise_for_status()
        csrf_token = None
        csrf_match = re.search(
            r'<meta\s+name="csrf-token"\s+content="([^"]+)"\s*/?>',
            warmup.text,
        )
        if csrf_match:
            csrf_token = csrf_match.group(1)
        headers = {'X-CSRFToken': csrf_token} if csrf_token else {}
        response = self.session.put(
            f'{self.base_url}{path}',
            json=body,
            params=params,
            headers=headers,
            timeout=30,
        )
        if response.status_code in (401, 403):
            new_csrf = self.refresh_csrf_token()
            retry_headers = (
                {'X-CSRFToken': new_csrf}
                if new_csrf and new_csrf != 'session-cookie'
                else {}
            )
            response = self.session.put(
                f'{self.base_url}{path}',
                json=body,
                params=params,
                headers=retry_headers,
                timeout=30,
            )
        self._raise_for_status(response)
        return response.json() if response.content else {}

    def get_mass_storage(self) -> dict[str, Any]:
        """Return backing files, intermediate files, and current mount mode."""
        return self._get_json('/api/massStorage/backingFiles')

    def get_mass_storage_filename_from_url(self, url: str) -> str:
        """Resolve or generate a backing file name from a download URL."""
        warmup = self.session.get(self.base_url, timeout=10)
        warmup.raise_for_status()
        response = self.session.get(
            f'{self.base_url}/api/massStorage/retrieveFileNameFromUrl',
            params={'url': url},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()['fileName']

    def fetch_mass_storage_from_url(self, filename: str, url: str) -> None:
        """Tell the device to download an image from a URL and store it as `filename`."""
        self._put_json(
            f'/api/massStorage/backingFiles/{filename}/fetchFromUrl',
            body={'url': url},
        )

    def mount_mass_storage(self, filename: str, mode: str) -> None:
        """Mount `filename` in the given mode (CDROM, FLASH_READ_ONLY, FLASH_READ_WRITE)."""
        self._put_json(
            f'/api/massStorage/mount/{filename}',
            params={'mode': mode},
        )

    def eject_mass_storage(self) -> None:
        """Eject the currently mounted image."""
        self._put_json('/api/massStorage/eject')

    def get_status(self) -> dict[str, Any]:
        return self._get_json('/api/status')

    def get_auth_status(self) -> dict[str, Any]:
        return self._get_json('/api/auth')

    def get_version(self) -> dict[str, Any]:
        return self._get_json('/api/version')

    def get_requires_https(self) -> dict[str, Any]:
        return self._get_json('/api/settings/requiresHttps')

    def get_video_settings(self) -> dict[str, Any]:
        return self._get_json('/api/settings/video')

    def get_screenshot(self, automation_token: str) -> bytes:
        response = self.session.get(
            f'{self.base_url}/api/v1/screenshot',
            headers={'Authorization': f'Bearer {automation_token}'},
            timeout=15,
        )
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            raise ValueError(
                'TinyPilot returned no screenshot image (HTTP 204 or empty body); '
                'often means no video signal from the target.',
            )
        return response.content

    def get_automation_state(self, automation_token: str) -> dict[str, Any]:
        """Unofficial Automation API: connected display resolution via result.source.resolution."""
        response = self.session.get(
            f'{self.base_url}/state',
            headers={'Authorization': f'Bearer {automation_token}'},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

