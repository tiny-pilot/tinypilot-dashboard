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


def test_device_card_open_webui_header_and_remove_label():
    source = CARD.read_text(encoding='utf-8')
    assert 'function renderHeaderOpenWebUi' in source
    assert 'class="header-open-webui"' in source
    assert '>Open WebUI</a>' in source
    assert 'Launch WebUI' not in source
    assert '>Remove device</button>' in source
    assert 'Delete device' not in source
    header = source.split('class="device-card-header"', 1)[1]
    header = header.split('</header>', 1)[0]
    assert 'renderHeaderOpenWebUi(device)' in header


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
    assert '_primeCachedScreenshot' in source


def test_tinypilot_device_heading_matches_target_system():
    source = CARD.read_text(encoding='utf-8')
    assert 'class="connected-system-summary__heading">Target system</h3>' in source
    assert (
        'class="connected-system-summary__heading">TinyPilot device</h3>'
        in source
    )
    css = (ROOT / 'app/static/css/dashboard.css').read_text(encoding='utf-8')
    assert '.tiny-device-body' in css
    assert '.connected-system-body' in css


def test_tinypilot_snapshot_health_line_and_software_row():
    source = CARD.read_text(encoding='utf-8')
    summary = source.split('function formatCollapsedSnapshotSummary', 1)[1]
    summary = summary.split('function ', 1)[0]
    assert 'Connected' in summary
    assert 'Could not reach this TinyPilot' in summary
    assert '${label}</span><span class="status-meta">, last checked' in summary
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
    opening = source.split('<details', 1)[1].split('>', 1)[0]
    assert 'device-details' in opening
    assert 'hidden' in opening
    refresh = source.split('async refreshSnapshot()', 1)[1]
    refresh = refresh.split('async ', 1)[0]
    assert '_setExpandedVisible' in refresh
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


def test_screenshot_click_opens_device_webui():
    source = CARD.read_text(encoding='utf-8')
    assert 'Open latest screenshot in new tab' not in source
    assert 'aria-label="Control ${escapeHtml(device.friendly_name)}"' in source
    assert 'href="/api/devices/${id}/latest-screenshot"' not in source
    assert 'latest-screenshot' in source
    assert 'device.base_url' in source
    link = source.split('id="connected-screenshot-link-${id}"', 1)[1]
    link = link.split('>', 1)[0]
    assert 'target="_blank"' in link
    activate = source.split('function activateScreenshotLink', 1)[1]
    activate = activate.split('function ', 1)[0]
    assert 'link.href' not in activate
