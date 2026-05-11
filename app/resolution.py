"""Helpers for extracting the connected display resolution from TinyPilot responses.

TinyPilot reports resolution information in a few different shapes depending on
the endpoint and firmware version:

* Unofficial ``GET /state`` → ``result.source.resolution`` (dict, list, or
  ``"WxH"`` string).
* Web UI JSON (``/api/settings/video``, ``/api/status``) → a top-level key
  such as ``resolution`` / ``displayResolution`` / ``connectedDeviceResolution``
  or a nested ``video`` / ``capture`` / ``kvm`` block.

This module owns the normalization so ``app.api`` can stay focused on routes.
"""

from typing import Optional


def resolution_from_automation_state(state: Optional[dict]) -> Optional[str]:
    """Return ``"WxH"`` from an Automation ``GET /state`` payload, or ``None``."""
    if not isinstance(state, dict):
        return None
    for key in ('result', 'data', 'payload'):
        nested = state.get(key)
        if isinstance(nested, dict):
            parsed = _parse_resolution_payload(nested.get('resolution'))
            if parsed:
                return parsed
            source = nested.get('source')
            if isinstance(source, dict):
                parsed = _parse_resolution_payload(source.get('resolution'))
                if parsed:
                    return parsed
    return _parse_resolution_payload(state.get('resolution'))


def connected_resolution_from_web_ui(
    video_settings: Optional[dict],
    status: Optional[dict],
) -> str:
    """Best-effort resolution from Web UI JSON, falling back to ``'unknown'``."""
    resolution = _extract_resolution_from_obj(video_settings)
    if resolution != 'unknown':
        return resolution
    return _extract_resolution_from_obj(status)


def _parse_resolution_payload(resolution) -> Optional[str]:
    if resolution is None:
        return None
    if isinstance(resolution, dict):
        width = _coerce_dimension(resolution.get('width'))
        height = _coerce_dimension(resolution.get('height'))
        if width is not None and height is not None:
            return f'{width}x{height}'
        return None
    if isinstance(resolution, (list, tuple)) and len(resolution) >= 2:
        width = _coerce_dimension(resolution[0])
        height = _coerce_dimension(resolution[1])
        if width is not None and height is not None:
            return f'{width}x{height}'
        return None
    if isinstance(resolution, str):
        normalized = resolution.strip().replace('×', 'x').replace('*', 'x')
        lower = normalized.lower()
        if 'x' in lower:
            left, _, right = lower.partition('x')
            width = _coerce_dimension(left.strip())
            height = _coerce_dimension(right.strip())
            if width is not None and height is not None:
                return f'{width}x{height}'
    return None


def _coerce_dimension(value) -> Optional[int]:
    if isinstance(value, bool):
        # bool is an int subclass; reject explicitly.
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)
    return None


def _extract_resolution_from_obj(payload: Optional[dict]) -> str:
    if not isinstance(payload, dict):
        return 'unknown'
    for key in (
        'resolution',
        'displayResolution',
        'inputResolution',
        'kvmResolution',
        'connectedDeviceResolution',
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ('video', 'capture', 'kvm'):
        nested = payload.get(key)
        if isinstance(nested, dict):
            nested_resolution = _extract_resolution_from_obj(nested)
            if nested_resolution != 'unknown':
                return nested_resolution
    width = _coerce_dimension(payload.get('width'))
    height = _coerce_dimension(payload.get('height'))
    if width is not None and height is not None:
        return f'{width}x{height}'
    return 'unknown'
