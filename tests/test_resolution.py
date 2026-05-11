"""Unit tests for the resolution parser module."""

from app.resolution import connected_resolution_from_web_ui
from app.resolution import resolution_from_automation_state


def test_resolution_from_automation_state_returns_none_for_non_dict():
    assert resolution_from_automation_state(None) is None
    assert resolution_from_automation_state('1920x1080') is None


def test_resolution_from_automation_state_rejects_zero_or_negative_dimensions():
    state = {'result': {'source': {'resolution': {'width': 0, 'height': 1080}}}}
    assert resolution_from_automation_state(state) is None


def test_resolution_from_automation_state_rejects_boolean_dimensions():
    state = {'result': {'source': {'resolution': {'width': True, 'height': True}}}}
    assert resolution_from_automation_state(state) is None


def test_connected_resolution_from_web_ui_prefers_video_settings():
    video = {'displayResolution': '1920x1080'}
    status = {'resolution': '800x600'}
    assert connected_resolution_from_web_ui(video, status) == '1920x1080'


def test_connected_resolution_from_web_ui_falls_back_to_status():
    status = {'video': {'connectedDeviceResolution': '1280x720'}}
    assert connected_resolution_from_web_ui(None, status) == '1280x720'


def test_connected_resolution_from_web_ui_returns_unknown_when_missing():
    assert connected_resolution_from_web_ui({}, {}) == 'unknown'
