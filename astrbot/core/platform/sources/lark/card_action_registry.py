"""Registry for Feishu card.action.trigger handlers (plugins register here)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lark_oapi.event.callback.model.p2_card_action_trigger import (
        P2CardActionTrigger,
        P2CardActionTriggerResponse,
    )

CardActionHandler = Callable[
    ["P2CardActionTrigger"], Awaitable["P2CardActionTriggerResponse | None"]
]

_handlers: list[CardActionHandler] = []


def register_card_action_handler(
    handler: CardActionHandler,
) -> CardActionHandler:
    _handlers.append(handler)
    return handler


def clear_card_action_handlers() -> None:
    _handlers.clear()


async def dispatch_card_action(
    event: P2CardActionTrigger,
) -> P2CardActionTriggerResponse | None:
    for handler in _handlers:
        resp = await handler(event)
        if resp is not None:
            return resp
    return None
