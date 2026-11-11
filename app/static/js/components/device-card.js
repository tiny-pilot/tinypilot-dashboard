import { escapeHtml, formatRelativeTime } from '../lib/strings.js';
import { formatExpandedSnapshot } from '../lib/snapshot-view.js';
import {
  latestVersionFrom,
  updateBannerKind,
} from '../lib/device-update.js';
import { getPreview, putPreview } from '../lib/preview-cache.js';

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
          <span class="status-copy"><span class="status-label">${label}</span><span class="status-meta">, checked <span class="status-checked-at" data-checked-at="${escapeHtml(checkedAt)}">${escapeHtml(checkedText)}</span>.</span></span>
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

function livePreviewCopy(capturedAt) {
  return `Live preview, updated ${formatRelativeTime(capturedAt)}.`;
}

function checkedStatusCopy(label, checkedAt) {
  const at = checkedAt || new Date().toISOString();
  return `${label}, checked ${formatRelativeTime(at)}.`;
}

function setPreviewStatus(el, text, kind, checkedAt) {
  if (!el) {
    return;
  }
  el.textContent = text;
  // Live stays muted; every other preview status uses the caution (yellow) style.
  el.classList.toggle('connected-status--caution', Boolean(kind) && kind !== 'live');
  if (kind) {
    el.dataset.previewKind = kind;
  } else {
    delete el.dataset.previewKind;
  }
  if (checkedAt) {
    el.dataset.checkedAt = checkedAt;
  } else {
    delete el.dataset.checkedAt;
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
    this._online = null;
    this._lastChecked = '';
    this._capturedAt = null;
    this._objectUrl = null;
    this._previewState = 'loading';
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
    this._revokeObjectUrl();
  }

  _revokeObjectUrl() {
    if (this._objectUrl) {
      URL.revokeObjectURL(this._objectUrl);
      this._objectUrl = null;
    }
  }

  _cacheElements() {
    const id = this._device.id;
    this._elements = {
      frame: this.querySelector(`#preview-frame-${id}`),
      screenshot: this.querySelector(`#connected-screenshot-${id}`),
      link: this.querySelector(`#connected-screenshot-link-${id}`),
      connectedStatus: this.querySelector(`#connected-status-${id}`),
      placeholder: this.querySelector(`#preview-placeholder-${id}`),
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
              <div id="preview-frame-${id}" class="preview-frame preview-frame--loading">
                <img
                  id="connected-screenshot-${id}"
                  class="connected-screenshot"
                  alt="Latest screenshot for ${escapeHtml(device.friendly_name)}"
                  hidden
                >
                <div id="preview-placeholder-${id}" class="preview-placeholder preview-placeholder--loading" aria-hidden="true">
                  <div class="preview-spinner" aria-hidden="true"></div>
                </div>
              </div>
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
              <button type="button" data-action="replace-api-key" data-device-id="${id}">Replace API key</button>
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
    this._showLoadingPlaceholder();
    void this._primeFromCache();
  }

  _showLoadingPlaceholder() {
    const { screenshot, placeholder, frame } = this._elements;
    if (screenshot) {
      screenshot.hidden = true;
      screenshot.removeAttribute('src');
      screenshot.classList.remove(
        'connected-screenshot--cached',
        'connected-screenshot--offline',
      );
    }
    if (placeholder) {
      placeholder.hidden = false;
      placeholder.className = 'preview-placeholder preview-placeholder--loading';
      placeholder.innerHTML = '<div class="preview-spinner" aria-hidden="true"></div>';
    }
    if (frame) {
      frame.className = 'preview-frame preview-frame--loading';
    }
    this._previewState = 'loading';
  }

  _showPanelPlaceholder(kind, title, detail) {
    const { screenshot, placeholder, frame, link } = this._elements;
    this._revokeObjectUrl();
    if (screenshot) {
      screenshot.hidden = true;
      screenshot.removeAttribute('src');
      screenshot.classList.remove(
        'connected-screenshot--cached',
        'connected-screenshot--offline',
      );
    }
    if (placeholder) {
      placeholder.hidden = false;
      placeholder.className = `preview-placeholder preview-placeholder--${kind}`;
      placeholder.innerHTML = `
        <p class="preview-placeholder-title">${escapeHtml(title)}</p>
        ${detail ? `<p class="preview-placeholder-detail">${escapeHtml(detail)}</p>` : ''}
      `;
    }
    if (frame) {
      frame.className = `preview-frame preview-frame--${kind}`;
    }
    deactivateScreenshotLink(link);
    this._previewState = kind;
  }

  _showCenteredLabel(text) {
    const { placeholder } = this._elements;
    if (!placeholder) {
      return;
    }
    placeholder.hidden = false;
    placeholder.className = 'preview-placeholder preview-placeholder--overlay';
    placeholder.innerHTML =
      `<p class="preview-placeholder-title">${escapeHtml(text)}</p>`;
  }

  _showImage({ blobUrl, capturedAt, kind }) {
    const { screenshot, placeholder, frame, link } = this._elements;
    if (!screenshot) {
      return;
    }
    screenshot.onerror = () => {
      screenshot.hidden = true;
      screenshot.removeAttribute('src');
      if (this._online === false) {
        this._showOfflineEmpty();
      } else {
        this._showLoadingPlaceholder();
      }
    };
    screenshot.hidden = false;
    screenshot.src = blobUrl;
    screenshot.classList.toggle('connected-screenshot--cached', kind === 'cached');
    screenshot.classList.toggle('connected-screenshot--offline', kind === 'offline');
    if (kind === 'offline') {
      this._showCenteredLabel('Offline');
    } else if (placeholder) {
      placeholder.hidden = true;
      placeholder.innerHTML = '';
    }
    if (frame) {
      frame.className = `preview-frame preview-frame--${kind}`;
    }
    if (deviceLaunchHref(this._device) && kind !== 'offline') {
      activateScreenshotLink(link);
    } else {
      deactivateScreenshotLink(link);
    }
    this._capturedAt = capturedAt;
    this._previewState = kind;
    if (kind === 'live') {
      setPreviewStatus(
        this._elements.connectedStatus,
        livePreviewCopy(capturedAt),
        'live',
        capturedAt,
      );
    } else if (kind === 'offline') {
      const checkedAt = this._lastChecked || capturedAt || new Date().toISOString();
      setPreviewStatus(
        this._elements.connectedStatus,
        checkedStatusCopy('Offline', checkedAt),
        'offline',
        checkedAt,
      );
    } else {
      setPreviewStatus(
        this._elements.connectedStatus,
        cachedPreviewCopy(capturedAt),
        'cached',
        capturedAt,
      );
    }
  }

  async _primeFromCache() {
    if (!this._device) {
      return;
    }
    const cached = await getPreview(this._device.id);
    if (!cached || !this.isConnected) {
      return;
    }
    const blob = await cached.blob();
    const capturedAt =
      cached.headers.get('X-Captured-At') || new Date().toISOString();
    this._revokeObjectUrl();
    this._objectUrl = URL.createObjectURL(blob);
    this._showImage({
      blobUrl: this._objectUrl,
      capturedAt,
      kind: 'cached',
    });
  }

  _showOfflineEmpty(checkedAt) {
    const at = checkedAt || this._lastChecked || new Date().toISOString();
    this._showPanelPlaceholder('offline', 'Offline', '');
    setPreviewStatus(
      this._elements.connectedStatus,
      checkedStatusCopy('Offline', at),
      'offline',
      at,
    );
  }

  _syncPreviewState() {
    if (this._previewState === 'no_signal' && this._online !== false) {
      return;
    }
    if (this._online === false) {
      if (this._objectUrl) {
        this._showImage({
          blobUrl: this._objectUrl,
          capturedAt: this._capturedAt || new Date().toISOString(),
          kind: 'offline',
        });
      } else {
        this._showOfflineEmpty();
      }
      return;
    }
    if (this._previewState === 'offline' && this._objectUrl) {
      this._showImage({
        blobUrl: this._objectUrl,
        capturedAt: this._capturedAt || new Date().toISOString(),
        kind: 'cached',
      });
    }
  }

  async refreshScreenshot(capturedAtByDevice) {
    if (!this._device) {
      return;
    }
    const id = this._device.id;
    const { link } = this._elements;
    deactivateScreenshotLink(link);

    if (!this._objectUrl) {
      this._showLoadingPlaceholder();
    }

    const result = await window.dashboardApi.postScreenshot(
      `/api/devices/${id}/refresh-screenshot`,
    );

    if (result.code === 'no_signal') {
      const checkedAt = this._lastChecked || new Date().toISOString();
      this._showPanelPlaceholder('no_signal', 'No signal', '');
      setPreviewStatus(
        this._elements.connectedStatus,
        checkedStatusCopy('No signal', checkedAt),
        'no_signal',
        checkedAt,
      );
      return;
    }

    if (result.error || !result.blob) {
      if (this._objectUrl) {
        const kind = this._online === false ? 'offline' : 'cached';
        this._showImage({
          blobUrl: this._objectUrl,
          capturedAt: this._capturedAt || new Date().toISOString(),
          kind,
        });
      } else if (this._online === false) {
        this._showOfflineEmpty();
      } else {
        const checkedAt = new Date().toISOString();
        this._showLoadingPlaceholder();
        setPreviewStatus(
          this._elements.connectedStatus,
          result.error || 'Could not capture a screenshot.',
          'error',
          checkedAt,
        );
      }
      return;
    }

    if (result.cacheCopy) {
      try {
        await putPreview(id, result.cacheCopy);
      } catch {
        // Cache Storage is best-effort; live image still shows.
      }
    }

    capturedAtByDevice.set(String(id), result.capturedAt);
    this._revokeObjectUrl();
    this._objectUrl = URL.createObjectURL(result.blob);
    this._showImage({
      blobUrl: this._objectUrl,
      capturedAt: result.capturedAt,
      kind: 'live',
    });
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
    this._online = snapshot.error ? false : online;
    this._lastChecked = snapshot.collapsed?.last_checked || '';
    this._syncPreviewState();

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
