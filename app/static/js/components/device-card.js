import { escapeHtml, formatRelativeTime } from '../lib/strings.js';
import { formatExpandedSnapshot } from '../lib/snapshot-view.js';
import {
  latestVersionFrom,
  updateBannerKind,
} from '../lib/device-update.js';

const AUTOMATION_LICENSE_INFO_URL = 'https://tinypilotkvm.com/pages/automation';
const UPDATE_POLL_INTERVAL_MS = 3000;
const UPDATE_POLL_MAX_ERRORS = 10;

function formatCollapsedSnapshotSummary(c) {
  const checkedAt = c.last_checked || '';
  const checkedText = formatRelativeTime(checkedAt);
  const label = c.online ? 'Connected' : 'Could not reach this TinyPilot';
  return `
        <div class="status-line">
          <span class="status-dot ${c.online ? 'is-connected' : 'is-disconnected'}"></span>
          <span class="status-copy"><span class="status-label">${label}</span><span class="status-meta">, last checked <span class="status-checked-at" data-checked-at="${escapeHtml(checkedAt)}">${escapeHtml(checkedText)}</span>.</span></span>
        </div>
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

function activateScreenshotLink(link) {
  if (!link) {
    return;
  }
  link.classList.add('connected-screenshot-link--available');
  link.setAttribute('tabindex', '0');
  link.removeAttribute('aria-disabled');
}

function deviceLaunchHref(device) {
  return String(device.base_url || '').trim();
}

function cachedPreviewCopy(capturedAt) {
  return `Cached preview from ${formatRelativeTime(capturedAt)}.`;
}

function missingPreviewCopy() {
  return 'Could not capture a screenshot.';
}

function setPreviewStatus(el, text, kind) {
  if (!el) {
    return;
  }
  el.textContent = text;
  el.classList.toggle(
    'connected-status--caution',
    kind === 'cached' || kind === 'error',
  );
  if (kind) {
    el.dataset.previewKind = kind;
  } else {
    delete el.dataset.previewKind;
  }
}

function renderHeaderOpenWebUi(device) {
  const url = deviceLaunchHref(device);
  if (!url) {
    return '';
  }
  return (
    `<a class="header-open-webui" href="${escapeHtml(url)}" ` +
    `target="_blank" rel="noopener noreferrer">Open WebUI</a>`
  );
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

  get desiredUpdateVersion() {
    return this._desiredUpdateVersion;
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
      expandedDetails: this.querySelector(`#device-details-${id}`),
    };
  }

  _render() {
    const device = this._device;
    if (!device) {
      return;
    }
    const id = device.id;
    const launchHref = deviceLaunchHref(device);
    this.className = 'device-wrapper';
    this.innerHTML = `
      <section class="panel device-card">
        <header class="device-card-header">
          <h3 class="device-card-title">${escapeHtml(device.friendly_name)}</h3>
          ${renderHeaderOpenWebUi(device)}
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
              href="${escapeHtml(launchHref) || '#'}"
              target="_blank"
              rel="noopener noreferrer"
              tabindex="-1"
              aria-disabled="true"
              aria-label="Control ${escapeHtml(device.friendly_name)}"
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
          <div class="tiny-device-header">
            <h3 class="connected-system-summary__heading">TinyPilot device</h3>
          </div>
          <div class="tiny-device-body">
            <div class="actions">
              <button type="button" data-action="fetch-device-snapshot" data-device-id="${id}">Refresh device snapshot</button>
              <button type="button" data-action="delete-device" data-device-id="${id}">Remove device</button>
            </div>
            <div id="device-collapsed-summary-${id}" class="metrics-output">
              Retrieving device snapshot...
            </div>
            <details id="device-details-${id}" class="device-details" hidden>
              <summary>Expanded TinyPilot device info</summary>
              <div id="device-metrics-output-${id}" class="metrics-output"></div>
            </details>
          </div>
        </section>
      </section>
    `;
    this._cacheElements();
    this._primeCachedScreenshot();
  }

  _primeCachedScreenshot() {
    const device = this._device;
    if (!device?.latest_screenshot_captured_at) {
      return;
    }
    const { screenshot, link, connectedStatus } = this._elements;
    if (!screenshot) {
      return;
    }
    const capturedAt = device.latest_screenshot_captured_at;
    const busted = `/api/devices/${device.id}/latest-screenshot?t=${encodeURIComponent(capturedAt)}`;
    screenshot.src = busted;
    screenshot.classList.add('connected-screenshot--cached');
    if (deviceLaunchHref(device)) {
      activateScreenshotLink(link);
    }
    setPreviewStatus(connectedStatus, cachedPreviewCopy(capturedAt), 'cached');
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
    const cachedAt =
      capturedAtByDevice.get(String(id)) ||
      this._device.latest_screenshot_captured_at;
    const enableLaunch = () => {
      if (deviceLaunchHref(this._device)) {
        activateScreenshotLink(link);
      }
    };

    if (result.error || !screenshot) {
      if (cachedAt) {
        screenshot?.classList.add('connected-screenshot--cached');
        enableLaunch();
        setPreviewStatus(
          connectedStatus,
          cachedPreviewCopy(cachedAt),
          'cached',
        );
      } else {
        setPreviewStatus(connectedStatus, missingPreviewCopy(), 'error');
      }
      return;
    }

    capturedAtByDevice.set(String(id), result.captured_at || new Date().toISOString());
    const busted = `/api/devices/${id}/latest-screenshot?t=${Date.now()}`;

    const markLive = () => {
      screenshot.classList.remove('connected-screenshot--cached');
      enableLaunch();
      setPreviewStatus(
        connectedStatus,
        `Live preview, updated ${formatRelativeTime(result.captured_at)}.`,
        'live',
      );
    };

    // Pre-load into an off-screen Image. Only swap the displayed <img> src
    // after the browser has fully decoded the new frame so it never goes blank.
    const preload = new Image();
    preload.onload = () => {
      screenshot.src = busted;
      markLive();
    };
    preload.onerror = () => {
      if (cachedAt) {
        screenshot.classList.add('connected-screenshot--cached');
        enableLaunch();
        setPreviewStatus(
          connectedStatus,
          cachedPreviewCopy(cachedAt),
          'cached',
        );
      } else {
        setPreviewStatus(connectedStatus, missingPreviewCopy(), 'error');
        deactivateScreenshotLink(link);
      }
    };
    preload.src = busted;

    // If already cached, onload may have fired synchronously — handle that case.
    if (preload.complete && preload.naturalWidth > 0 && screenshot.src !== busted) {
      screenshot.src = busted;
      markLive();
    }
  }

  _setExpandedVisible(visible) {
    const { expandedDetails, metricsOutput } = this._elements;
    if (expandedDetails) {
      expandedDetails.hidden = !visible;
      if (!visible) {
        expandedDetails.open = false;
      }
    }
    if (!visible && metricsOutput) {
      metricsOutput.innerHTML = '';
    }
  }

  async refreshSnapshot() {
    if (!this._device) {
      return;
    }
    const id = this._device.id;
    const { summaryOutput, metricsOutput } = this._elements;
    const snapshot = await window.dashboardApi.getJson(`/api/devices/${id}/device/snapshot`);
    const online = Boolean(snapshot.collapsed?.online);

    if (summaryOutput) {
      if (snapshot.error) {
        summaryOutput.textContent = snapshot.error;
      } else {
        summaryOutput.innerHTML = formatCollapsedSnapshotSummary(snapshot.collapsed);
      }
    }
    if (snapshot.error || !online) {
      this._setExpandedVisible(false);
      this._stopUpdatePoll();
    } else if (metricsOutput) {
      this._setExpandedVisible(true);
      metricsOutput.innerHTML = formatExpandedSnapshot(snapshot);
      this._syncSoftwareUpdate(snapshot);
    }
  }

  _stopUpdatePoll() {
    if (this._updatePollTimer) {
      window.clearTimeout(this._updatePollTimer);
      this._updatePollTimer = null;
    }
  }

  _syncSoftwareUpdate(snapshot) {
    const currentVersion = snapshot.collapsed?.software_version || '';
    const softwareUpdate = snapshot.expanded?.software_update || null;
    const kind = updateBannerKind(softwareUpdate, currentVersion);
    if (kind === 'available') {
      this._desiredUpdateVersion = latestVersionFrom(softwareUpdate);
    }
    if (kind === 'updating') {
      this._startUpdatePoll();
    } else {
      this._stopUpdatePoll();
    }
  }

  _setSoftwareVersionValue(html) {
    const { metricsOutput } = this._elements;
    if (!metricsOutput) {
      return;
    }
    for (const row of metricsOutput.querySelectorAll('.snapshot-row')) {
      const label = row.querySelector('span');
      if (label && label.textContent === 'Software version') {
        const value = row.querySelector('.snapshot-row__value');
        if (value) {
          value.innerHTML = html;
        }
      }
    }
  }

  _startUpdatePoll() {
    if (this._updatePollTimer || !this._device) {
      return;
    }
    this._updatePollErrors = 0;
    const id = this._device.id;
    const tick = async () => {
      const status = await window.dashboardApi.getJson(`/api/devices/${id}/device/update`);
      if (status.error) {
        this._updatePollErrors += 1;
        if (this._updatePollErrors >= UPDATE_POLL_MAX_ERRORS) {
          this._stopUpdatePoll();
          this._setSoftwareVersionValue('Lost contact during update. Refresh to check.');
          return;
        }
        this._updatePollTimer = window.setTimeout(tick, UPDATE_POLL_INTERVAL_MS);
        return;
      }
      this._updatePollErrors = 0;
      if (status.status === 'IN_PROGRESS') {
        const err = status.updateError ? ` ${escapeHtml(status.updateError)}` : '';
        this._setSoftwareVersionValue(`Updating TinyPilot…${err}`);
        this._updatePollTimer = window.setTimeout(tick, UPDATE_POLL_INTERVAL_MS);
        return;
      }
      this._stopUpdatePoll();
      await this.refreshSnapshot();
    };
    this._updatePollTimer = window.setTimeout(tick, UPDATE_POLL_INTERVAL_MS);
  }

  async startUpdate() {
    if (!this._device || !this._desiredUpdateVersion) {
      return;
    }
    const id = this._device.id;
    const result = await window.dashboardApi.putJson(`/api/devices/${id}/device/update`, {
      version: this._desiredUpdateVersion,
    });
    if (result.error) {
      this._setSoftwareVersionValue(
        `${escapeHtml(this._desiredUpdateVersion)} <span class="snapshot-section-error-text">${escapeHtml(result.error)}</span>`,
      );
      return;
    }
    this._setSoftwareVersionValue('Updating TinyPilot…');
    this._startUpdatePoll();
  }

}

customElements.define('device-card', DeviceCard);
