"""Resolve dialog route via platform LLM API."""

from __future__ import annotations

import os
import time
from typing import Any

from astrbot.api import logger

from .attachments import build_attachments
from .routing import detect_route, is_date_follow_up, is_display_refinement


async def resolve_route(
    client: Any,
    text: str,
    *,
    user_id: str,
    chat_id: str,
    message_id: str,
    active_data_chats: dict[str, float] | None = None,
) -> str:
    """Return query | schedule | cancel | list_schedules | ignore."""
    t = (text or "").strip()
    if not t:
        return "ignore"

    # Feishu doc Q&A must use chat/messages (attachments), never LLM route=ignore.
    if build_attachments(t):
        return "query"

    use_llm = os.getenv("GAME_DATA_AI_ROUTE_USE_LLM", "true").lower() not in (
        "0",
        "false",
        "no",
    )
    if use_llm and client is not None:
        try:
            payload = await client.classify_route(
                feishu_user_id=user_id,
                feishu_chat_id=chat_id,
                feishu_message_id=message_id or f"route_{int(time.time())}",
                question=t,
                session_id=f"sess_{chat_id}" if chat_id else None,
            )
            route = (payload.get("route") or "ignore").strip().lower()
            if route in ("query", "schedule", "cancel", "list_schedules", "ignore"):
                return route
        except Exception as e:
            logger.warning(f"[game_data_ai] route.api_failed fallback=keywords: {e}")

    # Keyword fallback + active session date/display follow-ups
    if detect_route(t) != "ignore":
        return detect_route(t)
    if chat_id and active_data_chats:
        ts = active_data_chats.get(chat_id)
        if ts and time.time() - ts <= 30 * 60:
            if is_date_follow_up(t) or is_display_refinement(t):
                return "query"
    return "ignore"
