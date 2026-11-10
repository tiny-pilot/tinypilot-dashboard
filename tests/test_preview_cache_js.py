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
    assert 'No signal from computer' in source
    assert 'Device offline' in source
    assert 'preview-placeholder--shimmer' in source
    assert 'latest-screenshot' not in source
    assert '_primeFromCache' in source
    assert 'Replace API key' in source
