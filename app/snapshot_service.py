"""Atomic write helpers for device screenshots.

The dashboard stores only the *latest* screenshot per device so the data
directory does not grow unbounded. Writing is two-step (``.tmp`` then atomic
``rename``) so a partially-written file is never visible to readers.
"""

from pathlib import Path


def write_latest_screenshot(
    root: Path,
    device_id: int,
    image_bytes: bytes,
) -> Path:
    """Write ``image_bytes`` as the latest screenshot for ``device_id``."""
    root.mkdir(parents=True, exist_ok=True)
    tmp_path = root / f'device-{device_id}-latest.jpg.tmp'
    latest_path = root / f'device-{device_id}-latest.jpg'
    tmp_path.write_bytes(image_bytes)
    tmp_path.replace(latest_path)
    return latest_path
