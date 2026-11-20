"""Flask routes for the assistant API."""

import json
from datetime import datetime
from datetime import timezone
from typing import Iterator

from flask import Blueprint
from flask import Response
from flask import jsonify
from flask import request

from app.assistant.agent import get_still
from app.assistant.agent import has_grant
from app.assistant.agent import request_cancel
from app.assistant.agent import run_agent_turn
from app.assistant.agent import set_grant
from app.assistant.agent import store_still
from app.assistant.config import get_config
from app.assistant.config import get_config_dict
from app.assistant.config import set_config
from app.assistant.provider import AssistantProvider
from app.db import get_db
from app.device_client import tinypilot_client_for_device

assistant_blueprint = Blueprint('assistant', __name__, url_prefix='/api/assistant')


def _session_key(device_id: int) -> str:
    """Session key for a device (no user auth in dashboard)."""
    return f'device-{device_id}'


def _record_usage(device_id: int, model: str, usage: dict) -> None:
    """Record token usage to SQLite."""
    db = get_db()
    db.execute(
        """
        INSERT INTO assistant_usage
        (device_id, timestamp, model, prompt_tokens, completion_tokens, total_tokens)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            device_id,
            datetime.now(timezone.utc).isoformat(),
            model,
            usage.get('prompt_tokens', 0),
            usage.get('completion_tokens', 0),
            usage.get('total_tokens', 0),
        ),
    )
    db.commit()


@assistant_blueprint.get('/config')
def get_assistant_config():
    """Get current assistant configuration."""
    return jsonify(get_config_dict())


@assistant_blueprint.put('/config')
def update_assistant_config():
    """Update assistant configuration."""
    payload = request.get_json(silent=True) or {}
    set_config(payload)
    return jsonify(get_config_dict())


@assistant_blueprint.get('/usage')
def get_usage():
    """Get usage history."""
    db = get_db()
    device_id = request.args.get('device_id', type=int)
    sql = 'SELECT * FROM assistant_usage'
    params: list[int] = []
    if device_id is not None:
        sql += ' WHERE device_id = ?'
        params.append(device_id)
    sql += ' ORDER BY id DESC LIMIT 100'
    rows = db.execute(sql, params).fetchall()
    return jsonify({
        'usage': [dict(row) for row in rows],
    })


@assistant_blueprint.post('/<int:device_id>/bootstrap')
def bootstrap(device_id: int):
    """Initialize assistant session, capture first screenshot."""
    config = get_config()
    if config is None:
        return jsonify({'ok': False, 'error': 'assistant_not_configured'}), 503

    client = tinypilot_client_for_device(device_id)
    if client is None:
        return jsonify({'ok': False, 'error': 'device_not_found'}), 404

    session = _session_key(device_id)
    set_grant(session, False)

    # Try to capture initial screenshot.
    try:
        screenshot = client.get_screenshot()
        store_still(session, screenshot)
        has_still = True
    except Exception:  # noqa: BLE001
        has_still = False

    return jsonify({
        'ok': True,
        'has_still': has_still,
        'grant_allowed': has_grant(session),
    })


@assistant_blueprint.get('/<int:device_id>/still')
def get_device_still(device_id: int):
    """Get current screenshot for device."""
    if get_config() is None:
        return jsonify({'error': 'assistant_not_configured'}), 503
    data = get_still(_session_key(device_id))
    if not data:
        return Response(status=204)
    return Response(data, mimetype='image/jpeg')


@assistant_blueprint.post('/<int:device_id>/grant')
def set_device_grant(device_id: int):
    """Set whether AI can use mutating tools."""
    payload = request.get_json(silent=True) or {}
    allowed = bool(payload.get('allowed'))
    set_grant(_session_key(device_id), allowed)
    return jsonify({'ok': True, 'allowed': allowed})


@assistant_blueprint.post('/<int:device_id>/stop')
def stop_turn(device_id: int):
    """Cancel in-progress turn."""
    request_cancel(_session_key(device_id))
    return jsonify({'ok': True, 'stopped': True})


@assistant_blueprint.post('/<int:device_id>/chat')
def chat(device_id: int):
    """Run an agent turn. Streams NDJSON events."""
    config = get_config()
    if config is None:
        return jsonify({'ok': False, 'error': 'assistant_not_configured'}), 503

    client = tinypilot_client_for_device(device_id)
    if client is None:
        return jsonify({'ok': False, 'error': 'device_not_found'}), 404

    payload = request.get_json(silent=True) or {}
    message = payload.get('message')
    if not isinstance(message, str):
        return jsonify({'ok': False, 'error': 'invalid_message'}), 400

    provider = AssistantProvider(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        timeout=config.timeout,
    )

    def event_stream() -> Iterator[str]:
        for event in run_agent_turn(
            message=message,
            session_key=_session_key(device_id),
            client=client,
            provider=provider,
            max_steps=config.max_steps,
            custom_instructions=config.instructions,
        ):
            # Record usage if present.
            if event.get('type') == 'usage' and event.get('usage'):
                _record_usage(device_id, config.model, event['usage'])
            yield json.dumps(event, separators=(',', ':')) + '\n'

    return Response(event_stream(), mimetype='application/x-ndjson')
