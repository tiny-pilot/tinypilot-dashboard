import { escapeHtml, formatRelativeTime } from '../lib/strings.js';
import { formatExpandedSnapshot } from '../lib/snapshot-view.js';
import {
  latestVersionFrom,
  licenseReason,
  licenseStatusFrom,
  updateBannerKind,
} from '../lib/device-update.js';

const AUTOMATION_LICENSE_INFO_URL = 'https://tinypilotkvm.com/pages/automation';
const UPDATE_POLL_INTERVAL_MS = 3000;

function formatCollapsedSnapshotSummary(c) {
  const checkedAt = c.last_checked || '';
  const checkedText = formatRelativeTime(checkedAt);
  return `
        <div class="status-line">
          <span class="status-dot ${c.online ? 'is-connected' : 'is-disconnected'}"></span>
          <span class="status-label">${c.online ? 'Connected' : 'Disconnected'}</span>
          <span class="status-meta">v${escapeHtml(c.software_version || 'unknown')} · Last checked <span class="status-checked-at" data-checked-at="${escapeHtml(checkedAt)}">${escapeHtml(checkedText)}</span></span>
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
    this._updatePollTimer = null;
    this._desiredUpdateVersion = null;
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

  disconnectedCallback() {
    this._stopUpdatePoll();
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
      updateBanner: this.querySelector(`#device-update-banner-${id}`),
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
        <section class="device-section connected-system">
          <div class="connected-system-header">
            <h3 class="connected-system-summary__heading">Target system</h3>
            <p class="section-note-automation">
              <a class="section-note-automation-link" href="${AUTOMATION_LICENSE_INFO_URL}" target="_blank" rel="noopener noreferrer">Requires Automation License</a>
            </p>
          </div>
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
              <label class="inline-interval-label" for="screenshot-interval-${id}">Auto-refresh (min, 0 = off)</label>
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
        </section>
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
          <div id="device-update-banner-${id}" class="device-update-banner" hidden></div>
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
    if (metricsOutput) {
      if (snapshot.error) {
        metricsOutput.textContent = snapshot.error;
      } else {
        metricsOutput.innerHTML = formatExpandedSnapshot(snapshot);
      }
    }
    if (!snapshot.error) {
      this._renderUpdateBanner(snapshot);
    }
  }

  _stopUpdatePoll() {
    if (this._updatePollTimer) {
      window.clearInterval(this._updatePollTimer);
      this._updatePollTimer = null;
    }
  }

  _renderUpdateBanner(snapshot) {
    const banner = this._elements.updateBanner;
    if (!banner || !this._device) {
      return;
    }
    const id = this._device.id;
    const currentVersion = snapshot.collapsed?.software_version || '';
    const softwareUpdate = snapshot.expanded?.software_update || null;
    const kind = updateBannerKind(softwareUpdate, currentVersion);
    const latestVersion = latestVersionFrom(softwareUpdate);
    const licenseStatus = licenseStatusFrom(softwareUpdate);
    const jobError = softwareUpdate?.job?.updateError;

    if (!kind || kind === 'hidden') {
      banner.hidden = true;
      banner.innerHTML = '';
      this._stopUpdatePoll();
      return;
    }

    banner.hidden = false;
    if (kind === 'updating') {
      banner.innerHTML = `
        <p class="device-update-banner__text">
          Updating TinyPilot${latestVersion ? ` to ${escapeHtml(latestVersion)}` : ''}…
          ${jobError ? `<span class="device-update-banner__error">${escapeHtml(jobError)}</span>` : ''}
        </p>
      `;
      this._startUpdatePoll();
      return;
    }
    if (kind === 'error') {
      banner.innerHTML = `
        <p class="device-update-banner__text">
          Could not check for updates:
          ${escapeHtml(softwareUpdate.latest_error || 'unknown error')}
        </p>
      `;
      this._stopUpdatePoll();
      return;
    }
    if (kind === 'license-blocked') {
      banner.innerHTML = `
        <p class="device-update-banner__text">
          Update available (${escapeHtml(currentVersion)} → ${escapeHtml(latestVersion)}),
          but ${escapeHtml(licenseReason(licenseStatus))}.
          <a class="launch-link" href="${escapeHtml(this._device.base_url)}" target="_blank" rel="noopener noreferrer">Attach license in WebUI ↗</a>
        </p>
      `;
      this._stopUpdatePoll();
      return;
    }
    // available
    this._desiredUpdateVersion = latestVersion;
    banner.innerHTML = `
      <p class="device-update-banner__text">
        Update available: ${escapeHtml(currentVersion)} → ${escapeHtml(latestVersion)}
      </p>
      <div class="device-update-banner__actions">
        <button type="button" data-action="start-device-update" data-device-id="${id}">Update</button>
      </div>
    `;
    this._stopUpdatePoll();
  }

  _startUpdatePoll() {
    if (this._updatePollTimer || !this._device) {
      return;
    }
    const id = this._device.id;
    this._updatePollTimer = window.setInterval(async () => {
      const status = await window.dashboardApi.getJson(`/api/devices/${id}/device/update`);
      if (status.error) {
        return;
      }
      if (status.status === 'IN_PROGRESS') {
        const banner = this._elements.updateBanner;
        if (banner && !banner.hidden) {
          const err = status.updateError
            ? `<span class="device-update-banner__error">${escapeHtml(status.updateError)}</span>`
            : '';
          banner.innerHTML = `
            <p class="device-update-banner__text">Updating TinyPilot… ${err}</p>
          `;
        }
        return;
      }
      this._stopUpdatePoll();
      await this.refreshSnapshot();
    }, UPDATE_POLL_INTERVAL_MS);
  }

  async startUpdate() {
    if (!this._device || !this._desiredUpdateVersion) {
      return;
    }
    const id = this._device.id;
    const banner = this._elements.updateBanner;
    if (banner) {
      banner.hidden = false;
      banner.innerHTML = `<p class="device-update-banner__text">Starting update…</p>`;
    }
    const result = await window.dashboardApi.putJson(`/api/devices/${id}/device/update`, {
      version: this._desiredUpdateVersion,
    });
    if (result.error) {
      if (banner) {
        banner.innerHTML = `
          <p class="device-update-banner__text device-update-banner__error">
            ${escapeHtml(result.error)}
          </p>
        `;
      }
      return;
    }
    this._startUpdatePoll();
  }

}

customElements.define('device-card', DeviceCard);
