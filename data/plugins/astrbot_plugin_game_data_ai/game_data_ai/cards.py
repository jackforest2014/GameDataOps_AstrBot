"""Feishu card JSON builders (schema 2.0 — no motion/action/note)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from astrbot.api import logger

from game_data_ai.charts import build_charts_elements


_PROBLEM_TYPE_LABELS: dict[str, str] = {
    "metric_scope_wrong": "口径不对",
    "time_range_wrong": "时间范围不对",
    "entity_recognition_wrong": "项目/活动识别不对",
    "metric_selection_wrong": "指标选择不对",
    "sql_logic_wrong": "SQL/模板逻辑有问题",
    "interpretation_wrong": "结论解释有问题",
    "format_wrong": "展示格式不符合预期",
    "data_quality_issue": "数据质量/缺失/异常",
    "other": "其他",
}


def _feedback_button(
    label: str,
    fb_type: str,
    trace_id: str,
    session_id: str,
    template_id: str,
    *,
    primary: bool = False,
    problem_type: str = "",
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
    if problem_type:
        value["problem_type"] = problem_type
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": "primary" if primary else "default",
        "value": value,
    }


def build_bad_case_correction_card(
    *,
    trace_id: str,
    session_id: str,
    template_id: str,
    problem_types: list[str],
) -> dict[str, Any]:
    """TC-10：Bad Case 追问卡片（问题类型按钮）。"""
    buttons: list[dict[str, Any]] = []
    for pt in problem_types[:6]:
        label = _PROBLEM_TYPE_LABELS.get(pt, pt)
        buttons.append(
            _feedback_button(
                label,
                "bad_case",
                trace_id,
                session_id,
                template_id,
                problem_type=pt,
            )
        )
    rows: list[dict[str, Any]] = []
    for i in range(0, len(buttons), 2):
        pair = buttons[i : i + 2]
        cols = [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "elements": [btn],
            }
            for btn in pair
        ]
        rows.append(
            {
                "tag": "column_set",
                "flex_mode": "none",
                "horizontal_spacing": "default",
                "columns": cols,
            }
        )

    elements: list[dict[str, Any]] = [
        {
            "tag": "markdown",
            "content": "**请补充：本次分析哪里有问题？**\n点击下方类型即可提交（无需再打字）。",
        },
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": f"<font color='grey'>trace: {trace_id}</font>",
        },
    ]
    elements.extend(rows)

    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "问题反馈 · 请选择类型"},
            "subtitle": {"tag": "plain_text", "content": "Bad Case 追问"},
            "template": "orange",
        },
        "body": {"elements": elements},
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


def _lineage_rag_block(citations: list[dict[str, Any]]) -> str:
    """论文式尾注引用区。

    飞书卡片 markdown 仅识别 font 的 red/green/grey 与枚举色名（如 wathet、blue），
    不支持 #RRGGBB；用 text_tag + 引用块 + wathet 与正文区分。
    """
    if not citations:
        return ""
    lines = [
        "<text_tag color='wathet'>引用内容</text_tag>",
        "<font color='grey'>以下摘录自知识库文档，供口径与结论对照，非本次 SQL 查询结果。</font>",
        "",
    ]
    for idx, c in enumerate(citations[:3], start=1):
        title = c.get("document_title", "未命名文档")
        proj = c.get("project_id", "")
        loc = c.get("locator", "")
        snippet = (c.get("snippet") or "").strip()
        if len(snippet) > 160:
            snippet = snippet[:160] + "…"
        body = f"**[{idx}]** {title}."
        if snippet:
            body += f" 「{snippet}」"
        meta = f"（{proj} · {loc}）" if loc else f"（{proj}）"
        # 引用块：左侧缩进；摘录用 wathet（天蓝），定位信息用 grey
        lines.append(f"> <font color='wathet'>{body}</font>")
        if meta:
            lines.append(f"> <font color='grey'>{meta}</font>")
    return "\n".join(lines)


def _lineage_experience_block(exp: dict[str, Any] | None) -> str:
    if not exp:
        return ""
    name = exp.get("display_name", "")
    aid = exp.get("asset_id", "")
    ver = exp.get("version", "")
    ver_part = f" · v{ver}" if ver else ""
    return (
        f"**经验复用**\n"
        f"<font color='green'>已复用经验</font>：**{name}**（`{aid}`{ver_part}）"
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
        f"chart_series={answer.get('chart_series') or []} "
        f"rag_citations={len(answer.get('rag_citations') or [])} "
        f"experience_reuse={bool(answer.get('experience_reuse'))}"
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
    charts = answer.get("charts") or []

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
        # 图表视图：优先 answer.charts[]（第六批），否则 chart_series 兼容
        if charts:
            elements.append(
                {
                    "tag": "markdown",
                    "content": (
                        "**数据图表**\n"
                        "<font color='grey'>以下为平台 Catalog 渲染的 VChart 图表，"
                        "可在手机端点击全屏查看。</font>"
                    ),
                }
            )
            elements.extend(build_charts_elements(charts))
        elif chart_series:
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

    rag_md = _lineage_rag_block(answer.get("rag_citations") or [])
    if rag_md:
        elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": rag_md})
    exp_md = _lineage_experience_block(answer.get("experience_reuse"))
    if exp_md:
        elements.append({"tag": "markdown", "content": exp_md})
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
