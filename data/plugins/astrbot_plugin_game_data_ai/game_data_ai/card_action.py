"""Feishu card.action.trigger handler for game_data_ai feedback buttons."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot.api import logger
from astrbot.core.platform.sources.lark.card_action_registry import (
    clear_card_action_handlers,
    register_card_action_handler,
)

if TYPE_CHECKING:
    from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTrigger

    from .client import GameDataAIClient


def _action_value(event: P2CardActionTrigger) -> dict[str, Any]:
    try:
        if event.event and event.event.action and event.event.action.value:
            val = event.event.action.value
            return val if isinstance(val, dict) else {}
    except Exception:
        pass
    return {}


def register_feedback_card_handler(client: GameDataAIClient) -> None:
    """Register handler; call once per plugin load (clears previous handlers)."""
    clear_card_action_handlers()

    @register_card_action_handler
    async def on_game_data_ai_card_action(
        event: P2CardActionTrigger,
    ) -> None:
        value = _action_value(event)
        if value.get("source") != "game_data_ai":
            return None
        if value.get("action") != "submit_feedback":
            logger.warning(f"[game_data_ai] 未知卡片动作: {value}")
            return None

        operator = event.event.operator if event.event else None
        feishu_user_id = (operator.open_id if operator else None) or ""
        ctx = event.event.context if event.event else None
        chat_id = (ctx.open_chat_id if ctx else None) or ""

        try:
            result = await client.submit_feedback(
                trace_id=value.get("trace_id", ""),
                session_id=value.get("session_id", ""),
                feishu_user_id=feishu_user_id,
                feishu_chat_id=chat_id,
                feedback_type=value.get("feedback_type", ""),
                template_id=value.get("template_id", ""),
                client_action_id=value.get("client_action_id", ""),
            )
            logger.info(
                f"[game_data_ai] feedback.submit status={result.get('status')} "
                f"trace={value.get('trace_id')} type={value.get('feedback_type')} "
                f"feedback_id={result.get('feedback_id')} "
                f"msg={result.get('display_message')}"
            )
            if result.get("error"):
                err = result["error"]
                logger.warning(
                    f"[game_data_ai] feedback.error code={err.get('code')} "
                    f"msg={err.get('message')}"
                )
        except Exception as e:
            logger.error(f"[game_data_ai] feedback.submit failed: {e}", exc_info=True)
        return None
