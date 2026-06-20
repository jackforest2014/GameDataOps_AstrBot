"""Per-chat session_id cache (design 57 A8)."""

from __future__ import annotations


def default_session_id(chat_id: str) -> str:
    chat_id = (chat_id or "").strip()
    if not chat_id:
        return ""
    return f"sess_{chat_id}"


class ChatSessionStore:
    """Maps feishu chat_id → current backend session_id."""

    def __init__(self) -> None:
        self._by_chat: dict[str, str] = {}

    def get(self, chat_id: str) -> str:
        chat_id = (chat_id or "").strip()
        if not chat_id:
            return ""
        return self._by_chat.get(chat_id) or default_session_id(chat_id)

    def update(self, chat_id: str, session_id: str | None) -> str:
        chat_id = (chat_id or "").strip()
        sid = (session_id or "").strip()
        if not chat_id:
            return sid
        if sid:
            self._by_chat[chat_id] = sid
            return sid
        return self.get(chat_id)

    def clear_mapping(self, chat_id: str) -> None:
        chat_id = (chat_id or "").strip()
        if chat_id:
            self._by_chat.pop(chat_id, None)
