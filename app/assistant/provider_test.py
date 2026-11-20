"""Tests for the assistant provider."""

import unittest
import uuid

from app.assistant.provider import ProviderEvent
from app.assistant.provider import ToolCall
from app.assistant.provider import _attach_images


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


class AttachImagesTest(unittest.TestCase):

    def test_appends_image_as_user_message(self):
        messages = [{'role': 'user', 'content': 'Hello'}]
        images = [b'fake-jpeg-data']
        result = _attach_images(messages, images)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], messages[0])
        self.assertEqual(result[1]['role'], 'user')
        self.assertIsInstance(result[1]['content'], list)
        self.assertEqual(result[1]['content'][0]['type'], 'text')
        self.assertEqual(result[1]['content'][1]['type'], 'image_url')

    def test_empty_images_returns_original(self):
        messages = [{'role': 'user', 'content': 'Hello'}]
        result = _attach_images(messages, [])
        self.assertEqual(result, messages)


class FakeProviderTest(unittest.TestCase):

    def test_returns_screenshot_tool_on_first_call(self):
        provider = FakeProvider()
        messages = [{'role': 'user', 'content': 'What do you see?'}]
        events = list(provider.complete(messages, []))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, 'tool_call')
        self.assertEqual(events[0].tool_call.name, 'screenshot')

    def test_returns_text_after_tool_result(self):
        provider = FakeProvider()
        messages = [
            {'role': 'user', 'content': 'What do you see?'},
            {'role': 'tool', 'tool_call_id': 'x', 'content': '{}'},
        ]
        events = list(provider.complete(messages, []))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, 'text')
        self.assertEqual(events[0].text, 'Done.')


if __name__ == '__main__':
    unittest.main()
