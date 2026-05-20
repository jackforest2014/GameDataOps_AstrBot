"""Feishu multi-select cancel card for scheduled deliveries."""

from __future__ import annotations

from typing import Any


def build_cancel_preview_card(preview: dict[str, Any]) -> dict[str, Any]:
    token = preview.get("action_token", "")
    items = preview.get("items") or []
    empty_reason = preview.get("empty_reason", "")
    match_phrase = preview.get("match_phrase", "")

    elements: list[dict[str, Any]] = [
        {
            "tag": "markdown",
            "content": "**请选择要取消的定时推送**\n勾选后点击底部【确认取消】。未勾选的任务不受影响。",
        },
    ]
    if match_phrase:
        elements.append(
            {
                "tag": "markdown",
                "content": f"<font color='grey'>匹配词：{match_phrase}</font>",
            }
        )

    if empty_reason == "no_match":
        elements.append(
            {
                "tag": "markdown",
                "content": "未找到匹配的定时任务。可点击下方「查看全部」重新选择。",
            }
        )
        elements.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看全部"},
                "type": "default",
                "value": {
                    "source": "game_data_ai",
                    "action": "schedule_cancel_show_all",
                    "token": token,
                },
            }
        )
    else:
        options = []
        for it in items:
            label = it.get("label") or it.get("schedule_id", "")
            sub = it.get("subtitle") or ""
            text = f"{label}\n{sub}" if sub else label
            options.append(
                {
                    "text": {"tag": "plain_text", "content": text[:80]},
                    "value": it.get("schedule_id", ""),
                    "default_checked": bool(it.get("default_selected")),
                }
            )
        if options:
            elements.append(
                {
                    "tag": "checkboxes",
                    "name": "schedule_ids",
                    "options": options,
                }
            )
        elements.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "确认取消"},
                "type": "danger",
                "value": {
                    "source": "game_data_ai",
                    "action": "schedule_cancel_confirm",
                    "token": token,
                },
            }
        )
        elements.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "放弃"},
                "type": "default",
                "value": {
                    "source": "game_data_ai",
                    "action": "schedule_cancel_abort",
                    "token": token,
                },
            }
        )

    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "取消定时推送"},
            "template": "orange",
        },
        "body": {"elements": elements},
    }


def build_cancel_success_card(resp: dict[str, Any]) -> dict[str, Any]:
    cancelled = resp.get("cancelled") or []
    lines = [f"· {c.get('label', c.get('schedule_id', ''))}" for c in cancelled]
    body = "\n".join(lines) if lines else "（无）"
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "已取消定时推送"},
            "template": "green",
        },
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "content": f"已取消 **{resp.get('cancelled_count', 0)}** 项：\n{body}",
                }
            ]
        },
    }


def build_schedule_created_card(resp: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "定时推送已创建"},
            "template": "blue",
        },
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"**{resp.get('label', '')}**\n"
                        f"下次执行：{resp.get('next_run_at', '')}\n"
                        f"任务 ID：`{resp.get('schedule_id', '')}`"
                    ),
                }
            ]
        },
    }
