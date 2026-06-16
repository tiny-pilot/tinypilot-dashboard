import { escapeHtml, formatRelativeTime } from '../lib/strings.js';
import { formatExpandedSnapshot } from '../lib/snapshot-view.js';

const AUTOMATION_LICENSE_INFO_URL = 'https://tinypilotkvm.com/pages/automation';

const _MOUNT_MODE_LABELS = {
  CDROM: 'CD-ROM',
  FLASH_READ_ONLY: 'USB — Read only',
  FLASH_READ_WRITE: 'USB — Read/write',
};

function _formatMountMode(mode) {
  return _MOUNT_MODE_LABELS[mode] || mode || 'Unknown';
}

function formatCollapsedSnapshotSummary(c) {
  const checkedText = formatRelativeTime(c.last_checked);
  return `
        <div class="status-line">
          <span class="status-dot ${c.online ? 'is-connected' : 'is-disconnected'}"></span>
          <span class="status-label">${c.online ? 'Connected' : 'Disconnected'}</span>
          <span class="status-meta">v${escapeHtml(c.software_version || 'unknown')} · Last checked ${escapeHtml(checkedText)}</span>
        </div>
        <div class="status-url">${escapeHtml(c.device_url || '')}</div>
      `;
}

function deactivateScreenshotLink(link) {
  if (!link) {
    return;
  }
  link.classList.remove('connected-screenshot-link--available');
  link.setAttribute('tabindex', '-1');
  link.setAttribute('aria-disabled', 'true');
}

class DeviceCard extends HTMLElement {
  constructor() {
    super();
    this._device = null;
    this._elements = {};
  }

  set device(value) {
    this._device = value;
    if (this.isConnected && value) {
      this._render();
    }
  }

  get device() {
    return this._device;
  }

  connectedCallback() {
    if (this._device) {
      this._render();
    }
  }

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

  _render() {
    const device = this._device;
    if (!device) {
      return;
    }
    const id = device.id;
    this.className = 'device-wrapper';
    this.innerHTML = `
      <section class="panel device-card">
        <header class="device-card-header">
          <h3 class="device-card-title">${escapeHtml(device.friendly_name)}</h3>
        </header>
        <details class="device-section connected-system connected-system-details" open>
          <summary class="connected-system-summary">
            <div class="connected-system-summary__lead">
              <h3 class="connected-system-summary__heading">Connected system</h3>
              <p class="section-note-automation">
                <a class="section-note-automation-link" href="${AUTOMATION_LICENSE_INFO_URL}" target="_blank" rel="noopener noreferrer">Requires Automation License</a>
              </p>
            </div>
            <span class="connected-system-summary__toggle" aria-hidden="true"></span>
          </summary>
          <div class="connected-system-body">
            <a
              id="connected-screenshot-link-${id}"
              class="connected-screenshot-link"
              href="/api/devices/${id}/latest-screenshot"
              target="_blank"
              rel="noopener noreferrer"
              tabindex="-1"
              aria-disabled="true"
              aria-label="Open latest screenshot in new tab"
            >
              <img
                id="connected-screenshot-${id}"
                class="connected-screenshot"
                alt="Latest screenshot for ${escapeHtml(device.friendly_name)}"
              >
            </a>
            <div class="actions actions-connected-primary">
              <button type="button" data-action="refresh-screenshot" data-device-id="${id}">Refresh screenshot</button>
            </div>
            <div class="actions actions-auto-refresh-row">
              <label class="inline-interval-label" for="screenshot-interval-${id}">Auto-refresh (min)</label>
              <input
                id="screenshot-interval-${id}"
                class="interval-input interval-input--two-digit"
                type="number"
                min="0"
                max="120"
                step="1"
                inputmode="numeric"
                value="${device.screenshot_refresh_interval_minutes || 0}"
              >
              <button type="button" data-action="save-screenshot-interval" data-device-id="${id}">Save</button>
            </div>
            <p id="connected-status-${id}" class="subtitle"></p>
          </div>
        </details>
        <details id="virtual-media-${id}" class="device-section virtual-media-details" open>
          <summary class="virtual-media-summary">
            <div class="virtual-media-summary__lead">
              <h3 class="virtual-media-summary__heading">Virtual media</h3>
              <p class="virtual-media-summary-text">Loading…</p>
            </div>
            <span class="virtual-media-summary__toggle" aria-hidden="true"></span>
          </summary>
          <div class="virtual-media-body"></div>
        </details>
        <section class="device-section tiny-device">
          <h3>TinyPilot device</h3>
          <p>
            <a class="launch-link" href="${escapeHtml(device.base_url)}" target="_blank" rel="noopener noreferrer">Launch WebUI ↗</a>
          </p>
          <div class="actions">
            <button type="button" data-action="fetch-device-snapshot" data-device-id="${id}">Refresh device snapshot</button>
            <button type="button" data-action="delete-device" data-device-id="${id}">Delete device</button>
          </div>
          <div id="device-collapsed-summary-${id}" class="metrics-output">
            Retrieving device snapshot...
          </div>
          <details class="device-details">
            <summary>Expanded TinyPilot device info</summary>
            <div id="device-metrics-output-${id}" class="metrics-output">Retrieving expanded device info...</div>
          </details>
        </section>
      </section>
    `;
    this._cacheElements();
  }

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

  async refreshSnapshot() {
    if (!this._device) {
      return;
    }
    const id = this._device.id;
    const { summaryOutput, metricsOutput } = this._elements;
    const snapshot = await window.dashboardApi.getJson(`/api/devices/${id}/device/snapshot`);

    if (summaryOutput) {
      if (snapshot.error) {
        summaryOutput.textContent = snapshot.error;
      } else {
        summaryOutput.innerHTML = formatCollapsedSnapshotSummary(snapshot.collapsed);
      }
    }
    if (!metricsOutput) {
      return;
    }
    if (snapshot.error) {
      metricsOutput.textContent = snapshot.error;
      return;
    }
    metricsOutput.innerHTML = formatExpandedSnapshot(snapshot);
  }

  _renderVirtualMedia(mediaState) {
    const id = this._device.id;
    const section = this._elements.virtualMediaSection;
    if (!section) {
      return;
    }
    const backingFiles = mediaState.backingFiles || [];
    const mountMode = mediaState.mountMode || '';
    const mountedFile = backingFiles.find(f => f.mounted) || null;

    const summaryText = section.querySelector('.virtual-media-summary-text');
    if (summaryText) {
      summaryText.textContent = mountedFile
        ? `${mountedFile.name} · ${_formatMountMode(mountMode)}`
        : 'Not mounted';
    }

    const body = section.querySelector('.virtual-media-body');
    if (!body) {
      return;
    }
    body.innerHTML = '';

    if (backingFiles.length === 0) {
      body.innerHTML = `
        <div class="virtual-media-fetch">
          <input
            id="virtual-media-url-${id}"
            class="virtual-media-url-input"
            type="url"
            placeholder="Paste image URL…"
            autocomplete="off"
          >
          <div class="virtual-media-actions">
            <button type="button" data-action="fetch-media" data-device-id="${id}">Add image</button>
          </div>
        </div>
        <p class="virtual-media-hint">
          Or <a href="${escapeHtml(this._device.base_url)}" target="_blank" rel="noopener noreferrer">upload via the TinyPilot WebUI ↗</a>
        </p>
        <p id="virtual-media-status-${id}" class="virtual-media-status"></p>
      `;
    } else if (!mountedFile) {
      const options = backingFiles
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
        <div id="virtual-media-eject-area-${id}" class="virtual-media-actions">
          <button type="button" data-action="eject-media" data-device-id="${id}">Eject</button>
        </div>
        <p id="virtual-media-status-${id}" class="virtual-media-status"></p>
      `;
    }
  }

  async refreshMedia() {
    if (!this._device) {
      return;
    }
    const id = this._device.id;
    const result = await window.dashboardApi.getJson(`/api/devices/${id}/media`);
    const section = this._elements.virtualMediaSection;
    if (result.error) {
      if (section) {
        const body = section.querySelector('.virtual-media-body');
        if (body) {
          body.textContent = `Could not reach device: ${result.error}`;
        }
      }
      return;
    }
    this._renderVirtualMedia(result);
  }

}

customElements.define('device-card', DeviceCard);
