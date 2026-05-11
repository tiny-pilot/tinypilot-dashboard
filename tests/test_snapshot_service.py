from app.snapshot_service import write_latest_screenshot


def test_atomic_latest_screenshot_write(tmp_path):
    screenshots_dir = tmp_path / 'screenshots'

    result = write_latest_screenshot(screenshots_dir, 7, b'jpeg-data')

    assert result.name == 'device-7-latest.jpg'
    assert result.exists()
    assert not (screenshots_dir / 'device-7-latest.jpg.tmp').exists()
