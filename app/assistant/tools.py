"""Device tools for the assistant (screenshot, HID input)."""

import time
from typing import Any

import requests

from app.tinypilot_client import TinyPilotClient

# Tools that require user grant before execution.
_MUTATING_TOOLS = frozenset({'keystroke', 'mouseEvent', 'click', 'paste'})

TOOL_SPECS: list[dict[str, Any]] = [
    {
        'type': 'function',
        'function': {
            'name': 'screenshot',
            'description': 'Capture a JPEG of the remote display.',
            'parameters': {
                'type': 'object',
                'properties': {},
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'keystroke',
            'description': 'Send one keystroke (Enter, Tab, arrows, letters, shortcuts).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'key': {
                        'type': 'string',
                        'description': 'Key value (e.g. "Enter", "a", "ArrowDown").',
                    },
                    'ctrlKey': {'type': 'boolean'},
                    'altKey': {'type': 'boolean'},
                    'shiftKey': {'type': 'boolean'},
                    'metaKey': {'type': 'boolean'},
                },
                'required': ['key'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'click',
            'description': 'Click at coordinates (relativeX/Y in 0-1, origin top-left).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'relativeX': {'type': 'number', 'description': 'X 0-1'},
                    'relativeY': {'type': 'number', 'description': 'Y 0-1'},
                    'button': {
                        'type': 'integer',
                        'enum': [1, 2, 4],
                        'description': '1=left, 2=right, 4=middle',
                    },
                },
                'required': ['relativeX', 'relativeY'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'paste',
            'description': 'Type a string via HID paste. Prefer over per-char keystrokes.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'text': {'type': 'string'},
                },
                'required': ['text'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'mouseEvent',
            'description': 'Low-level mouse move/scroll. Prefer click for normal clicks.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'buttons': {'type': 'integer'},
                    'relativeX': {'type': 'number'},
                    'relativeY': {'type': 'number'},
                    'verticalWheelDelta': {'type': 'integer'},
                    'horizontalWheelDelta': {'type': 'integer'},
                },
                'required': ['relativeX', 'relativeY'],
            },
        },
    },
]


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _relative_coord(value: Any) -> float | None:
    """Parse a 0–1 coordinate; None when the model sends garbage."""
    try:
        return _clamp(float(value))
    except (TypeError, ValueError):
        return None


def _int_arg(value: Any, default: int) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _wheel_delta(value: Any) -> int:
    """Normalize wheel delta to -1, 0, or 1."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0
    if n > 0:
        return 1
    if n < 0:
        return -1
    return 0


def run_tool(
    name: str,
    arguments: dict,
    *,
    client: TinyPilotClient,
    has_grant: bool,
    still_store: dict,
    session_key: str,
) -> dict:
    """Execute a tool. Returns {ok, result|error, still_updated?}."""

    if name in _MUTATING_TOOLS and not has_grant:
        return {'ok': False, 'error': 'grant_required'}

    if name == 'screenshot':
        try:
            img = client.get_screenshot()
        except (requests.RequestException, ValueError) as exc:
            return {'ok': False, 'error': str(exc)}
        still_store[session_key] = img
        return {'ok': True, 'result': {}, 'still_updated': True}

    if name == 'keystroke':
        try:
            client.post_v1('/api/v1/keystroke', arguments)
        except requests.RequestException as exc:
            return {'ok': False, 'error': str(exc)}
        return {'ok': True, 'result': {}}

    if name == 'paste':
        text = arguments.get('text')
        if not isinstance(text, str):
            return {'ok': False, 'error': 'invalid_arguments'}
        try:
            client.post_v1('/api/v1/paste', {'text': text, 'language': 'en-US'})
        except requests.RequestException as exc:
            return {'ok': False, 'error': str(exc)}
        # Settle delay: 100ms per char + 1s.
        time.sleep(0.1 * len(text) + 1.0)
        return {'ok': True, 'result': {}}

    if name == 'click':
        rel_x = _relative_coord(arguments.get('relativeX'))
        rel_y = _relative_coord(arguments.get('relativeY'))
        if rel_x is None or rel_y is None:
            return {'ok': False, 'error': 'invalid_arguments'}
        button = _int_arg(arguments.get('button', 1), 1)
        if button is None:
            return {'ok': False, 'error': 'invalid_arguments'}
        if button not in (1, 2, 4):
            return {'ok': False, 'error': 'invalid_arguments'}
        # Move -> press -> release.
        for buttons in (0, button, 0):
            try:
                client.post_v1('/api/v1/mouseEvent', {
                    'buttons': buttons,
                    'relativeX': rel_x,
                    'relativeY': rel_y,
                    'verticalWheelDelta': 0,
                    'horizontalWheelDelta': 0,
                })
            except requests.RequestException as exc:
                return {'ok': False, 'error': str(exc)}
            time.sleep(0.05)
        return {'ok': True, 'result': {'relativeX': rel_x, 'relativeY': rel_y}}

    if name == 'mouseEvent':
        rel_x = _relative_coord(arguments.get('relativeX'))
        rel_y = _relative_coord(arguments.get('relativeY'))
        if rel_x is None or rel_y is None:
            return {'ok': False, 'error': 'invalid_arguments'}
        buttons = _int_arg(arguments.get('buttons', 0), 0)
        if buttons is None:
            return {'ok': False, 'error': 'invalid_arguments'}
        body = {
            'buttons': buttons,
            'relativeX': rel_x,
            'relativeY': rel_y,
            'verticalWheelDelta': _wheel_delta(arguments.get('verticalWheelDelta', 0)),
            'horizontalWheelDelta': _wheel_delta(arguments.get('horizontalWheelDelta', 0)),
        }
        try:
            client.post_v1('/api/v1/mouseEvent', body)
        except requests.RequestException as exc:
            return {'ok': False, 'error': str(exc)}
        return {'ok': True, 'result': {}}

    return {'ok': False, 'error': 'unknown_tool'}
