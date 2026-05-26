"""Feishu card for document ingest approve / reject (v1.1)."""

from __future__ import annotations

from typing import Any


def build_ingest_confirm_card(
    *,
    document_id: str,
    title: str,
    trace_id: str,
) -> dict[str, Any]:
    doc_title = (title or document_id)[:120]
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "知识库 · 是否入库？"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"**{doc_title}**\n\n"
                    "解析已完成。写入知识库后，问数可引用该文档内容。\n"
                    "请选择 **入库** 或 **暂不入库**（仍可继续本次问数）。"
                ),
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "入库"},
                        "type": "primary",
                        "value": {
                            "source": "game_data_ai",
                            "action": "ingest_approve",
                            "document_id": document_id,
                            "trace_id": trace_id,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "不入库"},
                        "type": "default",
                        "value": {
                            "source": "game_data_ai",
                            "action": "ingest_reject",
                            "document_id": document_id,
                            "trace_id": trace_id,
                        },
                    },
                ],
            },
        ],
    }
