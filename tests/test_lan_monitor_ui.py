"""Static checks for LAN Monitor alerts on the v1 card."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD = ROOT / 'app/static/js/components/device-card.js'
APP = ROOT / 'app/static/js/dashboard-app.js'
CSS = ROOT / 'app/static/css/dashboard.css'


def test_checkbox_sits_under_the_device_info_buttons():
    source = CARD.read_text(encoding='utf-8')
    info = source.split('class="card-stage-info"', 1)[1]
    info = info.split('class="lan-monitor-alerts"', 1)[0]
    remove_at = info.index('Remove device')
    label_at = info.index('LAN Monitor alerts')
    details_at = info.index('device-details-')
    assert remove_at < label_at < details_at


def test_alert_lines_sit_between_the_picture_and_the_controls():
    source = CARD.read_text(encoding='utf-8')
    well = source.index('class="card-well"')
    alerts = source.index('class="lan-monitor-alerts"')
    controls = source.index('class="card-controls"')
    assert well < alerts < controls
    info = source.split('class="card-stage-info"', 1)[1].split('class="lan-monitor-alerts"', 1)[0]
    assert 'Dismiss' not in info
    assert 'connected-status--caution' in source
    assert '<button type="button" data-action="dismiss-lan-monitor-alert"' in source


def test_checkbox_stays_disabled_until_lan_monitor_is_on():
    source = CARD.read_text(encoding='utf-8')
    tag = source.split('data-action="lan-monitor-alerts"', 1)[1].split('>', 1)[0]
    assert 'disabled' in tag
    assert '/lan-monitor-status' in source
    assert 'LAN Monitor is off. Turn it on in the device WebUI.' in source
    css = CSS.read_text(encoding='utf-8')
    faded = css.split('.lan-monitor-alerts-toggle:has(input:disabled)', 1)[1].split('}', 1)[0]
    assert 'opacity: 0.55' in faded
    assert 'cursor: not-allowed' in faded


def test_checkbox_label_stays_on_one_row():
    css = CSS.read_text(encoding='utf-8')
    block = css.split('.lan-monitor-alerts-toggle', 1)[1].split('}', 1)[0]
    assert 'display: flex' in block


def test_lan_monitor_css_does_not_restyle_buttons():
    css = CSS.read_text(encoding='utf-8')
    block = css.split('.lan-monitor-alerts-toggle', 1)[1]
    assert 'button' not in block


def test_a_pause_survives_the_device_list_reload():
    source = APP.read_text(encoding='utf-8')
    start = source.split('async _startCheckedLanMonitors', 1)[1]
    start = start.split('async _setLanMonitorAlerts', 1)[0]
    assert '_ensureLanMonitorTimer(device.id)' in start
    assert 'true' not in start
    ensure = source.split('async _ensureLanMonitorTimer', 1)[1]
    ensure = ensure.split('entry.hold = false', 1)[0]
    assert 'entry.hold && !force' in ensure
    assert '_ensureLanMonitorTimer(deviceId, true)' in source


def test_poll_is_opt_in_and_uses_the_existing_reducer():
    source = APP.read_text(encoding='utf-8')
    assert 'applyLanMonitorPoll' in source
    assert 'dismissLanMonitorAlert' in source
    assert 'LAN_MONITOR_POLL_MS = 90_000' in source
    guard = source.split('if (!device.lan_monitor_alerts)', 1)[1]
    assert '/lan-monitor' in guard[:400]
