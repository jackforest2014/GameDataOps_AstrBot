"""Feishu multi-select cancel card for scheduled deliveries."""

from __future__ import annotations

from typing import Any


def _button(text: str, btn_type: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": text},
        "type": btn_type,
        "value": value,
    }


def build_cancel_preview_card(preview: dict[str, Any]) -> dict[str, Any]:
    # 用「每个任务一个按钮」的形态，而不是 checkboxes —— 飞书部分版本不支持
    # `tag: checkboxes`（返回 10002 not support tag: checkboxes），按钮则全版本可用。
    # 点某个任务的【取消此项】即删除该任务；【取消全部】携带全部 id 一次性取消。
    token = preview.get("action_token", "")
    items = preview.get("items") or []
    empty_reason = preview.get("empty_reason", "")
    match_phrase = preview.get("match_phrase", "")

    elements: list[dict[str, Any]] = [
        {
            "tag": "markdown",
            "content": "**请选择要取消的定时推送**\n点击对应任务的【取消此项】即可删除；或点【取消全部】。其余任务不受影响。",
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
            _button(
                "查看全部",
                "default",
                {
                    "source": "game_data_ai",
                    "action": "schedule_cancel_show_all",
                    "token": token,
                },
            )
        )
    else:
        all_ids: list[str] = []
        for it in items:
            sid = it.get("schedule_id", "")
            if not sid:
                continue
            all_ids.append(sid)
            label = (it.get("label") or sid).strip()
            sub = it.get("subtitle") or ""
            info = f"**{label}**"
            if sub:
                info += f"\n<font color='grey'>{sub}</font>"
            elements.append({"tag": "markdown", "content": info})
            elements.append(
                _button(
                    f"取消此项：{label[:30]}",
                    "danger",
                    {
                        "source": "game_data_ai",
                        "action": "schedule_cancel_confirm",
                        "token": token,
                        "schedule_id": sid,
                    },
                )
            )
        if len(all_ids) > 1:
            elements.append({"tag": "hr"})
            elements.append(
                _button(
                    "取消全部",
                    "danger",
                    {
                        "source": "game_data_ai",
                        "action": "schedule_cancel_confirm",
                        "token": token,
                        "schedule_ids": all_ids,
                    },
                )
            )
        elements.append(
            _button(
                "放弃",
                "default",
                {
                    "source": "game_data_ai",
                    "action": "schedule_cancel_abort",
                    "token": token,
                },
            )
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
