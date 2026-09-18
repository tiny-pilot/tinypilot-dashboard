"""Helpers for TinyPilot device software-update banners."""


def license_blocks_update(license_check_status: str | None) -> bool:
    """Return True when Gatekeeper/Web UI would refuse an update kickoff."""
    if not license_check_status:
        return True
    return license_check_status != 'VALID'


def update_available(current_version: str | None, latest_version: str | None) -> bool:
    if not current_version or not latest_version:
        return False
    return current_version != latest_version


def can_start_update(
    current_version: str | None,
    latest_version: str | None,
    license_check_status: str | None,
) -> bool:
    return update_available(current_version, latest_version) and not license_blocks_update(
        license_check_status
    )
