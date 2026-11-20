"""Multi-step agent turn loop."""

import json
import threading
from typing import Any
from typing import Iterable

from app.assistant.playbook import build_system_prompt
from app.assistant.provider import AssistantProvider
from app.assistant.tools import TOOL_SPECS
from app.assistant.tools import run_tool
from app.tinypilot_client import TinyPilotClient

# In-memory chat histories keyed by session.
_histories: dict[str, list[dict[str, Any]]] = {}
_stills: dict[str, bytes] = {}
_session_lock = threading.Lock()

# In-memory grants keyed by session.
_grants: dict[str, bool] = {}

# In-memory cancel flags keyed by session.
_cancels: set[str] = set()

# ponytail: one non-blocking lock per session so concurrent POST /chat fails fast.
_turn_locks: dict[str, threading.Lock] = {}


def clear_session_data_for_tests() -> None:
    """Clear all session state (for tests)."""
    with _session_lock:
        _histories.clear()
        _stills.clear()
    _grants.clear()
    _cancels.clear()
    _turn_locks.clear()


def set_grant(session_key: str, allowed: bool) -> None:
    """Set whether mutating tools are allowed for this session."""
    _grants[session_key] = allowed


def has_grant(session_key: str) -> bool:
    """Check if mutating tools are allowed."""
    return _grants.get(session_key, False)


def request_cancel(session_key: str) -> None:
    """Request cancellation of an in-progress turn."""
    _cancels.add(session_key)


def _is_cancelled(session_key: str) -> bool:
    return session_key in _cancels


def _clear_cancel(session_key: str) -> None:
    _cancels.discard(session_key)


def _cancelled_turn_events(session_key: str) -> list[dict[str, Any]] | None:
    if not _is_cancelled(session_key):
        return None
    _clear_cancel(session_key)
    return [{'type': 'stopped'}, {'type': 'done'}]


def get_still(session_key: str) -> bytes | None:
    """Get the current screenshot for a session."""
    with _session_lock:
        return _stills.get(session_key)


def store_still(session_key: str, data: bytes) -> None:
    """Store a screenshot for a session."""
    with _session_lock:
        _stills[session_key] = data


def run_agent_turn(
    *,
    message: str,
    session_key: str,
    client: TinyPilotClient,
    provider: AssistantProvider,
    max_steps: int = 20,
    custom_instructions: str = '',
) -> Iterable[dict[str, Any]]:
    """Run one chat turn. Yields text, tool, still, error, done events."""
    user_text = (message or '').strip()
    if not user_text:
        yield {'type': 'error', 'error': 'empty_message'}
        yield {'type': 'done'}
        return

    turn_lock = _turn_locks.setdefault(session_key, threading.Lock())
    if not turn_lock.acquire(blocking=False):
        yield {'type': 'error', 'error': 'turn_in_progress'}
        yield {'type': 'done'}
        return

    try:
        _clear_cancel(session_key)

        # Append user message to history.
        with _session_lock:
            history = _histories.setdefault(session_key, [])
            history.append({'role': 'user', 'content': user_text})
            history_copy = list(history)

        # Build messages with system prompt.
        system_prompt = build_system_prompt(custom_instructions)
        messages: list[dict[str, Any]] = [
            {'role': 'system', 'content': system_prompt},
            *history_copy,
        ]

        # Capture fresh still at turn start.
        with _session_lock:
            still_store = _stills
        refresh = run_tool(
            'screenshot', {},
            client=client,
            has_grant=True,
            still_store=still_store,
            session_key=session_key,
        )
        if refresh.get('still_updated'):
            yield {'type': 'still'}

        attach_still = bool(refresh.get('still_updated') or get_still(session_key))

        for _step in range(max_steps):
            if cancelled := _cancelled_turn_events(session_key):
                yield from cancelled
                return

            still = get_still(session_key) if attach_still else None
            images = [still] if still else None
            attach_still = False

            tool_calls = []
            text_chunks = []

            for event in provider.complete(messages, TOOL_SPECS, images):
                if cancelled := _cancelled_turn_events(session_key):
                    yield from cancelled
                    return
                if event.kind == 'error':
                    yield {'type': 'error', 'error': event.text or 'provider_error'}
                    yield {'type': 'done'}
                    return
                if event.kind == 'text' and event.text:
                    text_chunks.append(event.text)
                    yield {'type': 'text', 'text': event.text}
                if event.kind == 'tool_call' and event.tool_call:
                    tool_calls.append(event.tool_call)
                if event.kind == 'usage' and event.usage:
                    yield {'type': 'usage', 'usage': event.usage}

            if tool_calls:
                # Record assistant message with tool calls.
                assistant_msg: dict[str, Any] = {
                    'role': 'assistant',
                    'content': ''.join(text_chunks) if text_chunks else None,
                    'tool_calls': [{
                        'id': tc.id,
                        'type': 'function',
                        'function': {
                            'name': tc.name,
                            'arguments': json.dumps(tc.arguments),
                        },
                    } for tc in tool_calls],
                }
                messages.append(assistant_msg)
                with _session_lock:
                    _histories.setdefault(session_key, []).append(assistant_msg)

                # Execute each tool.
                for tc in tool_calls:
                    if cancelled := _cancelled_turn_events(session_key):
                        yield from cancelled
                        return

                    result = run_tool(
                        tc.name,
                        tc.arguments,
                        client=client,
                        has_grant=has_grant(session_key),
                        still_store=still_store,
                        session_key=session_key,
                    )

                    payload: dict[str, Any] = {
                        'type': 'tool',
                        'name': tc.name,
                        'ok': result.get('ok', False),
                    }
                    if not result.get('ok'):
                        payload['error'] = result.get('error')
                    yield payload

                    if result.get('still_updated'):
                        attach_still = True
                        yield {'type': 'still'}

                    tool_msg = {
                        'role': 'tool',
                        'tool_call_id': tc.id,
                        'content': json.dumps(result),
                    }
                    messages.append(tool_msg)
                    with _session_lock:
                        _histories.setdefault(session_key, []).append(tool_msg)
                continue

            # No tool calls - just text response.
            if text_chunks:
                assistant_plain = {'role': 'assistant', 'content': ''.join(text_chunks)}
                messages.append(assistant_plain)
                with _session_lock:
                    _histories.setdefault(session_key, []).append(assistant_plain)

            yield {'type': 'done'}
            return

        yield {'type': 'error', 'error': 'max_steps'}
        yield {'type': 'done'}
    finally:
        turn_lock.release()
