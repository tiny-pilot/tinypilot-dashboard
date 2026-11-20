"""Unit tests for assistant device tools."""

from unittest.mock import MagicMock

from app.assistant.agent import clear_session_data_for_tests
from app.assistant.tools import run_tool


def test_click_rejects_non_numeric_coordinates():
    client = MagicMock()
    still_store: dict = {}
    clear_session_data_for_tests()
    result = run_tool(
        'click',
        {'relativeX': 'nope', 'relativeY': 0.5},
        client=client,
        has_grant=True,
        still_store=still_store,
        session_key='test',
    )
    assert result == {'ok': False, 'error': 'invalid_arguments'}
    client.post_v1.assert_not_called()