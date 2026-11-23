"""Static checks for Remove device modal + Open WebUI header."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app/static/js/dashboard-app.js'
CARD = ROOT / 'app/static/js/components/device-card.js'
THEME = ROOT / 'app/static/css/theme.css'


def test_update_device_uses_in_page_confirm_modal():
    source = APP.read_text(encoding='utf-8')
    assert 'update-device-modal' in source
    assert '_openUpdateDeviceModal' in source
    assert '_confirmUpdateDevice' in source
    assert "action === 'start-device-update'" in source
    start = source.split("action === 'start-device-update'", 1)[1]
    start = start.split('}', 1)[0]
    assert 'startUpdate()' not in start
    assert '_openUpdateDeviceModal(card)' in start
    assert 'window.confirm(' not in source


def test_remove_device_uses_in_page_modal():
    source = APP.read_text(encoding='utf-8')
    assert '_openDeleteDeviceModal' in source
    assert 'delete-device-modal' in source
    assert "typed !== 'REMOVE'" in source
    assert 'window.confirm(' not in source
    assert 'window.prompt(' not in source
    assert 'button-danger-quiet' in source
    delete_modal = source.split('id="delete-device-modal"', 1)[1]
    delete_modal = delete_modal.split('id="replace-api-key-modal"', 1)[0]
    assert 'Type REMOVE to remove this device from your Dashboard.' in delete_modal
    assert 'add it again' not in delete_modal
    assert 'from the device' not in delete_modal


def test_replace_api_key_uses_in_page_modal_without_danger():
    app = APP.read_text(encoding='utf-8')
    assert 'replace-api-key-modal' in app
    assert '_openReplaceApiKeyModal' in app
    assert '_bindReplaceApiKeyForm' in app
    assert 'REPLACE_API_KEY_MODAL_LABEL' in app
    assert 'System → Automation' in app
    modal = app.split('id="replace-api-key-modal"', 1)[1]
    modal = modal.split('id="update-device-modal"', 1)[0]
    assert 'button-danger-quiet' not in modal
    assert 'type="password"' in modal
    assert '>Save</button>' in modal
    assert '>Cancel</button>' in modal
    assert 'Create a key on the device under System → Automation,<br>then paste it here.' in modal
    card = CARD.read_text(encoding='utf-8')
    assert 'data-action="replace-api-key"' in card
    assert 'replace-api-key-details' not in card
    actions = card.split('class="actions device-actions"', 1)[1]
    actions = actions.split('</div>', 1)[0]
    assert 'Replace API key' in actions
    assert 'Remove device' in actions
    assert actions.index('Replace API key') < actions.index('Remove device')


def test_device_card_open_webui_header_and_remove_label():
    source = CARD.read_text(encoding='utf-8')
    assert 'Open WebUI' not in source
    assert 'renderOpenDevice' not in source
    assert 'header-open-webui' not in source
    assert 'Launch WebUI' not in source
    assert '>Remove device</button>' in source
    assert 'Delete device' not in source
    primary = source.split('class="actions actions-connected-primary"', 1)[1]
    primary = primary.split('</div>', 1)[0]
    assert 'refresh-screenshot' in primary
    assert 'connected-status-' in primary
    refresh_row = source.split('class="actions actions-auto-refresh-row"', 1)[1]
    refresh_row = refresh_row.split('</div>', 1)[0]
    assert 'save-screenshot-interval' in refresh_row
    assert 'toggle-device-info' in refresh_row


def test_theme_defines_danger_and_warning_colors():
    source = THEME.read_text(encoding='utf-8')
    assert '--color-danger:' in source
    assert '--color-warning:' in source


def test_dashboard_is_dark_only_without_theme_toggle():
    app = APP.read_text(encoding='utf-8')
    index = (ROOT / 'app/templates/index.html').read_text(encoding='utf-8')
    assert 'id="theme-toggle"' not in app
    assert '_initThemeToggle' not in app
    assert 'data-theme="dark"' in index
    css = (ROOT / 'app/static/css/dashboard.css').read_text(encoding='utf-8')
    theme = THEME.read_text(encoding='utf-8')
    assert '.subtitle.connected-status--caution' in css
    assert ':root[data-theme="dark"]' not in css
    assert ':root[data-theme="dark"]' not in theme
    assert 'color-scheme: dark' in theme
    assert 'hsl(35, 60%, 97%)' not in theme


def test_device_card_keeps_cached_preview_copy():
    source = CARD.read_text(encoding='utf-8')
    assert 'Cached preview from' in source
    assert ' · ' not in source
    app = APP.read_text(encoding='utf-8')
    assert ' · ' not in app
    assert 'Could not capture a screenshot.' in source
    assert "kind === 'cached'" in source
    assert '_primeFromCache' in source


def test_page_shows_eight_devices_in_a_dense_grid():
    app = APP.read_text(encoding='utf-8')
    assert 'const DEVICES_PER_PAGE = 8;' in app
    render = app.split('_renderDeviceSections', 1)[1]
    render = render.split('_renderPaginationControls', 1)[0]
    assert 'devices.length > 4' in render
    assert 'devices.length === 5 || devices.length === 6' in render
    assert 'devices.length === 3 || devices.length === 4' in render
    assert "container.classList.add('device-grid--dense', 'device-grid--n1')" in render
    assert "container.classList.add('device-grid--dense', 'device-grid--six')" in render
    assert "container.classList.add('device-grid--dense', 'device-grid--quad')" in render
    assert "container.classList.add('device-grid--dense')" in render
    css = (ROOT / 'app/static/css/dashboard.css').read_text(encoding='utf-8')
    assert '.device-grid.device-grid--dense .card-stage' in css
    nondense = css.split(
        '.device-grid:not(.device-grid--n1):not(.device-grid--dense) .card-stage',
        1,
    )[1]
    nondense = nondense.split('}', 1)[0]
    assert 'aspect-ratio: 16 / 9' in nondense
    assert 'height: auto' in nondense
    assert 'repeat(4, minmax(0, 1fr))' in css
    assert 'repeat(3, minmax(0, 1fr))' in css
    assert 'device-grid--quad' in css
    assert 'repeat(2, minmax(0, 1fr))' in css
    assert '100vh' in css
    assert '52rem' not in css
    assert '.dashboard:has(.device-grid--n1) .device-grid.device-grid--n1' in css
    assert 'grid-template-rows: minmax(0, 1fr)' in css


def test_device_info_replaces_the_screen_inside_the_card():
    source = CARD.read_text(encoding='utf-8')
    assert 'Target system' not in source
    assert 'Requires Automation License' not in source
    assert 'Show device info' in source
    assert 'Hide device info' in source
    assert 'class="card-well"' in source
    assert 'class="card-stage"' in source
    well = source.split('class="card-well"', 1)[1]
    well = well.split('class="card-controls"', 1)[0]
    assert 'class="card-stage-info"' in well
    assert 'data-action="delete-device"' in well
    assert 'connected-screenshot-link' in well


def test_tinypilot_snapshot_health_line_and_software_row():
    source = CARD.read_text(encoding='utf-8')
    summary = source.split('function formatCollapsedSnapshotSummary', 1)[1]
    summary = summary.split('function ', 1)[0]
    assert 'Connected' in summary
    assert 'Could not reach this TinyPilot' in summary
    assert '${label}</span><span class="status-meta">, checked' in summary
    assert 'class="status-copy"' in summary
    assert 'Disconnected' not in summary
    assert 'software_version' not in summary
    assert 'device_url' not in summary
    assert 'status-url' not in source
    assert 'id="device-software-' not in source
    assert 'id="device-update-banner-' not in source
    card_remove = source.split('data-action="delete-device"', 1)[1]
    card_remove = card_remove.split('</button>', 1)[0]
    assert 'button-danger-quiet' not in card_remove
    view = (ROOT / 'app/static/js/lib/snapshot-view.js').read_text(encoding='utf-8')
    assert "snapshotRow('Device URL'" in view
    assert 'Software version' in view
    assert 'data-action="start-device-update"' in view
    assert "snapshotRow('Reachability'" not in view
    assert 'Reachability' not in view
    inner = source.split('class="device-details"', 1)[1]
    inner = inner.split('>', 1)[0]
    assert 'hidden' in inner
    refresh = source.split('async refreshSnapshot()', 1)[1]
    refresh = refresh.split('async ', 1)[0]
    assert '_setExpandedVisible' in refresh
    assert 'expandedDetails.open' not in source
    assert 'Refresh device info' in source
    assert 'Refresh device snapshot' not in source
    assert 'collapsed?.online' in refresh
    assert 'last_management_error' not in view
    api = (ROOT / 'app/static/js/api.js').read_text(encoding='utf-8')
    assert 'AbortSignal.timeout' in api
    assert "error: 'Could not reach the dashboard.'" in api
    app = (ROOT / 'app/static/js/dashboard-app.js').read_text(encoding='utf-8')
    assert 'Promise.allSettled' in app
    assert 'payload.error || !Array.isArray(payload.devices)' in app
    assert 'document.documentElement.dataset.theme' not in app
    assert 'UPDATE_POLL_MAX_ERRORS' in source
    assert 'window.setTimeout(tick' in source
    assert 'window.setInterval(async' not in source


def test_dashboard_buttons_match_cloud_navy():
    css = (ROOT / 'app/static/css/dashboard.css').read_text(encoding='utf-8')
    assert 'background: var(--color-nav);' in css
    assert 'border: 1px solid rgba(255, 255, 255, 0.45);' in css
    assert 'linear-gradient(0deg' not in css
    assert 'button.button-danger-quiet' in css
    assert 'hsl(230, 16%, 55%)' not in css


def test_circleci_runs_core_and_security_jobs():
    config = (ROOT / '.circleci/config.yml').read_text(encoding='utf-8')
    for job in (
        'check_whitespace',
        'check_bash',
        'check_python',
        'check_javascript',
        'check_security',
    ):
        assert job in config
    assert './dev-scripts/check-python' in config
    assert './dev-scripts/check-security' in config
    assert './dev-scripts/check-javascript' in config


def test_device_card_renames_from_the_title():
    source = CARD.read_text(encoding='utf-8')
    assert 'class="device-title-rename" data-rename="start"' in source
    assert 'aria-label="Rename ${escapeHtml(device.friendly_name)}"' in source
    assert '>Rename</button>' not in source
    assert 'maxlength="60"' in source
    assert 'maxlength="60"' in APP.read_text(encoding='utf-8')
    assert 'data-rename="cancel"' not in source
    assert 'Could not rename this device.' in source
    assert 'role="alert"' in source
    assert 'data-action="rename"' not in source
    assert 'window.prompt(' not in APP.read_text(encoding='utf-8')
    assert "start.setAttribute('aria-label', `Rename ${name}`)" in source
    blur = source.split("addEventListener('blur'", 1)[1]
    blur = blur.split('addEventListener', 1)[0]
    assert '.focus(' not in blur
    escape = source.split("event.key === 'Escape'", 1)[1]
    escape = escape.split("event.key === 'Enter'", 1)[0]
    assert 'start.focus()' in escape
    enter = source.split("event.key === 'Enter'", 1)[1]
    enter = enter.split('setTimeout', 1)[0]
    assert 'start.focus()' in enter
    css = (ROOT / 'app/static/css/dashboard.css').read_text(encoding='utf-8')
    rule = css.split('.device-card-header .device-rename-error', 1)[1]
    rule = rule.split('}', 1)[0]
    assert 'var(--color-danger)' in rule


def test_screenshot_click_opens_device_webui():
    source = CARD.read_text(encoding='utf-8')
    assert 'Open latest screenshot in new tab' not in source
    assert 'aria-label="Control ${escapeHtml(device.friendly_name)}"' in source
    assert 'href="/api/devices/${id}/latest-screenshot"' not in source
    assert 'latest-screenshot' not in source
    assert 'device.base_url' in source
    link = source.split('id="connected-screenshot-link-${id}"', 1)[1]
    link = link.split('>', 1)[0]
    assert 'target="_blank"' in link
    activate = source.split('function activateScreenshotLink', 1)[1]
    activate = activate.split('function ', 1)[0]
    assert 'link.href' not in activate
