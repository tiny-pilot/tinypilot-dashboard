import { escapeHtml, formatRelativeTime } from '../lib/strings.js';
import { formatExpandedSnapshot } from '../lib/snapshot-view.js';

const AUTOMATION_LICENSE_INFO_URL = 'https://tinypilotkvm.com/pages/automation';

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

    if (screenshot) {
      screenshot.onload = null;
      screenshot.onerror = null;
      screenshot.removeAttribute('src');
    }
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

    screenshot.onload = () => {
      activateScreenshotLink();
    };

    screenshot.onerror = () => {
      screenshot.onerror = null;
      screenshot.onload = null;
      screenshot.removeAttribute('src');
      if (connectedStatus) {
        connectedStatus.textContent = 'Screenshot failed to load (image error).';
      }
      deactivateScreenshotLink(link);
    };

    screenshot.src = busted;
    if (link) {
      link.href = busted;
    }

    if (screenshot.complete && screenshot.naturalWidth > 0) {
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

}

customElements.define('device-card', DeviceCard);
