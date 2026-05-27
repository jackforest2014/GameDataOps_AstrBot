"""Feishu OAuth prompt card (schema 2.0, cardkit-compatible)."""

from __future__ import annotations

from typing import Any


def build_feishu_auth_card_json(*, auth_url: str) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "需要飞书文档授权"},
            "subtitle": {"tag": "plain_text", "content": "完成授权后可继续解析文档"},
        },
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        "访问该文档需要你的飞书账号授权。\n\n"
                        f"请在浏览器打开并完成授权：\n{auth_url}\n\n"
                        "完成后回到本对话重新发送文档链接。"
                    ),
                },
            ],
        },
    }
