"""Tests for the assistant tools."""

import unittest
from unittest.mock import MagicMock

from app.assistant.tools import _clamp
from app.assistant.tools import _wheel_delta
from app.assistant.tools import run_tool


class ClampTest(unittest.TestCase):

    def test_clamps_to_range(self):
        self.assertEqual(_clamp(-0.5), 0.0)
        self.assertEqual(_clamp(1.5), 1.0)
        self.assertEqual(_clamp(0.5), 0.5)


class WheelDeltaTest(unittest.TestCase):

    def test_normalizes_to_sign(self):
        self.assertEqual(_wheel_delta(100), 1)
        self.assertEqual(_wheel_delta(-50), -1)
        self.assertEqual(_wheel_delta(0), 0)
        self.assertEqual(_wheel_delta('invalid'), 0)


class RunToolTest(unittest.TestCase):

    def setUp(self):
        self.client = MagicMock()
        self.still_store = {}

    def test_screenshot_stores_image(self):
        self.client.get_screenshot.return_value = b'jpeg-data'

        result = run_tool(
            'screenshot',
            {},
            client=self.client,
            has_grant=False,
            still_store=self.still_store,
            session_key='test',
        )

        self.assertTrue(result['ok'])
        self.assertTrue(result.get('still_updated'))
        self.assertEqual(self.still_store['test'], b'jpeg-data')

    def test_mutating_tool_requires_grant(self):
        result = run_tool(
            'keystroke',
            {'key': 'Enter'},
            client=self.client,
            has_grant=False,
            still_store=self.still_store,
            session_key='test',
        )

        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'grant_required')

    def test_unknown_tool_returns_error(self):
        result = run_tool(
            'unknown_tool',
            {},
            client=self.client,
            has_grant=True,
            still_store=self.still_store,
            session_key='test',
        )

        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'unknown_tool')


if __name__ == '__main__':
    unittest.main()
