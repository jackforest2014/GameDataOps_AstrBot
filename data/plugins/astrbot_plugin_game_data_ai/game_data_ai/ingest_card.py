"""Feishu card for document ingest approve / reject (schema 2.0 — buttons in column_set, no action tag)."""

from __future__ import annotations

from typing import Any


def _ingest_button(
    label: str,
    *,
    document_id: str,
    trace_id: str,
    action: str,
    primary: bool = False,
) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": "primary" if primary else "default",
        "value": {
            "source": "game_data_ai",
            "action": action,
            "document_id": document_id,
            "trace_id": trace_id,
        },
    }


def build_ingest_confirm_card(
    *,
    document_id: str,
    title: str,
    trace_id: str,
) -> dict[str, Any]:
    doc_title = (title or document_id)[:120]
    approve = _ingest_button(
        "入库",
        document_id=document_id,
        trace_id=trace_id,
        action="ingest_approve",
        primary=True,
    )
    reject = _ingest_button(
        "暂不入库",
        document_id=document_id,
        trace_id=trace_id,
        action="ingest_reject",
    )
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "知识库 · 是否入库？（可选）"},
        },
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"**{doc_title}**\n\n"
                        "上方已根据文档内容返回本次分析。"
                        "若希望后续问数可长期引用该文档，可选择 **入库**；"
                        "**暂不入库** 不影响本次结果。"
                    ),
                },
                {
                    "tag": "column_set",
                    "flex_mode": "none",
                    "horizontal_spacing": "default",
                    "columns": [
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [approve],
                        },
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [reject],
                        },
                    ],
                },
            ],
        },
    }
