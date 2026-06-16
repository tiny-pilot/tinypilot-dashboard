# TinyPilot Dashboard v0.1.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Virtual Media section to each device card (mount/eject/fetch-from-URL) and fix screenshot flicker by holding the last frame until the new one is pixel-ready.

**Architecture:** Virtual media is a new collapsible `<details>` section in `device-card.js`, peer to "Connected System". Backend adds four new proxy routes in `api.py` that delegate to five new methods on `TinyPilotClient`. The flicker fix is a pure JS change: pre-load new screenshots into a temporary `Image` object before swapping `<img src>`. A cleanup task fixes a network-mapping bug and removes dead code.

**Tech Stack:** Python/Flask (backend routes), `requests` (TinyPilot HTTP client), vanilla ES modules + web components (frontend), SQLite (unchanged — no schema changes needed).

**Working directory:** `/Users/shalver/Downloads/tinypilot-dashboard/.worktrees/poc-dashboard`

**Run tests with:** `pytest -q` (from working directory)

---

## Task 1: Fix screenshot flicker

**Files:**
- Modify: `app/static/js/components/device-card.js` (lines 144–207)

The flicker is caused by `screenshot.removeAttribute('src')` at line 154, which blanks the image before the new one loads. The fix pre-loads the new image into an off-screen `Image` object and only swaps `screenshot.src` once the new image is ready.

- [ ] **Step 1: Replace `refreshScreenshot` with the flicker-free version**

Open `app/static/js/components/device-card.js` and replace the entire `refreshScreenshot` method (lines 144–207) with:

```js
async refreshScreenshot(capturedAtByDevice) {
  if (!this._device) {
    return;
  }
  const id = this._device.id;
  const { screenshot, link, connectedStatus } = this._elements;

  // Do NOT clear screenshot.src here — keep showing the current frame
  // until the replacement is ready to avoid a visible blank state.
  deactivateScreenshotLink(link);

  const result = await window.dashboardApi.postJson(`/api/devices/${id}/refresh-screenshot`);

  if (connectedStatus) {
    if (result.error) {
      connectedStatus.textContent = `Screenshot failed: ${result.error}`;
    } else {
      capturedAtByDevice.set(String(id), result.captured_at || new Date().toISOString());
      connectedStatus.textContent = `Screenshot refreshed ${formatRelativeTime(result.captured_at)}.`;
    }
  }

  if (result.error || !screenshot) {
    return;
  }

  const busted = `/api/devices/${id}/latest-screenshot?t=${Date.now()}`;

  const activateScreenshotLink = () => {
    if (!link) {
      return;
    }
    link.classList.add('connected-screenshot-link--available');
    link.setAttribute('tabindex', '0');
    link.removeAttribute('aria-disabled');
    link.href = busted;
  };

  // Pre-load into an off-screen Image. Only swap the displayed <img> src
  // after the browser has fully decoded the new frame so it never goes blank.
  const preload = new Image();
  preload.onload = () => {
    screenshot.src = busted;
    activateScreenshotLink();
    if (connectedStatus) {
      connectedStatus.textContent = `Screenshot refreshed ${formatRelativeTime(result.captured_at)}.`;
    }
  };
  preload.onerror = () => {
    // Keep the current screenshot; show a status note.
    if (connectedStatus) {
      connectedStatus.textContent = 'Screenshot failed to load (image error).';
    }
    deactivateScreenshotLink(link);
  };
  preload.src = busted;

  // If already cached, onload may have fired synchronously — handle that case.
  if (preload.complete && preload.naturalWidth > 0 && screenshot.src !== busted) {
    screenshot.src = busted;
    activateScreenshotLink();
  }
}
```

- [ ] **Step 2: Verify tests still pass**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add app/static/js/components/device-card.js
git commit -m "Fix screenshot flicker by pre-loading before swapping src"
```

---

## Task 2: TinyPilotClient — virtual media methods

**Files:**
- Modify: `app/tinypilot_client.py`
- Create: `tests/test_tinypilot_client.py`

Add five new methods to `TinyPilotClient` and a `_put_json` helper. All mass storage endpoints are Web UI session-based (ADMIN role). For the alpha (no Web UI passwords), CSRF tokens may not be strictly enforced, but we include a CSRF header as best practice.

- [ ] **Step 1: Write failing tests**

Create `tests/test_tinypilot_client.py`:

```python
"""Unit tests for TinyPilotClient virtual media methods."""

from unittest.mock import MagicMock, patch

import pytest

from app.tinypilot_client import TinyPilotClient


@pytest.fixture
def client():
    return TinyPilotClient('https://device.local')


def _mock_session(client, responses):
    """Attach a mock session that returns `responses` in order."""
    mock_session = MagicMock()
    mock_session.get.return_value = responses[0] if len(responses) == 1 else MagicMock(
        raise_for_status=MagicMock(),
        text='<html></html>',
        status_code=200,
    )
    mock_session.put.return_value = responses[-1]
    client.session = mock_session
    return mock_session


def make_response(json_data=None, status_code=200, content=b''):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_data or {}
    r.content = content
    r.raise_for_status = MagicMock()
    return r


def test_get_mass_storage_returns_backing_files_and_mount_mode(client):
    warmup = make_response()
    warmup.text = '<html></html>'
    api_response = make_response({
        'backingFiles': [{'name': 'ubuntu.iso', 'isMounted': True, 'loadedBytes': 1000, 'totalBytes': 1000}],
        'intermediateFiles': [],
        'mountMode': 'CDROM',
    })
    mock_session = MagicMock()
    mock_session.get.side_effect = [warmup, api_response]
    client.session = mock_session

    result = client.get_mass_storage()

    assert result['mountMode'] == 'CDROM'
    assert result['backingFiles'][0]['name'] == 'ubuntu.iso'


def test_get_mass_storage_filename_from_url_returns_filename(client):
    warmup = make_response()
    warmup.text = '<html></html>'
    api_response = make_response({'fileName': 'ubuntu-24.04.iso'})
    mock_session = MagicMock()
    mock_session.get.side_effect = [warmup, api_response]
    client.session = mock_session

    result = client.get_mass_storage_filename_from_url('https://example.com/ubuntu.iso')

    assert result == 'ubuntu-24.04.iso'


def test_mount_mass_storage_sends_correct_path_and_mode(client):
    warmup = make_response()
    warmup.text = '<html></html>'
    put_response = make_response({'success': True})
    mock_session = MagicMock()
    mock_session.get.return_value = warmup
    mock_session.put.return_value = put_response
    client.session = mock_session

    client.mount_mass_storage('ubuntu.iso', 'CDROM')

    call_args = mock_session.put.call_args
    assert 'massStorage/mount/ubuntu.iso' in call_args[0][0]
    assert call_args[1]['params']['mode'] == 'CDROM'


def test_eject_mass_storage_calls_eject_endpoint(client):
    warmup = make_response()
    warmup.text = '<html></html>'
    put_response = make_response()
    put_response.content = b''
    mock_session = MagicMock()
    mock_session.get.return_value = warmup
    mock_session.put.return_value = put_response
    client.session = mock_session

    client.eject_mass_storage()

    call_args = mock_session.put.call_args
    assert 'massStorage/eject' in call_args[0][0]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_tinypilot_client.py -v
```

Expected: `AttributeError: 'TinyPilotClient' object has no attribute 'get_mass_storage'` (or similar).

- [ ] **Step 3: Add `_put_json` helper and five new methods to `TinyPilotClient`**

In `app/tinypilot_client.py`, add after `_get_json` (after line 92):

```python
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
        self.refresh_csrf_token()
        response = self.session.put(
            f'{self.base_url}{path}',
            json=body,
            params=params,
            headers=headers,
            timeout=30,
        )
    response.raise_for_status()
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_tinypilot_client.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Run full test suite to confirm nothing regressed**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/tinypilot_client.py tests/test_tinypilot_client.py
git commit -m "Add virtual media methods to TinyPilotClient"
```

---

## Task 3: Dashboard backend — virtual media routes

**Files:**
- Modify: `app/api.py`
- Modify: `tests/test_api_connections.py`

Add four new routes: `GET /media`, `POST /media/fetch`, `PUT /media/mount`, `PUT /media/eject`. All use the same device-lookup + client pattern already established in `api.py`.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api_connections.py`:

```python
def _create_device(client, base_url='https://192.168.1.200'):
    """Helper: create a device with no automation token."""
    with patch('app.api.TinyPilotClient') as cls:
        cls.return_value.refresh_automation_token.side_effect = RuntimeError('no device')
        resp = client.post('/api/devices', json={
            'friendly_name': 'Media Test Device',
            'base_url': base_url,
        })
    return resp.json['device']['id']


def test_get_media_returns_backing_files(client):
    device_id = _create_device(client)
    backing_files_response = {
        'backingFiles': [{'name': 'ubuntu.iso', 'isMounted': True, 'loadedBytes': 100, 'totalBytes': 100}],
        'intermediateFiles': [],
        'mountMode': 'CDROM',
    }
    with patch('app.api.TinyPilotClient') as cls:
        cls.return_value.get_mass_storage.return_value = backing_files_response
        response = client.get(f'/api/devices/{device_id}/media')

    assert response.status_code == 200
    assert response.json['backingFiles'][0]['name'] == 'ubuntu.iso'
    assert response.json['mountMode'] == 'CDROM'


def test_get_media_returns_404_for_unknown_device(client):
    response = client.get('/api/devices/9999/media')
    assert response.status_code == 404


def test_media_fetch_triggers_device_download(client):
    device_id = _create_device(client)
    with patch('app.api.TinyPilotClient') as cls:
        cls.return_value.get_mass_storage_filename_from_url.return_value = 'ubuntu.iso'
        cls.return_value.fetch_mass_storage_from_url.return_value = None
        response = client.post(
            f'/api/devices/{device_id}/media/fetch',
            json={'url': 'https://example.com/ubuntu.iso'},
        )

    assert response.status_code == 200
    assert response.json['fileName'] == 'ubuntu.iso'


def test_media_fetch_returns_400_without_url(client):
    device_id = _create_device(client)
    response = client.post(f'/api/devices/{device_id}/media/fetch', json={})
    assert response.status_code == 400


def test_media_mount_calls_device(client):
    device_id = _create_device(client)
    with patch('app.api.TinyPilotClient') as cls:
        cls.return_value.mount_mass_storage.return_value = None
        response = client.put(
            f'/api/devices/{device_id}/media/mount',
            json={'fileName': 'ubuntu.iso', 'mode': 'CDROM'},
        )

    assert response.status_code == 200
    cls.return_value.mount_mass_storage.assert_called_once_with('ubuntu.iso', 'CDROM')


def test_media_mount_returns_400_without_required_fields(client):
    device_id = _create_device(client)
    response = client.put(f'/api/devices/{device_id}/media/mount', json={'fileName': 'ubuntu.iso'})
    assert response.status_code == 400


def test_media_eject_calls_device(client):
    device_id = _create_device(client)
    with patch('app.api.TinyPilotClient') as cls:
        cls.return_value.eject_mass_storage.return_value = None
        response = client.put(f'/api/devices/{device_id}/media/eject')

    assert response.status_code == 200
    cls.return_value.eject_mass_storage.assert_called_once()
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
pytest tests/test_api_connections.py -k "media" -v
```

Expected: `404 NOT FOUND` on all (routes don't exist yet).

- [ ] **Step 3: Add four new routes to `app/api.py`**

Append to `app/api.py` (before the final newline):

```python
@api_blueprint.get('/devices/<int:device_id>/media')
def get_device_media(device_id: int):
    """Return current virtual media state (backing files + mount mode) for a device."""
    row = _device_row_with_web_auth(device_id)
    if row is None:
        return jsonify({'error': 'device not found'}), 404
    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    http_basic = _http_basic_from_auth_row(key_path, row)
    client = TinyPilotClient(row['base_url'], http_basic=http_basic)
    try:
        result = client.get_mass_storage()
    except Exception as err:  # pylint: disable=broad-exception-caught
        return jsonify({'error': f'failed to fetch media state: {err}'}), 502
    return jsonify(result)


@api_blueprint.post('/devices/<int:device_id>/media/fetch')
def fetch_device_media_from_url(device_id: int):
    """Tell the device to download an image from a URL."""
    row = _device_row_with_web_auth(device_id)
    if row is None:
        return jsonify({'error': 'device not found'}), 404
    payload = request.get_json(silent=True) or {}
    url = (payload.get('url') or '').strip()
    if not url:
        return jsonify({'error': 'url is required'}), 400
    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    http_basic = _http_basic_from_auth_row(key_path, row)
    client = TinyPilotClient(row['base_url'], http_basic=http_basic)
    try:
        file_name = client.get_mass_storage_filename_from_url(url)
        client.fetch_mass_storage_from_url(file_name, url)
    except Exception as err:  # pylint: disable=broad-exception-caught
        return jsonify({'error': f'failed to fetch image from URL: {err}'}), 502
    return jsonify({'device_id': device_id, 'fileName': file_name})


@api_blueprint.put('/devices/<int:device_id>/media/mount')
def mount_device_media(device_id: int):
    """Mount a backing file on the device."""
    row = _device_row_with_web_auth(device_id)
    if row is None:
        return jsonify({'error': 'device not found'}), 404
    payload = request.get_json(silent=True) or {}
    file_name = (payload.get('fileName') or '').strip()
    mode = (payload.get('mode') or '').strip()
    if not file_name or not mode:
        return jsonify({'error': 'fileName and mode are required'}), 400
    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    http_basic = _http_basic_from_auth_row(key_path, row)
    client = TinyPilotClient(row['base_url'], http_basic=http_basic)
    try:
        client.mount_mass_storage(file_name, mode)
    except Exception as err:  # pylint: disable=broad-exception-caught
        return jsonify({'error': f'failed to mount image: {err}'}), 502
    return jsonify({'device_id': device_id, 'mounted': True, 'fileName': file_name, 'mode': mode})


@api_blueprint.put('/devices/<int:device_id>/media/eject')
def eject_device_media(device_id: int):
    """Eject the currently mounted image on the device."""
    row = _device_row_with_web_auth(device_id)
    if row is None:
        return jsonify({'error': 'device not found'}), 404
    key_path = Path(current_app.config['SECRET_KEY_PATH'])
    http_basic = _http_basic_from_auth_row(key_path, row)
    client = TinyPilotClient(row['base_url'], http_basic=http_basic)
    try:
        client.eject_mass_storage()
    except Exception as err:  # pylint: disable=broad-exception-caught
        return jsonify({'error': f'failed to eject media: {err}'}), 502
    return jsonify({'device_id': device_id, 'ejected': True})
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_api_connections.py -k "media" -v
```

Expected: all 8 new tests pass.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/api.py tests/test_api_connections.py
git commit -m "Add virtual media proxy routes to dashboard API"
```

---

## Task 4: Virtual Media frontend section

**Files:**
- Modify: `app/static/js/components/device-card.js`
- Modify: `app/static/css/dashboard.css`
- Modify: `app/templates/index.html` (bump `asset_v`)

Add a collapsible "Virtual media" section below "Connected system" in the device card. Uses the same `<details>` open/close pattern as Connected System.

The section has three UI states:
- **No images:** URL input + "Add image" button + hint to TinyPilot WebUI
- **Images available, nothing mounted:** file `<select>` + mode `<select>` + "Mount" button
- **Mounted:** filename + mode label + "Eject" button (with inline confirmation)

- [ ] **Step 1: Add `_renderVirtualMedia` helper and extend `_cacheElements` in `device-card.js`**

In `_cacheElements`, add `virtualMediaSection` to `this._elements`:

```js
_cacheElements() {
  const id = this._device.id;
  this._elements = {
    screenshot: this.querySelector(`#connected-screenshot-${id}`),
    link: this.querySelector(`#connected-screenshot-link-${id}`),
    connectedStatus: this.querySelector(`#connected-status-${id}`),
    summaryOutput: this.querySelector(`#device-collapsed-summary-${id}`),
    metricsOutput: this.querySelector(`#device-metrics-output-${id}`),
    intervalInput: this.querySelector(`#screenshot-interval-${id}`),
    virtualMediaSection: this.querySelector(`#virtual-media-${id}`),
  };
}
```

Add the `_renderVirtualMedia(mediaState)` method after `refreshSnapshot`:

```js
_renderVirtualMedia(mediaState) {
  const id = this._device.id;
  const section = this._elements.virtualMediaSection;
  if (!section) {
    return;
  }
  const { backingFiles, mountMode } = mediaState;
  const mountedFile = (backingFiles || []).find(f => f.isMounted);
  const allFiles = (backingFiles || []);

  // Update collapsed summary.
  const summary = section.querySelector('.virtual-media-summary-text');
  if (summary) {
    summary.textContent = mountedFile
      ? `${mountedFile.name} · ${_formatMountMode(mountMode)}`
      : 'Not mounted';
  }

  // Render body.
  const body = section.querySelector('.virtual-media-body');
  if (!body) {
    return;
  }
  body.innerHTML = '';

  if (allFiles.length === 0) {
    body.innerHTML = `
      <p class="virtual-media-empty">
        No images on this device.
        <a href="${escapeHtml(this._device.base_url)}" target="_blank" rel="noopener noreferrer">
          Upload via the TinyPilot WebUI
        </a>.
      </p>
      <div class="virtual-media-fetch">
        <input
          id="virtual-media-url-${id}"
          class="virtual-media-url-input"
          type="url"
          placeholder="Paste image URL…"
          autocomplete="off"
        >
        <button type="button" data-action="fetch-media" data-device-id="${id}">Add image</button>
      </div>
      <p id="virtual-media-status-${id}" class="virtual-media-status"></p>
    `;
  } else if (!mountedFile) {
    const options = allFiles
      .map(f => `<option value="${escapeHtml(f.name)}">${escapeHtml(f.name)}</option>`)
      .join('');
    body.innerHTML = `
      <select id="virtual-media-file-${id}" class="virtual-media-select">
        <option value="" disabled selected>Select image…</option>
        ${options}
      </select>
      <select id="virtual-media-mode-${id}" class="virtual-media-select">
        <option value="CDROM">CD-ROM</option>
        <option value="FLASH_READ_ONLY">USB — Read only</option>
        <option value="FLASH_READ_WRITE">USB — Read/write</option>
      </select>
      <div class="virtual-media-actions">
        <button type="button" data-action="mount-media" data-device-id="${id}">Mount</button>
      </div>
      <p id="virtual-media-status-${id}" class="virtual-media-status"></p>
    `;
  } else {
    body.innerHTML = `
      <dl class="virtual-media-info">
        <dt>Mounted</dt>
        <dd>${escapeHtml(mountedFile.name)}</dd>
        <dt>Mode</dt>
        <dd>${escapeHtml(_formatMountMode(mountMode))}</dd>
      </dl>
      <div class="virtual-media-actions" id="virtual-media-eject-area-${id}">
        <button type="button" data-action="eject-media" data-device-id="${id}">Eject</button>
      </div>
      <p id="virtual-media-status-${id}" class="virtual-media-status"></p>
    `;
  }
}
```

Add the module-level helper `_formatMountMode` at the top of `device-card.js` (after the imports):

```js
const _MOUNT_MODE_LABELS = {
  CDROM: 'CD-ROM',
  FLASH_READ_ONLY: 'USB — Read only',
  FLASH_READ_WRITE: 'USB — Read/write',
};

function _formatMountMode(mode) {
  return _MOUNT_MODE_LABELS[mode] || mode || 'Unknown';
}
```

- [ ] **Step 2: Add the Virtual Media HTML to `_render()`**

In `_render()`, after the closing `</details>` of the Connected System section (after line 121), add the new section:

```js
        <details id="virtual-media-${id}" class="device-section virtual-media-details" open>
          <summary class="virtual-media-summary">
            <div class="virtual-media-summary__lead">
              <svg class="virtual-media-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <rect x="1" y="4" width="14" height="9" rx="1.5" stroke="currentColor" stroke-width="1.3"/>
                <circle cx="5" cy="8.5" r="1.2" fill="currentColor"/>
                <rect x="8" y="6.5" width="5" height="1.2" rx="0.6" fill="currentColor"/>
                <rect x="8" y="9.3" width="3" height="1.2" rx="0.6" fill="currentColor"/>
              </svg>
              <h3 class="virtual-media-summary__heading">Virtual media</h3>
              <p class="virtual-media-summary-text">Loading…</p>
            </div>
            <span class="virtual-media-summary__toggle" aria-hidden="true"></span>
          </summary>
          <div class="virtual-media-body"></div>
        </details>
```

- [ ] **Step 3: Add event handlers for virtual media actions**

The `dashboard-app.js` dispatches button click events with `data-action`. Open `app/static/js/dashboard-app.js` and find where `data-action` values are handled. Add cases for the new actions:

In the click handler (look for `refresh-screenshot`, `fetch-device-snapshot`, etc.), add:

```js
case 'fetch-media': {
  const statusEl = document.getElementById(`virtual-media-status-${deviceId}`);
  const urlInput = document.getElementById(`virtual-media-url-${deviceId}`);
  const url = urlInput ? urlInput.value.trim() : '';
  if (!url) {
    if (statusEl) statusEl.textContent = 'Please enter a URL.';
    break;
  }
  if (statusEl) statusEl.textContent = 'Downloading…';
  const result = await window.dashboardApi.postJson(`/api/devices/${deviceId}/media/fetch`, { url });
  if (result.error) {
    if (statusEl) statusEl.textContent = `Failed: ${result.error}`;
  } else {
    const card = this._deviceCards.get(deviceId);
    if (card) await card.refreshMedia();
  }
  break;
}
case 'mount-media': {
  const fileSelect = document.getElementById(`virtual-media-file-${deviceId}`);
  const modeSelect = document.getElementById(`virtual-media-mode-${deviceId}`);
  const statusEl = document.getElementById(`virtual-media-status-${deviceId}`);
  const fileName = fileSelect ? fileSelect.value : '';
  const mode = modeSelect ? modeSelect.value : 'CDROM';
  if (!fileName) {
    if (statusEl) statusEl.textContent = 'Please select an image.';
    break;
  }
  const result = await window.dashboardApi.putJson(`/api/devices/${deviceId}/media/mount`, { fileName, mode });
  if (result.error) {
    if (statusEl) statusEl.textContent = `Mount failed: ${result.error}`;
  } else {
    const card = this._deviceCards.get(deviceId);
    if (card) await card.refreshMedia();
  }
  break;
}
case 'eject-media': {
  const ejectArea = document.getElementById(`virtual-media-eject-area-${deviceId}`);
  if (ejectArea) {
    ejectArea.innerHTML = `
      <span class="virtual-media-confirm-text">Eject this image?</span>
      <button type="button" data-action="eject-media-confirm" data-device-id="${deviceId}">Eject</button>
      <button type="button" data-action="eject-media-cancel" data-device-id="${deviceId}">Cancel</button>
    `;
  }
  break;
}
case 'eject-media-confirm': {
  const statusEl = document.getElementById(`virtual-media-status-${deviceId}`);
  const result = await window.dashboardApi.putJson(`/api/devices/${deviceId}/media/eject`);
  if (result.error) {
    if (statusEl) statusEl.textContent = `Eject failed: ${result.error}`;
  } else {
    const card = this._deviceCards.get(deviceId);
    if (card) await card.refreshMedia();
  }
  break;
}
case 'eject-media-cancel': {
  const card = this._deviceCards.get(deviceId);
  if (card) await card.refreshMedia();
  break;
}
```

- [ ] **Step 4: Add `refreshMedia()` method and `putJson` to the API helper**

In `device-card.js`, add after `refreshSnapshot`:

```js
async refreshMedia() {
  if (!this._device) {
    return;
  }
  const id = this._device.id;
  const result = await window.dashboardApi.getJson(`/api/devices/${id}/media`);
  if (result.error) {
    const section = this._elements.virtualMediaSection;
    if (section) {
      const body = section.querySelector('.virtual-media-body');
      if (body) body.textContent = `Could not reach device: ${result.error}`;
    }
    return;
  }
  this._renderVirtualMedia(result);
}
```

In `app/static/js/api.js`, add a `putJson` method alongside the existing `postJson`:

```js
async putJson(path, body = {}) {
  try {
    const response = await fetch(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return await response.json();
  } catch (err) {
    return { error: String(err) };
  }
}
```

- [ ] **Step 5: Call `refreshMedia()` from the snapshot refresh loop**

In `dashboard-app.js`, wherever `card.refreshSnapshot()` is called, add a follow-up call:

```js
await card.refreshSnapshot();
await card.refreshMedia();
```

- [ ] **Step 6: Add CSS for the new section**

In `app/static/css/dashboard.css`, append:

```css
/* Virtual media section — mirrors .connected-system-* structure */

.virtual-media-details {
  border-top: 1px solid color-mix(in srgb, var(--color-text) 10%, transparent);
  padding-top: var(--space-3);
  margin-top: var(--space-2);
}

.virtual-media-summary {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: start;
  list-style: none;
  cursor: pointer;
  user-select: none;
  padding: 0;
}

.virtual-media-summary::-webkit-details-marker {
  display: none;
}

.virtual-media-summary__lead {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.virtual-media-icon {
  color: var(--color-text-muted, #5a6770);
  margin-bottom: 2px;
}

.virtual-media-summary__heading {
  margin: 0;
  font-size: 1.0625rem;
  line-height: 1.3;
  font-weight: 400;
}

.virtual-media-summary-text {
  margin: 0;
  font-size: 0.82rem;
  color: var(--color-text-muted, #5a6770);
}

.virtual-media-summary__toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 1.5rem;
  font-size: 1.1rem;
  color: var(--color-text-muted, #5a6770);
  padding-top: 0.15em;
}

.virtual-media-details[open] .virtual-media-summary__toggle::after {
  content: '\2212';
}

.virtual-media-details:not([open]) .virtual-media-summary__toggle::after {
  content: '+';
}

.virtual-media-summary:hover .virtual-media-summary__toggle,
.virtual-media-summary:focus-visible .virtual-media-summary__toggle {
  color: var(--color-accent-hover);
}

.virtual-media-body {
  margin-top: var(--space-3);
}

.virtual-media-select {
  display: block;
  width: 100%;
  margin-bottom: var(--space-2);
  font-family: inherit;
  font-size: 0.9rem;
}

.virtual-media-url-input {
  display: block;
  width: 100%;
  margin-bottom: var(--space-2);
  font-family: inherit;
  font-size: 0.9rem;
}

.virtual-media-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
}

.virtual-media-confirm-text {
  font-size: 0.88rem;
  margin-right: auto;
}

.virtual-media-info {
  display: grid;
  grid-template-columns: 5rem 1fr;
  gap: var(--space-1) var(--space-3);
  margin: 0 0 var(--space-3) 0;
  font-size: 0.88rem;
}

.virtual-media-info dt {
  color: var(--color-text-muted, #5a6770);
}

.virtual-media-info dd {
  margin: 0;
  word-break: break-all;
}

.virtual-media-empty {
  font-size: 0.85rem;
  color: var(--color-text-muted, #5a6770);
  margin: 0 0 var(--space-3) 0;
}

.virtual-media-status {
  font-size: 0.82rem;
  color: var(--color-text-muted, #5a6770);
  min-height: 1.2em;
  margin: var(--space-2) 0 0 0;
}
```

- [ ] **Step 7: Bump `asset_v` in the HTML template**

In `app/templates/index.html`, increment `asset_v` (e.g. `20260511-15` → `20260615-01`):

```html
{% set asset_v = '20260615-01' %}
```

- [ ] **Step 8: Run full test suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 9: Smoke-test locally with Docker**

```bash
docker compose up --build --detach
```

Open `http://localhost:8080` and verify:
- The Virtual Media section appears below "Connected system" on each card.
- The `+` / `−` toggle collapses/expands the section.
- Collapsed state shows "Loading…" (before `refreshMedia` runs) then the mount status.

- [ ] **Step 10: Commit**

```bash
git add app/static/js/components/device-card.js \
        app/static/js/dashboard-app.js \
        app/static/js/api.js \
        app/static/css/dashboard.css \
        app/templates/index.html
git commit -m "Add Virtual Media section to device card"
```

---

## Task 5: Cleanup

**Files:**
- Modify: `app/api.py` (remove dead endpoint, fix network mapping)

Two targeted cleanup items touched during this work:

1. **Fix network mapping bug** — `get_device_snapshot` maps `network` as `{'interfaces': network.get('interfaces', [])}` but TinyPilot returns `{ethernet: {...}, wifi: {...}}` — `interfaces` never exists. Fix to pass through the full network object.

2. **Remove dead `get_device_metrics` endpoint** — superseded by the snapshot endpoint; not called by any frontend code.

- [ ] **Step 1: Fix network mapping in `get_device_snapshot`**

In `app/api.py`, find the `expanded` dict construction in `get_device_snapshot` (around line 560). Change:

```python
'network': {'interfaces': (network or {}).get('interfaces', []), 'error': network_error},
```

to:

```python
'network': {'data': network or {}, 'error': network_error},
```

- [ ] **Step 2: Update `snapshot-view.js` to use the new key**

In `app/static/js/lib/snapshot-view.js`, find any reference to `snapshot.expanded.network.interfaces` and update it to read from `snapshot.expanded.network.data` (check for both `ethernet` and `wifi` keys):

```js
// In the network section formatter, replace any .interfaces array walk with:
const networkData = (expanded.network || {}).data || {};
const ethernet = networkData.ethernet;
const wifi = networkData.wifi;
// Render ethernet and wifi directly rather than iterating an interfaces array.
```

- [ ] **Step 3: Remove `get_device_metrics` from `app/api.py`**

Delete the entire `get_device_metrics` function and its route decorator (lines 441–461):

```python
@api_blueprint.get('/devices/<int:device_id>/device/metrics')
def get_device_metrics(device_id: int):
    ...
```

- [ ] **Step 4: Run full test suite**

```bash
pytest -q
```

Expected: all tests pass (no test references `get_device_metrics`).

- [ ] **Step 5: Commit**

```bash
git add app/api.py app/static/js/lib/snapshot-view.js
git commit -m "Fix network mapping in snapshot and remove dead metrics endpoint"
```
