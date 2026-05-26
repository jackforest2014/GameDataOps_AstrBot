"""Ensure v1.1 API paths are used."""

import inspect

from game_data_ai.client import GameDataAIClient


def test_chat_messages_uses_v1_path():
    src = inspect.getsource(GameDataAIClient.chat_messages)
    assert "/api/v1/chat/messages" in src
    assert "/api/v1/query/metric" not in src
