"""Tests for the assistant agent loop."""

import threading
import time
import unittest
import uuid
from unittest.mock import MagicMock

from app.assistant.agent import clear_session_data_for_tests
from app.assistant.agent import has_grant
from app.assistant.agent import run_agent_turn
from app.assistant.agent import set_grant
from app.assistant.provider import ProviderEvent
from app.assistant.provider import ToolCall


class FakeProvider:
    """Deterministic provider for tests."""

    def complete(self, messages, tools, images=None):
        if any(m.get('role') == 'tool' for m in messages):
            yield ProviderEvent(kind='text', text='Done.')
            return
        yield ProviderEvent(
            kind='tool_call',
            tool_call=ToolCall(
                id=f'fake-{uuid.uuid4().hex[:8]}',
                name='screenshot',
                arguments={},
            ),
        )


class KeystrokeProvider:
    """Requests a keystroke on the first model turn (after any tool results)."""

    def complete(self, messages, tools, images=None):
        if any(m.get('role') == 'tool' for m in messages):
            yield ProviderEvent(kind='text', text='Done.')
            return
        yield ProviderEvent(
            kind='tool_call',
            tool_call=ToolCall(
                id='fake-key',
                name='keystroke',
                arguments={'key': 'Enter'},
            ),
        )


class GrantTest(unittest.TestCase):

    def setUp(self):
        clear_session_data_for_tests()

    def test_grant_defaults_to_false(self):
        self.assertFalse(has_grant('new-session'))

    def test_set_grant_enables(self):
        set_grant('test', True)
        self.assertTrue(has_grant('test'))

    def test_set_grant_disables(self):
        set_grant('test', True)
        set_grant('test', False)
        self.assertFalse(has_grant('test'))


class RunAgentTurnTest(unittest.TestCase):

    def setUp(self):
        clear_session_data_for_tests()
        self.client = MagicMock()
        self.client.get_screenshot.return_value = b'fake-jpeg'
        self.provider = FakeProvider()

    def test_empty_message_returns_error(self):
        events = list(run_agent_turn(
            message='',
            session_key='test',
            client=self.client,
            provider=self.provider,
        ))

        self.assertEqual(events[0]['type'], 'error')
        self.assertEqual(events[0]['error'], 'empty_message')
        self.assertEqual(events[1]['type'], 'done')

    def test_captures_screenshot_at_turn_start(self):
        events = list(run_agent_turn(
            message='Hello',
            session_key='test',
            client=self.client,
            provider=self.provider,
        ))

        # First event should be still (from initial screenshot).
        self.assertEqual(events[0]['type'], 'still')
        self.client.get_screenshot.assert_called()

    def test_yields_tool_events(self):
        events = list(run_agent_turn(
            message='What do you see?',
            session_key='test',
            client=self.client,
            provider=self.provider,
        ))

        # Should have: still, tool (screenshot from FakeProvider), still, text, done.
        event_types = [e['type'] for e in events]
        self.assertIn('tool', event_types)
        self.assertIn('done', event_types)

    def test_keystroke_without_grant_yields_grant_required(self):
        events = list(run_agent_turn(
            message='Press enter',
            session_key='test',
            client=self.client,
            provider=KeystrokeProvider(),
        ))
        tool_events = [e for e in events if e.get('type') == 'tool']
        self.assertTrue(tool_events)
        self.assertEqual(tool_events[0]['name'], 'keystroke')
        self.assertFalse(tool_events[0]['ok'])
        self.assertEqual(tool_events[0]['error'], 'grant_required')
        self.client.post_v1.assert_not_called()

    def test_concurrent_turn_returns_turn_in_progress(self):
        started = threading.Event()

        class SlowProvider:
            def complete(self, messages, tools, images=None):
                started.set()
                time.sleep(0.3)
                yield ProviderEvent(kind='text', text='Done.')

        def first_turn():
            list(run_agent_turn(
                message='First',
                session_key='busy',
                client=self.client,
                provider=SlowProvider(),
            ))

        thread = threading.Thread(target=first_turn)
        thread.start()
        self.assertTrue(started.wait(timeout=2))

        second = list(run_agent_turn(
            message='Second',
            session_key='busy',
            client=self.client,
            provider=FakeProvider(),
        ))
        thread.join(timeout=2)

        self.assertEqual(second[0]['type'], 'error')
        self.assertEqual(second[0]['error'], 'turn_in_progress')


if __name__ == '__main__':
    unittest.main()
