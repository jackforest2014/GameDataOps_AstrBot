"""飞书 session 空闲结束系统提示卡片（schema 2.0，与问数结果卡一致）。"""

from __future__ import annotations

from typing import Any


def build_session_closed_card_json(*, message: str, idle_minutes: int) -> dict[str, Any]:
    """灰色 header + 灰色 markdown 正文，区别于蓝色/绿色问数结果卡。"""
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "系统提示"},
            "subtitle": {
                "tag": "plain_text",
                "content": f"超过 {idle_minutes} 分钟无新消息",
            },
            "template": "grey",
        },
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "content": f"**{message}**",
                },
                {
                    "tag": "markdown",
                    "content": (
                        "<font color='grey'>"
                        "本条为会话状态提示（非问数结果），已写入平台 session 记录。"
                        "</font>"
                    ),
                },
            ],
        },
    }
