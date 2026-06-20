"""Feishu interactive card for overseas dashboard scope clarification (design 57 B6)."""

from __future__ import annotations

from typing import Any


def _button(text: str, btn_type: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": text},
        "type": btn_type,
        "value": value,
    }


def build_overseas_scope_clarify_card(payload: dict[str, Any]) -> dict[str, Any]:
    clarification = payload.get("clarification") or {}
    trace_id = str(payload.get("trace_id") or "")
    session_id = str(payload.get("session_id") or "")
    prompt = str(clarification.get("prompt") or "请选择海外大盘的数据范围")
    options = clarification.get("options") or []

    elements: list[dict[str, Any]] = [
        {"tag": "markdown", "content": f"**{prompt}**"},
    ]
    buttons: list[dict[str, Any]] = []
    for opt in options[:3]:
        opt_id = str(opt.get("id") or "")
        label = str(opt.get("label") or opt_id)
        if not opt_id:
            continue
        if opt.get("disabled"):
            elements.append(
                {
                    "tag": "markdown",
                    "content": f"<font color='grey'>~~{label}~~（不可选）</font>",
                }
            )
            continue
        buttons.append(
            _button(
                label,
                "primary" if opt_id.endswith("_project") else "default",
                {
                    "source": "game_data_ai",
                    "action": "overseas_scope_confirm",
                    "option_id": opt_id,
                    "trace_id": trace_id,
                    "session_id": session_id,
                    "feishu_chat_id": payload.get("feishu_chat_id") or "",
                },
            )
        )
    if buttons:
        elements.append(
            {
                "tag": "column_set",
                "flex_mode": "none",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [btn],
                    }
                    for btn in buttons
                ],
            }
        )
    elements.append(
        {
            "tag": "markdown",
            "content": "<font color='grey'>也可直接回复选项文字。</font>",
        }
    )
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "请选择数据范围"},
            "template": "blue",
        },
        "body": {"elements": elements},
    }
