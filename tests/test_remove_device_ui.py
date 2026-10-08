"""Static checks for Remove device modal + Open WebUI header."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app/static/js/dashboard-app.js'
CARD = ROOT / 'app/static/js/components/device-card.js'
THEME = ROOT / 'app/static/css/theme.css'


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


def test_theme_defines_danger_color():
    source = THEME.read_text(encoding='utf-8')
    assert '--color-danger:' in source
