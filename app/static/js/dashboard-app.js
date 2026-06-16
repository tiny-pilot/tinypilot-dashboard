import './components/device-card.js';
import { escapeHtml, formatRelativeTime } from './lib/strings.js';

const DEVICES_PER_PAGE = 4;
const CONNECTED_STATUS_REFRESH_INTERVAL_MS = 30_000;

class DashboardApp extends HTMLElement {
  constructor() {
    super();
    this._elements = {};
    this._allDevices = [];
    this._currentPage = 1;
    this._screenshotAutoRefreshTimers = new Map();
    this._screenshotCapturedAtByDevice = new Map();
  }

  connectedCallback() {
    const v = this.dataset.assetVersion || '1';
    const dashboardVersion = this.dataset.dashboardVersion || '';
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <link rel="stylesheet" href="/static/css/dashboard.css?v=${encodeURIComponent(v)}">
      <header class="topbar">
        <div class="topbar-brand">
          <img class="topbar-logo" src="/static/img/tinypilot-logo.svg?v=${encodeURIComponent(v)}" alt="TinyPilot">
          ${dashboardVersion ? `<span class="topbar-version" title="Dashboard version">v${dashboardVersion}</span>` : ''}
        </div>
        <div class="topbar-actions">
          <button id="add-device-toggle" type="button" class="theme-toggle">Add a device</button>
          <button id="theme-toggle" type="button" class="theme-toggle">Dark mode</button>
        </div>
      </header>
      <main class="dashboard">
        <div id="device-sections" class="device-grid"></div>
        <div id="device-pagination" class="pagination pagination-footer"></div>
      </main>
      <div id="add-device-modal" class="modal" hidden role="dialog" aria-modal="true" aria-labelledby="add-device-heading">
        <button type="button" class="modal-backdrop" id="add-device-modal-backdrop" tabindex="-1" aria-label="Close dialog"></button>
        <section class="modal-panel panel">
          <header class="modal-header">
            <h2 id="add-device-heading">Add a device</h2>
            <button type="button" class="modal-close" id="add-device-modal-close" aria-label="Close">&times;</button>
          </header>
          <form id="add-device-form" class="form-grid">
            <label>
              Friendly name
              <input name="friendly_name" required>
            </label>
            <label>
              TinyPilot device URL
              <input name="base_url" type="url" placeholder="https://192.168.1.44" required>
            </label>
            <button type="submit">Add a device</button>
          </form>
          <p id="add-device-status" class="subtitle"></p>
        </section>
      </div>
    `;

    this._elements = {
      deviceSections: this.shadowRoot.getElementById('device-sections'),
      devicePagination: this.shadowRoot.getElementById('device-pagination'),
      addDeviceToggle: this.shadowRoot.getElementById('add-device-toggle'),
      themeToggle: this.shadowRoot.getElementById('theme-toggle'),
      addDeviceModal: this.shadowRoot.getElementById('add-device-modal'),
      addDeviceHeading: this.shadowRoot.getElementById('add-device-heading'),
      addDeviceModalClose: this.shadowRoot.getElementById('add-device-modal-close'),
      addDeviceModalBackdrop: this.shadowRoot.getElementById('add-device-modal-backdrop'),
      addDeviceForm: this.shadowRoot.getElementById('add-device-form'),
      addDeviceStatus: this.shadowRoot.getElementById('add-device-status'),
    };

    this._bind();
    void this._refreshDeviceList();
    window.setInterval(() => this._refreshConnectedStatusTimes(), CONNECTED_STATUS_REFRESH_INTERVAL_MS);
  }

  _bind() {
    const e = this._elements;
    e.addDeviceToggle.textContent = 'Add a device';
    e.addDeviceToggle.addEventListener('click', () => {
      if (e.addDeviceModal.hasAttribute('hidden')) {
        this._openAddDeviceModal();
      } else {
        this._closeAddDeviceModal();
      }
    });
    e.addDeviceModalClose.addEventListener('click', () => this._closeAddDeviceModal());
    e.addDeviceModalBackdrop.addEventListener('click', () => this._closeAddDeviceModal());

    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') {
        return;
      }
      if (e.addDeviceModal && !e.addDeviceModal.hasAttribute('hidden')) {
        this._closeAddDeviceModal();
        event.preventDefault();
      }
    });

    this._initThemeToggle();
    this._bindAddDeviceForm();
    e.deviceSections.addEventListener('click', (event) => {
      void this._onDeviceSectionClick(event);
    });
    this.shadowRoot.addEventListener('click', (event) => {
      void this._onPaginationClick(event);
    });
  }

  _initThemeToggle() {
    const root = document.documentElement;
    const button = this._elements.themeToggle;
    const savedTheme = window.localStorage.getItem('dashboard-theme');
    if (savedTheme === 'dark' || savedTheme === 'light') {
      root.dataset.theme = savedTheme;
    }
    this._updateThemeToggleText(button, root.dataset.theme === 'dark');
    button.addEventListener('click', () => {
      const isDark = root.dataset.theme === 'dark';
      root.dataset.theme = isDark ? 'light' : 'dark';
      window.localStorage.setItem('dashboard-theme', root.dataset.theme);
      this._updateThemeToggleText(button, !isDark);
    });
  }

  _updateThemeToggleText(button, isDark) {
    button.textContent = isDark ? 'Light mode' : 'Dark mode';
  }

  _addDeviceModalHeadingText() {
    return this._allDevices.length === 0 ? 'Add your first device' : 'Add a device';
  }

  _syncAddDeviceModalState() {
    const { addDeviceModal, addDeviceHeading } = this._elements;
    if (!addDeviceModal || !addDeviceHeading) {
      return;
    }
    addDeviceHeading.textContent = this._addDeviceModalHeadingText();
    if (this._allDevices.length === 0) {
      this._openAddDeviceModal();
    }
  }

  _openAddDeviceModal() {
    const e = this._elements;
    e.addDeviceHeading.textContent = this._addDeviceModalHeadingText();
    e.addDeviceModal.removeAttribute('hidden');
    document.body.style.overflow = 'hidden';
    if (e.addDeviceStatus) {
      e.addDeviceStatus.textContent = '';
    }
    window.requestAnimationFrame(() => {
      const firstInput = e.addDeviceForm?.querySelector('input[name="friendly_name"]');
      firstInput?.focus();
    });
  }

  _closeAddDeviceModal() {
    const { addDeviceModal } = this._elements;
    if (!addDeviceModal || addDeviceModal.hasAttribute('hidden')) {
      return;
    }
    addDeviceModal.setAttribute('hidden', '');
    document.body.style.overflow = '';
  }

  _bindAddDeviceForm() {
    const { addDeviceForm, addDeviceStatus } = this._elements;
    if (!addDeviceForm) {
      return;
    }
    addDeviceForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const formData = new FormData(addDeviceForm);
      const payload = {
        friendly_name: formData.get('friendly_name'),
        base_url: formData.get('base_url'),
      };
      const result = await window.dashboardApi.postJson('/api/devices', payload);
      if (result.error) {
        if (addDeviceStatus) {
          addDeviceStatus.textContent = result.error;
        }
        return;
      }
      if (addDeviceStatus) {
        addDeviceStatus.textContent = `Added device: ${result.device.friendly_name}`;
      }
      addDeviceForm.reset();
      this._currentPage = Number.MAX_SAFE_INTEGER;
      await this._refreshDeviceList();
      this._closeAddDeviceModal();
    });
  }

  _totalPages() {
    return Math.max(1, Math.ceil(this._allDevices.length / DEVICES_PER_PAGE));
  }

  _deviceCard(deviceId) {
    return this._elements.deviceSections.querySelector(
      `device-card[data-device-id="${deviceId}"]`,
    );
  }

  async _onDeviceSectionClick(event) {
    const button = event.target.closest('button[data-action]');
    if (!button) {
      return;
    }
    const action = button.dataset.action;
    const deviceId = button.dataset.deviceId;
    if (!deviceId) {
      return;
    }
    const card = this._deviceCard(deviceId);
    if (!card) {
      return;
    }
    if (action === 'refresh-screenshot') {
      await card.refreshScreenshot(this._screenshotCapturedAtByDevice);
      return;
    }
    if (action === 'save-screenshot-interval') {
      const input = card.querySelector(`#screenshot-interval-${deviceId}`);
      const interval = Number.parseInt(input?.value || '0', 10);
      const result = await window.dashboardApi.postJson(
        `/api/devices/${deviceId}/screenshot-refresh-config`,
        { interval_minutes: interval }
      );
      const connectedStatus = card.querySelector(`#connected-status-${deviceId}`);
      if (result.error) {
        if (connectedStatus) {
          connectedStatus.textContent = `Auto-refresh update failed: ${result.error}`;
        }
        return;
      }
      this._scheduleScreenshotAutoRefresh(String(deviceId), result.screenshot_refresh_interval_minutes);
      if (connectedStatus) {
        connectedStatus.textContent = result.screenshot_refresh_interval_minutes > 0
          ? `Auto-refresh set to every ${result.screenshot_refresh_interval_minutes} min.`
          : 'Auto-refresh disabled.';
      }
      return;
    }
    if (action === 'delete-device') {
      const confirmed = window.confirm('Delete this device from the dashboard?');
      if (!confirmed) {
        return;
      }
      await window.dashboardApi.deleteJson(`/api/devices/${deviceId}`);
      await this._refreshDeviceList();
      return;
    }
    if (action === 'fetch-device-snapshot') {
      await card.refreshSnapshot();
      return;
    }
    if (action === 'fetch-media') {
      const statusEl = card.querySelector(`#virtual-media-status-${deviceId}`);
      const urlInput = card.querySelector(`#virtual-media-url-${deviceId}`);
      const url = urlInput ? urlInput.value.trim() : '';
      if (!url) {
        if (statusEl) {
          statusEl.textContent = 'Please enter a URL.';
        }
        return;
      }
      if (statusEl) {
        statusEl.textContent = 'Downloading…';
      }
      const fetchResult = await window.dashboardApi.postJson(
        `/api/devices/${deviceId}/media/fetch`,
        { url },
      );
      if (fetchResult.error) {
        if (statusEl) {
          statusEl.textContent = `Failed: ${fetchResult.error}`;
        }
      } else {
        await card.refreshMedia();
      }
      return;
    }
    if (action === 'mount-media') {
      const fileSelect = card.querySelector(`#virtual-media-file-${deviceId}`);
      const modeSelect = card.querySelector(`#virtual-media-mode-${deviceId}`);
      const statusEl = card.querySelector(`#virtual-media-status-${deviceId}`);
      const fileName = fileSelect ? fileSelect.value : '';
      const mode = modeSelect ? modeSelect.value : 'CDROM';
      if (!fileName) {
        if (statusEl) {
          statusEl.textContent = 'Please select an image.';
        }
        return;
      }
      const mountResult = await window.dashboardApi.putJson(
        `/api/devices/${deviceId}/media/mount`,
        { fileName, mode },
      );
      if (mountResult.error) {
        if (statusEl) {
          statusEl.textContent = `Mount failed: ${mountResult.error}`;
        }
      } else {
        await card.refreshMedia();
      }
      return;
    }
    if (action === 'eject-media') {
      const ejectArea = card.querySelector(`#virtual-media-eject-area-${deviceId}`);
      const mountedName = ejectArea
        ? ejectArea.closest('.virtual-media-body').querySelector('dd')?.textContent || 'this image'
        : 'this image';
      if (ejectArea) {
        ejectArea.innerHTML = `
          <span class="virtual-media-confirm-text">Eject ${escapeHtml(mountedName)}?</span>
          <button type="button" data-action="eject-media-confirm" data-device-id="${deviceId}">Eject</button>
          <button type="button" data-action="eject-media-cancel" data-device-id="${deviceId}">Cancel</button>
        `;
      }
      return;
    }
    if (action === 'eject-media-confirm') {
      const statusEl = card.querySelector(`#virtual-media-status-${deviceId}`);
      const ejectResult = await window.dashboardApi.putJson(
        `/api/devices/${deviceId}/media/eject`,
      );
      if (ejectResult.error) {
        if (statusEl) {
          statusEl.textContent = `Eject failed: ${ejectResult.error}`;
        }
      } else {
        await card.refreshMedia();
      }
      return;
    }
    if (action === 'eject-media-cancel') {
      await card.refreshMedia();
    }
  }

  async _onPaginationClick(event) {
    const button = event.target.closest('#device-pagination button[data-action]');
    if (!button) {
      return;
    }
    const totalPages = this._totalPages();
    if (button.dataset.action === 'page-prev') {
      this._currentPage = Math.max(1, this._currentPage - 1);
    } else if (button.dataset.action === 'page-next') {
      this._currentPage = Math.min(totalPages, this._currentPage + 1);
    } else {
      return;
    }
    this._renderCurrentPage();
    await this._refreshVisibleDevicePanels();
  }

  _getVisibleDevices() {
    const start = (this._currentPage - 1) * DEVICES_PER_PAGE;
    return this._allDevices.slice(start, start + DEVICES_PER_PAGE);
  }

  _renderDeviceSections(devices) {
    const container = this._elements.deviceSections;
    container.innerHTML = '';
    container.className = 'device-grid';
    const count = Math.min(devices.length, DEVICES_PER_PAGE);
    if (count > 0) {
      container.classList.add(`device-grid--n${count}`);
    }
    for (const device of devices) {
      const card = document.createElement('device-card');
      card.dataset.deviceId = String(device.id);
      card.device = device;
      container.appendChild(card);
    }
  }

  _renderPaginationControls() {
    const container = this._elements.devicePagination;
    const total = this._allDevices.length;
    const totalPages = Math.max(1, Math.ceil(total / DEVICES_PER_PAGE));
    const start = total === 0 ? 0 : (this._currentPage - 1) * DEVICES_PER_PAGE + 1;
    const end = Math.min(this._currentPage * DEVICES_PER_PAGE, total);
    container.innerHTML = `
    <span class="pagination-summary">Showing ${start}-${end} of ${total}</span>
    <button type="button" data-action="page-prev" ${this._currentPage <= 1 ? 'disabled' : ''}>Previous page</button>
    <span class="pagination-summary">Page ${this._currentPage} / ${totalPages}</span>
    <button type="button" data-action="page-next" ${this._currentPage >= totalPages ? 'disabled' : ''}>Next page</button>
  `;
  }

  _clearAllScreenshotAutoRefreshTimers() {
    for (const timer of this._screenshotAutoRefreshTimers.values()) {
      window.clearInterval(timer);
    }
    this._screenshotAutoRefreshTimers.clear();
  }

  _scheduleScreenshotAutoRefresh(deviceId, intervalMinutes) {
    const timer = this._screenshotAutoRefreshTimers.get(deviceId);
    if (timer) {
      window.clearInterval(timer);
      this._screenshotAutoRefreshTimers.delete(deviceId);
    }
    const intervalMs = Number(intervalMinutes) * 60 * 1000;
    if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
      return;
    }
    const newTimer = window.setInterval(() => {
      const card = this._deviceCard(deviceId);
      if (card) {
        void card.refreshScreenshot(this._screenshotCapturedAtByDevice);
      }
    }, intervalMs);
    this._screenshotAutoRefreshTimers.set(deviceId, newTimer);
  }

  _scheduleScreenshotAutoRefreshForDevices(devices) {
    this._clearAllScreenshotAutoRefreshTimers();
    for (const device of devices) {
      this._scheduleScreenshotAutoRefresh(String(device.id), device.screenshot_refresh_interval_minutes || 0);
    }
  }

  _renderCurrentPage() {
    const visibleDevices = this._getVisibleDevices();
    this._renderDeviceSections(visibleDevices);
    this._renderPaginationControls();
    this._scheduleScreenshotAutoRefreshForDevices(visibleDevices);
  }

  _refreshConnectedStatusTimes() {
    for (const [deviceId, capturedAt] of this._screenshotCapturedAtByDevice.entries()) {
      const card = this._deviceCard(deviceId);
      const connectedStatus = card?.querySelector(`#connected-status-${deviceId}`);
      if (!connectedStatus) {
        continue;
      }
      connectedStatus.textContent = `Screenshot refreshed ${formatRelativeTime(capturedAt)}.`;
    }
  }

  async _refreshVisibleDevicePanels() {
    const visibleDevices = this._getVisibleDevices();
    for (const device of visibleDevices) {
      const card = this._deviceCard(String(device.id));
      if (!card) {
        continue;
      }
      await card.refreshScreenshot(this._screenshotCapturedAtByDevice);
      await card.refreshSnapshot();
      await card.refreshMedia();
    }
  }

  async _refreshDeviceList() {
    const payload = await window.dashboardApi.getJson('/api/devices');
    this._allDevices = payload.devices || [];
    for (const device of this._allDevices) {
      if (device.latest_screenshot_captured_at) {
        this._screenshotCapturedAtByDevice.set(String(device.id), device.latest_screenshot_captured_at);
      }
    }
    const totalPages = this._totalPages();
    this._currentPage = Math.min(this._currentPage, totalPages);
    this._renderCurrentPage();
    this._syncAddDeviceModalState();
    await this._refreshVisibleDevicePanels();
    this._refreshConnectedStatusTimes();
  }
}

customElements.define('dashboard-app', DashboardApp);
