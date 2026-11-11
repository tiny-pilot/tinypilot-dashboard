"""Static contracts for browser preview cache + labeled preview states."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'app/static/js/lib/preview-cache.js'
API = ROOT / 'app/static/js/api.js'
CARD = ROOT / 'app/static/js/components/device-card.js'


def test_preview_cache_exports_stable_name_and_clear():
    source = CACHE.read_text(encoding='utf-8')
    assert 'tinypilot-dashboard-previews-v1' in source
    assert 'export async function clearPreviewCache' in source
    assert 'window.tinypilotPreviewCache' in source


def test_api_js_has_post_screenshot_and_preserves_code():
    source = API.read_text(encoding='utf-8')
    assert 'postScreenshot' in source
    assert 'code: data.code' in source


def test_device_card_preview_state_labels():
    source = CARD.read_text(encoding='utf-8')
    assert 'Cached preview from' in source
    assert 'Live preview, updated' in source
    assert 'No signal' in source
    assert 'No signal from computer' not in source
    assert 'checkedStatusCopy' in source
    assert "_showCenteredLabel('Offline')" in source
    assert 'Device offline' not in source
    assert 'preview-placeholder--loading' in source
    assert 'preview-placeholder--overlay' in source
    assert 'preview-spinner' in source
    assert 'preview-monitor-icon' not in source
    assert 'preview-offline-badge' not in source
    assert 'latest-screenshot' not in source
    assert '_primeFromCache' in source
    assert 'Replace API key' in source
    assert "kind !== 'live'" in source


def test_dashboard_polls_visible_snapshots_every_five_minutes():
    app = (ROOT / 'app/static/js/dashboard-app.js').read_text(encoding='utf-8')
    assert 'DEVICE_SNAPSHOT_REFRESH_INTERVAL_MS = 5 * 60 * 1000' in app
    assert '_refreshVisibleDeviceSnapshots' in app
    assert '_scheduleSnapshotAutoRefresh' in app


def test_preview_placeholder_hidden_overrides_flex_display():
    css = (ROOT / 'app/static/css/dashboard.css').read_text(encoding='utf-8')
    assert '.preview-placeholder[hidden]' in css
    assert 'display: none !important' in css
    assert 'preview-spinner' in css
    assert 'preview-shimmer' not in css
    assert '.preview-placeholder--offline' in css
    assert '.preview-placeholder--no_signal' in css
