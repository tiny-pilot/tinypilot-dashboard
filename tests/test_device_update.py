"""Tests for device software-update banner helpers."""

from app.device_update import can_start_update
from app.device_update import license_blocks_update
from app.device_update import update_available


def test_update_available_when_versions_differ():
    assert update_available('3.1.0', '3.2.0') is True
    assert update_available('3.2.0', '3.2.0') is False
    assert update_available(None, '3.2.0') is False


def test_license_blocks_when_not_valid():
    assert license_blocks_update('VALID') is False
    assert license_blocks_update('UNLICENSED') is True
    assert license_blocks_update('EXPIRED') is True
    assert license_blocks_update('INVALID') is True
    assert license_blocks_update(None) is True


def test_can_start_update_requires_newer_and_valid_license():
    assert can_start_update('3.1.0', '3.2.0', 'VALID') is True
    assert can_start_update('3.1.0', '3.2.0', 'UNLICENSED') is False
    assert can_start_update('3.2.0', '3.2.0', 'VALID') is False
