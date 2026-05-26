"""Feishu card.action.trigger handlers for feedback and schedule cancel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from astrbot.api import logger
from astrbot.core.platform.sources.lark.card_action_registry import (
    clear_card_action_handlers,
    register_card_action_handler,
)

from .cards import build_bad_case_correction_card
from .schedule_cancel_card import build_cancel_preview_card, build_cancel_success_card

if TYPE_CHECKING:
    from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTrigger
    from .client import GameDataAIClient

SendCardFn = Callable[[Any, dict[str, Any], str], Awaitable[None]]


def _action_value(event: P2CardActionTrigger) -> dict[str, Any]:
    try:
        if event.event and event.event.action and event.event.action.value:
            val = event.event.action.value
            return val if isinstance(val, dict) else {}
    except Exception:
        pass
    return {}


def _form_value(event: P2CardActionTrigger) -> dict[str, Any]:
    try:
        action = event.event.action if event.event else None
        if action is None:
            return {}
        fv = getattr(action, "form_value", None) or getattr(action, "formValue", None)
        return fv if isinstance(fv, dict) else {}
    except Exception:
        return {}


def register_feedback_card_handler(
    client: GameDataAIClient,
    send_card: SendCardFn | None = None,
    *,
    cancel_candidates: dict[str, list[str]] | None = None,
) -> None:
    """Register handler; call once per plugin load."""
    clear_card_action_handlers()
    store = cancel_candidates if cancel_candidates is not None else {}

    @register_card_action_handler
    async def on_game_data_ai_card_action(event: P2CardActionTrigger) -> None:
        value = _action_value(event)
        if value.get("source") != "game_data_ai":
            return None

        action = value.get("action", "")
        operator = event.event.operator if event.event else None
        feishu_user_id = (operator.open_id if operator else None) or ""
        ctx = event.event.context if event.event else None
        chat_id = (ctx.open_chat_id if ctx else None) or ""

        if action == "submit_feedback":
            await _handle_feedback(client, send_card, event, value, feishu_user_id, chat_id)
            return None

        if action in ("ingest_approve", "ingest_reject"):
            await _handle_ingest_decision(
                client, event, value, feishu_user_id, chat_id
            )
            return None

        if action in (
            "schedule_cancel_confirm",
            "schedule_cancel_abort",
            "schedule_cancel_show_all",
        ):
            await _handle_schedule_cancel(
                client, send_card, event, value, feishu_user_id, chat_id, store
            )
        return None


async def _handle_ingest_decision(
    client: GameDataAIClient,
    event: P2CardActionTrigger,
    value: dict[str, Any],
    feishu_user_id: str,
    chat_id: str,
) -> None:
    document_id = value.get("document_id", "")
    trace_id = value.get("trace_id", "")
    decision = "approve" if value.get("action") == "ingest_approve" else "reject"
    msg_id = ""
    try:
        ctx = event.event.context if event.event else None
        msg_id = getattr(ctx, "open_message_id", None) or f"ingest_{trace_id[:12]}"
    except Exception:
        msg_id = f"ingest_{trace_id[:12]}"
    try:
        resp = await client.ingest_decision(
            document_id=document_id,
            feishu_user_id=feishu_user_id,
            feishu_chat_id=chat_id,
            feishu_message_id=msg_id,
            trace_id=trace_id,
            decision=decision,
        )
        logger.info(
            f"[game_data_ai] ingest.decision doc={document_id} "
            f"decision={decision} resp={resp}"
        )
    except Exception as e:
        logger.error(f"[game_data_ai] ingest.decision failed: {e}", exc_info=True)


async def _handle_feedback(
    client: GameDataAIClient,
    send_card: SendCardFn | None,
    event: P2CardActionTrigger,
    value: dict[str, Any],
    feishu_user_id: str,
    chat_id: str,
) -> None:
    try:
        result = await client.submit_feedback(
            trace_id=value.get("trace_id", ""),
            session_id=value.get("session_id", ""),
            feishu_user_id=feishu_user_id,
            feishu_chat_id=chat_id,
            feedback_type=value.get("feedback_type", ""),
            template_id=value.get("template_id", ""),
            client_action_id=value.get("client_action_id", ""),
            problem_type=value.get("problem_type", ""),
        )
        if (
            result.get("status") == "correction_required"
            and send_card is not None
            and chat_id
        ):
            card = build_bad_case_correction_card(
                trace_id=value.get("trace_id", ""),
                session_id=value.get("session_id", ""),
                template_id=value.get("template_id", ""),
                problem_types=result.get("problem_types") or [],
            )
            await send_card(event, card, chat_id)
    except Exception as e:
        logger.error(f"[game_data_ai] feedback.submit failed: {e}", exc_info=True)


async def _handle_schedule_cancel(
    client: GameDataAIClient,
    send_card: SendCardFn | None,
    event: P2CardActionTrigger,
    value: dict[str, Any],
    feishu_user_id: str,
    chat_id: str,
    store: dict[str, list[str]],
) -> None:
    action = value.get("action", "")
    token = value.get("token", "")

    if action == "schedule_cancel_abort":
        logger.info("[game_data_ai] schedule.cancel_abort")
        return

    if action == "schedule_cancel_show_all" and send_card and chat_id:
        preview = await client.cancel_preview(
            feishu_user_id=feishu_user_id,
            feishu_chat_id=chat_id,
            feishu_message_id=f"show_all_{token}",
            mode="vague",
        )
        store[token] = [it.get("schedule_id", "") for it in preview.get("items") or []]
        await send_card(event, build_cancel_preview_card(preview), chat_id)
        return

    if action != "schedule_cancel_confirm":
        return

    form = _form_value(event)
    raw_ids = form.get("schedule_ids") or form.get("Schedule_ids") or []
    if isinstance(raw_ids, str):
        schedule_ids = [raw_ids]
    else:
        schedule_ids = list(raw_ids)
    if not schedule_ids and token in store:
        schedule_ids = list(store[token])

    if not schedule_ids:
        logger.warning("[game_data_ai] schedule.cancel_confirm empty selection")
        return

    try:
        resp = await client.cancel_confirm(
            feishu_user_id=feishu_user_id,
            feishu_chat_id=chat_id,
            feishu_message_id=f"confirm_{token}",
            action_token=token,
            schedule_ids=schedule_ids,
        )
        if send_card and chat_id:
            await send_card(event, build_cancel_success_card(resp), chat_id)
    except Exception as e:
        logger.error(f"[game_data_ai] schedule.cancel_confirm failed: {e}", exc_info=True)
