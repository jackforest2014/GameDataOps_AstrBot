"""Feishu card for KG mapping candidate approval (SSE: document.kg.candidates).

Each candidate is one LLM-proposed 业务名→物理列 mapping staged as a draft; the
user approves/rejects it so the semantic layer only grows under human control.
See docs/mvp/design/19-自验证闭环归因-方案设计.md §5.8.3.
"""

from __future__ import annotations

from typing import Any

_KIND_LABELS: dict[str, str] = {
    "activity": "活动",
    "billing_point": "计费点",
    "version": "版本",
    "metric": "指标",
    "segment": "分层",
}


def _kg_button(label: str, *, action: str, entity_id: str, edge_id: str, primary: bool) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": "primary" if primary else "default",
        "value": {
            "source": "game_data_ai",
            "action": action,
            "entity_id": entity_id,
            "edge_id": edge_id,
        },
    }


def _candidate_block(cand: dict[str, Any]) -> list[dict[str, Any]]:
    name = str(cand.get("name") or "").strip()
    kind = _KIND_LABELS.get(str(cand.get("kind") or ""), str(cand.get("kind") or ""))
    table = str(cand.get("table") or "")
    column = str(cand.get("column") or "")
    value = str(cand.get("value") or "")
    aliases = [str(a) for a in (cand.get("aliases") or []) if str(a).strip()]
    entity_id = str(cand.get("entity_id") or "")
    edge_id = str(cand.get("edge_id") or "")

    target = f"`{table}.{column}`"
    if value:
        target += f" = `{value}`"
    alias_line = f"\n<font color='grey'>别名：{', '.join(aliases)}</font>" if aliases else ""
    md = (
        f"**{name}**<font color='grey'>（{kind}）</font>\n"
        f"<font color='grey'>映射到</font> {target}{alias_line}"
    )
    approve = _kg_button("批准映射", action="kg_approve", entity_id=entity_id, edge_id=edge_id, primary=True)
    reject = _kg_button("忽略", action="kg_reject", entity_id=entity_id, edge_id=edge_id, primary=False)
    return [
        {"tag": "markdown", "content": md},
        {
            "tag": "column_set",
            "flex_mode": "none",
            "horizontal_spacing": "default",
            "columns": [
                {"tag": "column", "width": "weighted", "weight": 1, "elements": [approve]},
                {"tag": "column", "width": "weighted", "weight": 1, "elements": [reject]},
            ],
        },
    ]


def build_kg_candidate_card(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    elements: list[dict[str, Any]] = [
        {
            "tag": "markdown",
            "content": (
                "<font color='grey'>从刚入库的文档中识别出以下「业务术语 → 数仓列」候选映射。"
                "批准后，后续问数与自动验证可用业务名直接锚定到该列。</font>"
            ),
        }
    ]
    for i, cand in enumerate(candidates):
        if i:
            elements.append({"tag": "hr"})
        elements.extend(_candidate_block(cand))
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "violet",
            "title": {"tag": "plain_text", "content": "知识图谱 · 候选映射待确认"},
            "subtitle": {"tag": "plain_text", "content": "语义层 · 业务名→物理列"},
        },
        "body": {"elements": elements},
    }
