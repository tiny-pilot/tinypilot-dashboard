"""OpenAI-compatible LLM provider for the assistant."""

import base64
import json
import uuid
from dataclasses import dataclass
from typing import Any
from typing import Iterable
from typing import Optional

import requests


@dataclass
class ToolCall:
    """A tool call from the model."""

    id: str
    name: str
    arguments: dict


@dataclass
class ProviderEvent:
    """Event from the provider during completion."""

    # kind: 'text' | 'tool_call' | 'error' | 'usage'
    kind: str
    text: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    usage: Optional[dict] = None


class AssistantProvider:
    """OpenAI-compatible chat completions client."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip('/')
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def complete(
        self,
        messages: list[dict],
        tools: list[dict],
        images: Optional[list[bytes]] = None,
    ) -> Iterable[ProviderEvent]:
        """Run one model completion. Yields text, tool_call, error, usage."""
        payload_messages = list(messages)
        if images:
            payload_messages = _attach_images(payload_messages, images)

        body: dict[str, Any] = {
            'model': self._model,
            'messages': payload_messages,
        }
        if tools:
            body['tools'] = tools
            body['tool_choice'] = 'auto'

        url = f'{self._base_url}/chat/completions'
        headers = {
            'Authorization': f'Bearer {self._api_key}',
            'Content-Type': 'application/json',
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            yield ProviderEvent(kind='error', text=str(exc))
            return

        if response.status_code == 429:
            yield ProviderEvent(
                kind='error',
                text='Rate limited. Wait a moment and try again.',
            )
            return
        if response.status_code >= 400:
            yield ProviderEvent(
                kind='error',
                text=f'Model API error (HTTP {response.status_code})',
            )
            return

        try:
            data = response.json()
        except ValueError:
            yield ProviderEvent(kind='error', text='Invalid JSON from model')
            return

        message = (data.get('choices') or [{}])[0].get('message') or {}
        content = message.get('content')
        if content:
            yield ProviderEvent(kind='text', text=content)

        for raw_call in message.get('tool_calls') or []:
            fn = raw_call.get('function') or {}
            name = fn.get('name') or ''
            arguments = fn.get('arguments') or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            yield ProviderEvent(
                kind='tool_call',
                tool_call=ToolCall(
                    id=raw_call.get('id') or f'call-{uuid.uuid4().hex[:8]}',
                    name=name,
                    arguments=arguments,
                ),
            )

        usage = data.get('usage')
        if isinstance(usage, dict):
            yield ProviderEvent(kind='usage', usage=usage)


def _attach_images(messages: list[dict], images: list[bytes]) -> list[dict]:
    """Append images as a user message with vision content."""
    if not images:
        return messages
    out = [dict(m) for m in messages]
    parts: list[dict] = [{'type': 'text', 'text': 'Current screenshot:'}]
    for img in images:
        encoded = base64.standard_b64encode(img).decode('ascii')
        parts.append({
            'type': 'image_url',
            'image_url': {
                'url': f'data:image/jpeg;base64,{encoded}'
            },
        })
    out.append({'role': 'user', 'content': parts})
    return out


