"""Feishu card JSON builders (schema 2.0 — no motion/action/note)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from astrbot.api import logger


def _feedback_button(
    label: str,
    fb_type: str,
    trace_id: str,
    session_id: str,
    template_id: str,
    *,
    primary: bool = False,
) -> dict[str, Any]:
    value = {
        "source": "game_data_ai",
        "version": "v1",
        "action": "submit_feedback",
        "trace_id": trace_id,
        "session_id": session_id,
        "feedback_type": fb_type,
        "client_action_id": f"act_{uuid.uuid4().hex[:12]}",
        "template_id": template_id,
    }
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": "primary" if primary else "default",
        "value": value,
    }


def _metric_columns(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tiles = metrics[:4]
    if not tiles:
        return []

    def cell(m: dict[str, Any]) -> dict[str, Any]:
        label = m.get("label", "")
        value = m.get("value", "")
        delta = m.get("delta", "")
        trend = m.get("trend", "")
        delta_line = ""
        if delta:
            arrow = "↑" if trend == "up" else ("↓" if trend == "down" else "")
            color = "green" if trend == "up" else ("red" if trend == "down" else "grey")
            delta_line = f"\n<font color='{color}'>{arrow}{delta}</font>"
        md = f"**{label}**\n<font color='grey'>{value}</font>{delta_line}"
        return {
            "tag": "column",
            "width": "weighted",
            "weight": 1,
            "elements": [{"tag": "markdown", "content": md}],
        }

    rows: list[dict[str, Any]] = []
    for i in range(0, len(tiles), 2):
        pair = tiles[i : i + 2]
        rows.append(
            {
                "tag": "column_set",
                "flex_mode": "bisect",
                "horizontal_spacing": "default",
                "columns": [cell(m) for m in pair],
            }
        )
    return rows


def _chart_native_element(series: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Feishu 原生 chart 组件（VChart），PC/移动端条形长度一致。"""
    if not series:
        return None
    values = []
    for p in series:
        day = p.get("day_label") or f"活动第{p.get('day_index', '?')}天"
        date = p.get("date", "")
        label = f"{date} · {day}" if date else day
        values.append(
            {
                "label": label,
                "revenue": float(p.get("revenue_wan") or 0),
            }
        )
    return {
        "tag": "chart",
        "element_id": "gd_daily_trend",
        "aspect_ratio": "4:3",
        "color_theme": "brand",
        "preview": True,
        "chart_spec": {
            "type": "bar",
            "title": {"text": "活动期高付费流水（万元）"},
            "data": {"values": values},
            "direction": "horizontal",
            "xField": "revenue",
            "yField": "label",
            "axes": [
                {
                    "orient": "bottom",
                    "title": {"visible": True, "text": "流水（万元）"},
                }
            ],
            "label": {"visible": True},
        },
    }


def _chart_series_data_table(series: list[dict[str, Any]]) -> str:
    """纯数字明细表（无 Unicode 横条，避免手机端表格渲染异常）。"""
    if not series:
        return ""
    mx = max((float(p.get("revenue_wan") or 0) for p in series), default=1.0) or 1.0
    lines = [
        "**明细数据**",
        "<font color='grey'>占峰值 = 当日流水 ÷ 活动期最高日流水</font>",
        "",
        "| 天数 | 日期 | 流水(万) | 占峰值 |",
        "| --- | --- | ---: | ---: |",
    ]
    for p in series:
        day = p.get("day_label") or f"活动第{p.get('day_index', '?')}天"
        date = p.get("date", "")
        rev = float(p.get("revenue_wan") or 0)
        pct = int(rev / mx * 100)
        lines.append(f"| {day} | {date} | **{rev:.1f}** | {pct}% |")
    peak = max(series, key=lambda x: float(x.get("revenue_wan") or 0))
    lines.append("")
    lines.append(
        f"<font color='grey'>峰值：{peak.get('day_label')}（{peak.get('date')}）"
        f" · {float(peak.get('revenue_wan', 0)):.1f} 万元</font>"
    )
    return "\n".join(lines)


def _table_mode_hint(series: list[dict[str, Any]]) -> str:
    if not series:
        return ""
    peak = max(series, key=lambda x: float(x.get("revenue_wan") or 0))
    return (
        f"<font color='grey'>活动期共 {len(series)} 天；"
        f"峰值在 {peak.get('day_label')}（{peak.get('date')}），"
        f"{float(peak.get('revenue_wan', 0)):.1f} 万元。"
        f"发送「用图形展示」可查看按日趋势图。</font>"
    )


def log_card_build(payload: dict[str, Any], card: dict[str, Any]) -> None:
    answer = payload.get("answer") or {}
    rendering = payload.get("rendering") or {}
    header = card.get("header") or {}
    body = card.get("body") or {}
    elements = body.get("elements") or []
    logger.info(
        "[game_data_ai] card.build "
        f"trace={payload.get('trace_id')} "
        f"mode={rendering.get('preferred', 'table')} "
        f"title={answer.get('title', '')} "
        f"metrics={len(answer.get('metrics') or [])} "
        f"chart_points={len(answer.get('chart_series') or [])} "
        f"elements={len(elements)} "
        f"header_template={header.get('template', 'blue')}"
    )
    logger.info(
        "[game_data_ai] card.answer "
        f"summary={answer.get('summary', '')[:120]} "
        f"facts={answer.get('facts') or []} "
        f"chart_series={answer.get('chart_series') or []}"
    )


def build_result_card_json(payload: dict[str, Any]) -> dict[str, Any]:
    answer = payload.get("answer") or {}
    rendering = payload.get("rendering") or {}
    trace_id = payload.get("trace_id", "")
    session_id = payload.get("session_id", "")
    template_id = answer.get("template_id", "")
    preferred = rendering.get("preferred", "table")
    facts = answer.get("facts") or []
    metrics = answer.get("metrics") or []
    chart_series = answer.get("chart_series") or []

    summary = answer.get("summary", "")
    facts_md = "\n".join(f"• {f}" for f in facts[:5])
    trace_block = (
        f"**追溯信息**\n"
        f"trace `{trace_id}` · 模板 `{template_id}`\n"
        f"口径 {answer.get('methodology', '')}\n"
        f"SQL digest `{answer.get('sql_digest', '')}`"
    )

    is_chart = preferred == "chart"
    elements: list[dict[str, Any]] = [
        {"tag": "markdown", "content": f"**摘要**\n{summary or '（无摘要）'}"},
    ]

    if is_chart:
        # 图表视图：原生 chart（手机/PC 一致）+ 数字明细表
        if chart_series:
            elements.append(
                {
                    "tag": "markdown",
                    "content": (
                        "**活动期高付费流水 · 按日趋势**\n"
                        "<font color='grey'>下图横条长度表示当日高付费流水（万元），"
                        "可在手机端点击全屏查看。</font>"
                    ),
                }
            )
            chart_el = _chart_native_element(chart_series)
            if chart_el:
                elements.append(chart_el)
            elements.append(
                {"tag": "markdown", "content": _chart_series_data_table(chart_series)}
            )
        compact = metrics[:2]
        elements.extend(_metric_columns(compact))
        if facts_md:
            elements.append(
                {
                    "tag": "markdown",
                    "content": f"**结论摘要**\n{facts_md}",
                }
            )
    else:
        # 表格视图：完整 KPI 格 + 关键事实，不展示易误解的条形图
        elements.extend(_metric_columns(metrics))
        if facts_md:
            elements.append({"tag": "markdown", "content": f"**关键事实**\n{facts_md}"})
        hint = _table_mode_hint(chart_series)
        if hint:
            elements.append({"tag": "markdown", "content": hint})

    elements.append({"tag": "hr"})
    elements.append({"tag": "markdown", "content": trace_block})
    elements.append(
        {
            "tag": "markdown",
            "content": (
                "<font color='grey'>反馈与沉淀为独立动作：可先点「有用」，"
                "再点「沉淀模板候选」。</font>"
            ),
        }
    )

    buttons = [
        _feedback_button("有用", "good_case", trace_id, session_id, template_id, primary=True),
        _feedback_button("有问题", "bad_case", trace_id, session_id, template_id),
        _feedback_button(
            "沉淀模板候选", "sql_template_candidate", trace_id, session_id, template_id
        ),
    ]
    elements.append(
        {
            "tag": "column_set",
            "flex_mode": "trisect",
            "horizontal_spacing": "default",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [buttons[0]],
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [buttons[1]],
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [buttons[2]],
                },
            ],
        }
    )

    card = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": answer.get("title", "分析结果")},
            "subtitle": {
                "tag": "plain_text",
                "content": "图表视图 · 按日趋势" if is_chart else "数据报表 · 指标总览",
            },
            "template": "green" if is_chart else "blue",
        },
        "body": {"elements": elements},
    }
    log_card_build(payload, card)
    return card


def build_denied_plain(error: dict[str, Any] | None) -> str:
    if not error:
        return "请求被拒绝。"
    return f"【无法查询】{error.get('code', 'denied')}\n{error.get('message', '')}"


def build_progress_plain() -> str:
    return "已收到，正在分析中，请稍候…"


def build_p2p_only_plain() -> str:
    return "【当前仅支持飞书单聊】\n请在飞书应用中与机器人单聊提问，群聊暂不支持问数（p2p_only）。"


def card_json_to_plain_fallback(card: dict[str, Any]) -> str:
    return json.dumps(card, ensure_ascii=False, indent=2)[:3500]
