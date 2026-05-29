"""Feishu card JSON builders (schema 2.0 — no motion/action/note)."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from astrbot.api import logger

from game_data_ai.charts import (
    annotate_first_chart_legend,
    build_charts_elements,
    is_week_compare_legend_chart,
    panel_has_week_compare_legend,
)


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


def _daily_pay_table(rows: list[dict[str, Any]], *, title: str = "**每日明细**") -> str:
    """多维每日付费明细（平台 answer.daily_rows）。"""
    if not rows:
        return ""
    lines = [
        title,
        "<font color='grey'>金额：万元；付费率/溢价/留存：%；溢价=(付费笔数-人数)÷人数×100</font>",
        "",
        "| 日期 | 流水(万) | 人数 | 付费率 | ARPPU | ARPU | 付费次数溢价 | 付费留存 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        date = r.get("date", "")
        rev = float(r.get("revenue_wan") or 0)
        payers = r.get("payers")
        pay_rate = r.get("pay_rate_pct")
        arppu = r.get("arppu")
        arpu = r.get("arpu")
        rep = r.get("same_day_repurchase_pct")
        ret = r.get("pay_retention_1d_pct")

        def _cell(v: Any, fmt: str = "") -> str:
            if v is None or v == "":
                return "—"
            if fmt:
                return fmt.format(round(float(v), 2) if isinstance(v, (int, float)) else v)
            return str(v)

        lines.append(
            "| {date} | **{rev:.2f}** | {payers} | {pr} | {arppu} | {arpu} | {rep} | {ret} |".format(
                date=date,
                rev=rev,
                payers=_cell(payers, "{:.2f}"),
                pr=_cell(pay_rate, "{:.2f}%"),
                arppu=_cell(arppu, "{:.2f}"),
                arpu=_cell(arpu, "{:.2f}"),
                rep=_cell(rep, "{:.2f}%"),
                ret=_cell(ret, "{:.2f}%"),
            )
        )
    return "\n".join(lines)


def _daily_pay_tables_by_period(rows: list[dict[str, Any]]) -> list[str]:
    """按 PDF 示例拆 P1 / P2 两张日表。"""
    p1 = [r for r in rows if r.get("period") in ("近一周", "P1")]
    p2 = [r for r in rows if r.get("period") in ("前一周", "P2")]
    blocks: list[str] = []
    if p1:
        blocks.append(_daily_pay_table(p1, title="**表1 · P1（近一周）每日明细**"))
    if p2:
        blocks.append(_daily_pay_table(p2, title="**表2 · P2（前一周）每日明细**"))
    if not blocks and rows:
        blocks.append(_daily_pay_table(rows))
    return blocks


def _is_pay_weekly_sections(sections: list[dict[str, Any]]) -> bool:
    return any(
        s.get("stage_index") == 2 and "周维度" in (s.get("title") or "")
        for s in sections
    )


# 单张飞书卡片内 VChart 过多易触发 2200；超出时拆为多张卡片（关系紧密的内容仍同卡）
MAX_CHARTS_PER_CARD = 4


def _count_chart_elements(elements: list[dict[str, Any]]) -> int:
    return sum(1 for e in elements if e.get("tag") == "chart")


def _is_metric_subplot_title(el: dict[str, Any]) -> bool:
    if el.get("tag") != "markdown":
        return False
    content = (el.get("content") or "").strip()
    return (
        content.startswith("**")
        and content.endswith("**")
        and content.count("**") == 2
        and "\n" not in content[2:-2]
    )


def _split_week_compare_panel_elements(
    panel_elements: list[dict[str, Any]], *, max_charts: int = MAX_CHARTS_PER_CARD
) -> list[list[dict[str, Any]]]:
    """按「指标标题 markdown + 子图 chart」原子单元分包，避免 ARPU 等标题与图跨卡。"""
    preamble: list[dict[str, Any]] = []
    units: list[list[dict[str, Any]]] = []
    i = 0
    while i < len(panel_elements):
        el = panel_elements[i]
        if (
            _is_metric_subplot_title(el)
            and i + 1 < len(panel_elements)
            and panel_elements[i + 1].get("tag") == "chart"
        ):
            units.append([el, panel_elements[i + 1]])
            i += 2
            continue
        if is_week_compare_legend_chart(el):
            preamble.append(el)
            i += 1
            continue
        if el.get("tag") == "chart":
            units.append([el])
            i += 1
            continue
        preamble.append(el)
        i += 1

    if not units:
        return [panel_elements]

    has_legend = panel_has_week_compare_legend(panel_elements)
    chunks: list[list[dict[str, Any]]] = []
    batch: list[list[dict[str, Any]]] = []
    for unit in units:
        preamble_charts = sum(1 for e in preamble if e.get("tag") == "chart")
        if not preamble and has_legend and chunks:
            # 续卡 annotate 会插入图例，预留 1 个 chart 位
            preamble_charts = 1
        if len(batch) >= max_charts - preamble_charts:
            chunk = preamble + [e for u in batch for e in u]
            annotate_first_chart_legend(chunk)
            chunks.append(chunk)
            preamble = []
            batch = []
        batch.append(unit)
    if batch:
        chunk = preamble + [e for u in batch for e in u]
        annotate_first_chart_legend(chunk)
        chunks.append(chunk)
    return chunks if chunks else [panel_elements]


def _make_feishu_card(
    *,
    title: str,
    subtitle: str,
    elements: list[dict[str, Any]],
    template: str = "blue",
) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "subtitle": {"tag": "plain_text", "content": subtitle},
            "template": template,
        },
        "body": {"elements": elements},
    }


def _chart_caption_md(spec: dict[str, Any]) -> str:
    """仅补充非图例说明（折线图图例由 VChart legends 渲染）。"""
    if spec.get("type") == "line" and spec.get("series_field"):
        return "<font color='grey'>横轴 D1–D7 表示当周内第 N 天</font>"
    return ""


def _week_compare_table_md(
    metrics: list[dict[str, Any]],
    *,
    compare_rows: list[dict[str, Any]] | None = None,
    chart_rows: list[dict[str, Any]] | None = None,
) -> str:
    """表3 周维度对比（7 项指标：P1 / P2 / 环比）。"""
    rows: list[tuple[str, str, str, str]] = []
    if compare_rows:
        for r in compare_rows:
            rows.append(
                (
                    str(r.get("metric") or ""),
                    str(r.get("p1") or ""),
                    str(r.get("p2") or ""),
                    str(r.get("delta") or ""),
                )
            )
    elif chart_rows:
        grouped: dict[str, dict[str, float]] = {}
        for r in chart_rows:
            metric = str(r.get("metric") or "")
            period = str(r.get("period") or "")
            if metric:
                grouped.setdefault(metric, {})[period] = float(r.get("value") or 0)
        for metric, vals in grouped.items():
            p1 = vals.get("近一周", 0)
            p2 = vals.get("前一周", 0)
            delta = ""
            if p2:
                delta = f"{(p1 - p2) / p2 * 100:+.1f}%"
            rows.append(
                (
                    metric,
                    f"{p1:.2f}",
                    f"{p2:.2f}",
                    delta,
                )
            )
    elif len(metrics) >= 4:
        rows = [
            ("流水", str(metrics[0].get("value", "")), str(metrics[1].get("value", "")), str(metrics[0].get("delta") or "")),
            ("付费人数", str(metrics[2].get("value", "")), str(metrics[3].get("value", "")), str(metrics[2].get("delta") or "")),
        ]
    if not rows:
        return ""
    lines = [
        "**表3 · 周维度对比**",
        "",
        "| 指标 | 近一周(P1) | 前一周(P2) |",
        "| --- | ---: | ---: |",
    ]
    for metric, p1, p2, delta in rows:
        d1s = f" ({delta})" if delta else ""
        lines.append(f"| {metric} | **{p1}**{d1s} | {p2} |")
    return "\n".join(lines)


def _append_section_charts(
    elements: list[dict[str, Any]],
    charts: list[dict[str, Any]],
    *,
    trace_id: str = "",
    used_chart_ids: set[str] | None = None,
) -> None:
    seen = used_chart_ids if used_chart_ids is not None else set()
    for spec in charts:
        cap = _chart_caption_md(spec)
        if cap:
            elements.append({"tag": "markdown", "content": cap})
        elements.extend(
            build_charts_elements([spec], trace_id=trace_id, used_ids=seen)
        )


def _append_card_footer(
    elements: list[dict[str, Any]],
    payload: dict[str, Any],
    *,
    with_feedback: bool = True,
) -> None:
    answer = payload.get("answer") or {}
    trace_id = payload.get("trace_id", "")
    session_id = payload.get("session_id", "")
    template_id = answer.get("template_id", "")
    trace_block = (
        f"**追溯信息**\n"
        f"trace `{trace_id}` · 模板 `{template_id}`\n"
        f"口径 {answer.get('methodology', '')}\n"
        f"SQL digest `{answer.get('sql_digest', '')}`"
    )
    rag_md = _lineage_rag_block(answer.get("rag_citations") or [])
    if rag_md:
        elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": rag_md})
    exp_md = _lineage_experience_block(answer.get("experience_reuse"))
    if exp_md:
        elements.append({"tag": "markdown", "content": exp_md})
    elements.append({"tag": "hr"})
    elements.append({"tag": "markdown", "content": trace_block})
    if not with_feedback:
        return
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


def _section_header_md(sec: dict[str, Any], *, text_color: str | None = None) -> str:
    label = sec.get("stage_label") or ""
    title = sec.get("title") or label
    header = f"**{label} · {title}**" if label else f"**{title}**"
    if sec.get("summary"):
        header += f"\n{sec['summary']}"
    if text_color:
        return f"<font color='{text_color}'>{header}</font>"
    return header


def _section_header_element(sec: dict[str, Any]) -> dict[str, Any]:
    """Section title element with optional gain/loss background tint."""
    title = str(sec.get("title") or "")
    # 深绿/深红底需浅色字；飞书 markdown 支持 white 等枚举色名。
    if "涨幅贡献" in title:
        md = _section_header_md(sec, text_color="white")
        return {
            "tag": "column_set",
            "flex_mode": "none",
            "background_style": "green",
            "horizontal_spacing": "default",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "vertical_align": "top",
                    "elements": [{"tag": "markdown", "content": md}],
                }
            ],
        }
    if "跌幅贡献" in title:
        md = _section_header_md(sec, text_color="white")
        return {
            "tag": "column_set",
            "flex_mode": "none",
            "background_style": "red",
            "horizontal_spacing": "default",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "vertical_align": "top",
                    "elements": [{"tag": "markdown", "content": md}],
                }
            ],
        }
    return {"tag": "markdown", "content": _section_header_md(sec)}


# ---------------------------------------------------------------------------
# Structured report renderer (answer.report → Feishu card elements)
#
# Backend (Go) emits a structured apiv1.Report; this block is the *only* place
# that maps it to Feishu card JSON. It is deliberately self-contained and
# data-driven (style tables below) so it can be lifted into the Go backend
# wholesale if/when card assembly is migrated off AstrBot. See
# docs/mvp/design/飞书文档问答-端到端流程与报告编排器设计.md §2.7.
# ---------------------------------------------------------------------------

# 同级标题同样式、不同级不同样式：一级深蓝底白字，二级灰底默认字。
_REPORT_SECTION_STYLES: dict[int, dict[str, str | None]] = {
    1: {"background_style": "blue", "text_color": "white"},
    2: {"background_style": "grey", "text_color": None},
}

# bullet kind → 字色（与设计 2.7 配色一致）。
_REPORT_BULLET_COLORS: dict[str, str | None] = {
    "finding": "blue",
    "hypothesis": "orange",
    "to_verify": "grey",
    "forecast": "purple",
    "plain": None,
}

# 首行缩进两个全角空格。
_REPORT_INDENT = "\u3000\u3000"

_HEADING_PREFIX_RE = re.compile(r"^#{1,6}\s*")


def _report_strip_heading(text: str) -> str:
    """剥离 LLM 误带的 markdown 标题前缀，避免飞书把 ### 渲染成大字号。"""
    return _HEADING_PREFIX_RE.sub("", text.strip())


def _report_header_element(title: str, level: int) -> dict[str, Any]:
    """整行背景色标题：column_set 单列 + background_style（客户端 ≥ 7.9）。"""
    style = _REPORT_SECTION_STYLES.get(level, _REPORT_SECTION_STYLES[1])
    text = f"**{title}**"
    color = style.get("text_color")
    if color:
        text = f"<font color='{color}'>{text}</font>"
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": style.get("background_style") or "default",
        "horizontal_spacing": "default",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "elements": [{"tag": "markdown", "content": text}],
            }
        ],
    }


def _report_paragraph_md(text: str) -> str:
    return _REPORT_INDENT + _report_strip_heading(text)


def _report_bullet_line(bullet: dict[str, Any]) -> str:
    text = str(bullet.get("text") or "").strip()
    color = _REPORT_BULLET_COLORS.get(str(bullet.get("kind") or "plain"))
    if color:
        return f"• <font color='{color}'>{text}</font>"
    return f"• {text}"


def _report_section_elements(section: dict[str, Any]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    title = str(section.get("title") or "").strip()
    level = int(section.get("level") or 1)
    if title:
        elements.append(_report_header_element(title, level))
    paragraphs = [
        _report_paragraph_md(p)
        for p in (section.get("paragraphs") or [])
        if str(p).strip()
    ]
    if paragraphs:
        elements.append({"tag": "markdown", "content": "\n\n".join(paragraphs)})
    bullets = section.get("bullets") or []
    if bullets:
        lines = "\n".join(_report_bullet_line(b) for b in bullets)
        elements.append({"tag": "markdown", "content": lines})
    return elements


def _report_elements(report: dict[str, Any]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for section in report.get("sections") or []:
        elements.extend(_report_section_elements(section))
    return elements


def _notice_markdown_content(notice: dict[str, Any]) -> str:
    level = (notice.get("level") or "warning").lower()
    icon = "⚠️" if level == "warning" else "ℹ️"
    title_color = "red" if level == "warning" else "blue"
    title = notice.get("title") or "提示"
    body = (notice.get("body") or "").strip()
    md_parts = [f"{icon} <font color='{title_color}'>**{title}**</font>"]
    if body:
        md_parts.append(body)
    formula = (notice.get("formula") or "").strip()
    if formula:
        md_parts.append(f"```\n{formula}\n```")
    return "\n".join(md_parts)


def _notice_callout_element(notice: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": "grey",
        "horizontal_spacing": "default",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "elements": [
                    {"tag": "markdown", "content": _notice_markdown_content(notice)},
                ],
            }
        ],
    }


def _append_answer_notices(
    elements: list[dict[str, Any]], answer: dict[str, Any]
) -> None:
    notices = answer.get("notices") or []
    for notice in notices:
        if isinstance(notice, dict) and (notice.get("title") or notice.get("body")):
            elements.append(_notice_callout_element(notice))
            elements.append({"tag": "hr"})


def _build_pay_weekly_sec1_elements(
    sec: dict[str, Any],
    *,
    daily_rows: list[dict[str, Any]],
    trace_id: str,
    used_chart_ids: set[str],
) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    elements.append(_section_header_element(sec))
    p1_rows = [r for r in daily_rows if r.get("period") in ("近一周", "P1")]
    p2_rows = [r for r in daily_rows if r.get("period") in ("前一周", "P2")]
    if p1_rows:
        elements.append(
            {
                "tag": "markdown",
                "content": _daily_pay_table(p1_rows, title="**表1 · P1（近一周）每日明细**"),
            }
        )
    if p2_rows:
        elements.append(
            {
                "tag": "markdown",
                "content": _daily_pay_table(p2_rows, title="**表2 · P2（前一周）每日明细**"),
            }
        )
    for fact in sec.get("facts") or []:
        elements.append({"tag": "markdown", "content": f"<font color='grey'>{fact}</font>"})
    _append_section_charts(
        elements, sec.get("charts") or [], trace_id=trace_id, used_chart_ids=used_chart_ids
    )
    return elements


def _build_pay_weekly_sec2_element_groups(
    sec: dict[str, Any],
    *,
    metrics: list[dict[str, Any]],
    trace_id: str,
    used_chart_ids: set[str],
) -> list[list[dict[str, Any]]]:
    """表3 + 周对比子图；图表超限时拆成多段元素列表（可对应多张卡片）。"""
    prefix: list[dict[str, Any]] = [
        _section_header_element(sec),
    ]
    chart_rows: list[dict[str, Any]] = []
    panel_spec: dict[str, Any] | None = None
    for ch in sec.get("charts") or []:
        if ch.get("chart_id") == "wk_cmp_panel":
            chart_rows = ch.get("data_rows") or []
            panel_spec = ch
            break
    tbl = _week_compare_table_md(
        sec.get("metrics") or metrics,
        compare_rows=sec.get("compare_rows"),
        chart_rows=chart_rows,
    )
    if tbl:
        prefix.append({"tag": "markdown", "content": tbl})
    elif sec.get("facts"):
        prefix.append(
            {
                "tag": "markdown",
                "content": "\n".join(f"• {f}" for f in (sec.get("facts") or [])[:4]),
            }
        )
    if not panel_spec:
        return [prefix]

    chart_parts: list[dict[str, Any]] = []
    _append_section_charts(
        chart_parts, [panel_spec], trace_id=trace_id, used_chart_ids=used_chart_ids
    )
    panel_chunks = _split_week_compare_panel_elements(chart_parts)
    if len(panel_chunks) <= 1:
        annotate_first_chart_legend(panel_chunks[0])
        return [prefix + panel_chunks[0]]
    out: list[list[dict[str, Any]]] = []
    total = len(panel_chunks)
    for i, chunk in enumerate(panel_chunks):
        if i == 0:
            out.append(prefix + chunk)
            continue
        cont: list[dict[str, Any]] = [
            {
                "tag": "markdown",
                "content": (
                    f"**{sec.get('title') or '表3'}（续 {i + 1}/{total}）**\n"
                    "<font color='grey'>周对比子图（接上一卡）</font>"
                ),
            }
        ]
        cont.extend(chunk)
        annotate_first_chart_legend(cont)
        out.append(cont)
    return out


def _build_pay_weekly_sec3_elements(sec: dict[str, Any]) -> list[dict[str, Any]]:
    header = _section_header_md(sec)
    if sec.get("facts"):
        header += "\n" + "\n".join(f"• {f}" for f in sec.get("facts")[:6])
    return [{"tag": "markdown", "content": header}]


def build_pay_weekly_cards_json(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """双周付费分析拆为多张飞书卡片，避免单卡 VChart 过多导致 2200。"""
    answer = payload.get("answer") or {}
    sections = answer.get("sections") or []
    summary = answer.get("summary", "")
    daily_rows = answer.get("daily_rows") or []
    metrics = answer.get("metrics") or []
    base_title = answer.get("title", "分析结果")
    used_chart_ids: set[str] = set()
    trace_id = payload.get("trace_id", "")

    card_bodies: list[tuple[str, list[dict[str, Any]], str]] = []

    sec1 = next((s for s in sections if s.get("stage_index") == 1), None)
    sec2 = next((s for s in sections if s.get("stage_index") == 2), None)
    sec3 = next((s for s in sections if s.get("stage_index") == 3), None)

    if sec1:
        el1: list[dict[str, Any]] = [
            {"tag": "markdown", "content": f"**摘要**\n{summary or '（无摘要）'}"},
        ]
        el1.extend(
            _build_pay_weekly_sec1_elements(
                sec1, daily_rows=daily_rows, trace_id=trace_id, used_chart_ids=used_chart_ids
            )
        )
        card_bodies.append(("每日明细 · 表1/表2 · 日流水与趋势图", el1, "blue"))

    if sec2:
        for group in _build_pay_weekly_sec2_element_groups(
            sec2, metrics=metrics, trace_id=trace_id, used_chart_ids=used_chart_ids
        ):
            n = _count_chart_elements(group)
            sub = f"周维度对比 · 表3" + (f" · {n} 图" if n else "")
            card_bodies.append((sub, group, "blue"))

    if sec3:
        el3 = _build_pay_weekly_sec3_elements(sec3)
        _append_card_footer(el3, payload, with_feedback=True)
        card_bodies.append(("结论与追溯反馈", el3, "green"))

    total = len(card_bodies)
    cards: list[dict[str, Any]] = []
    for i, (subtitle, elements, template) in enumerate(card_bodies, start=1):
        part_title = base_title if total == 1 else f"{base_title}（{i}/{total}）"
        part_sub = subtitle if total == 1 else f"{i}/{total} · {subtitle}"
        cards.append(
            _make_feishu_card(
                title=part_title,
                subtitle=part_sub,
                elements=elements,
                template=template,
            )
        )
        log_card_build(payload, cards[-1], part=i, parts=total)
    return cards


def build_result_cards_json(payload: dict[str, Any]) -> list[dict[str, Any]]:
    answer = payload.get("answer") or {}
    if answer.get("query_mode") == "adhoc" or answer.get("adhoc_table"):
        return [build_adhoc_result_card_json(payload)]
    sections = answer.get("sections") or []
    if sections and _is_pay_weekly_sections(sections):
        return build_pay_weekly_cards_json(payload)
    return [build_result_card_json(payload)]


def _append_chart_blocks(
    elements: list[dict[str, Any]],
    charts: list[dict[str, Any]],
    *,
    max_charts: int = 3,
    heading: str = "**数据图表**",
    trace_id: str = "",
    used_chart_ids: set[str] | None = None,
) -> None:
    if not charts:
        return
    elements.append(
        {
            "tag": "markdown",
            "content": (
                f"{heading}\n"
                "<font color='grey'>趋势/对比图可在手机端点击全屏查看；"
                "与上方表格为同一数据源。</font>"
            ),
        }
    )
    elements.extend(
        build_charts_elements(
            charts,
            max_charts=max_charts,
            trace_id=trace_id,
            used_ids=used_chart_ids,
        )
    )


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


def _split_decline_facts(facts: list[str]) -> tuple[list[str], list[str]]:
    """Separate rule-based decline exploration bullets from headline facts."""
    for i, f in enumerate(facts):
        if str(f).startswith("【环比下降探查】"):
            return facts[:i], facts[i:]
    return facts, []


def _decline_explore_block(facts: list[str]) -> str:
    _, explore = _split_decline_facts(facts)
    if not explore:
        return ""
    lines = [f"• {f}" for f in explore]
    return "**环比下降 · 自动探查**\n" + "\n".join(lines)


# 飞书 JSON 2.0：单卡最多 5 个原生 table 组件
_MAX_FEISHU_NATIVE_TABLES = 5
_FEISHU_TABLE_PAGE_SIZE_MAX = 10


def _feishu_table_element_id(seq: int) -> str:
    eid = f"gdTbl{seq}"
    return eid[:20]


def _parse_adhoc_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip().replace(",", "").replace(" ", "")
    if s in ("", "—", "-"):
        return None
    if s.endswith("%"):
        return None
    try:
        return float(s.lstrip("+"))
    except ValueError:
        return None


def _adhoc_column_def(col: dict[str, Any], *, is_first: bool) -> dict[str, Any]:
    key = col.get("key") or ""
    label = col.get("display_name") or col.get("label") or key
    col_type = (col.get("type") or "string").lower()
    width = "140px" if is_first else "auto"
    if col_type == "number":
        return {
            "name": key,
            "display_name": label,
            "data_type": "number",
            "width": width,
            "horizontal_align": "right",
            "format": {"separator": True, "precision": 2},
        }
    return {
        "name": key,
        "display_name": label,
        "data_type": "text",
        "width": width if is_first else "auto",
        "vertical_align": "top",
        "horizontal_align": "left",
    }


def _adhoc_row_native(
    row: dict[str, Any], columns: list[dict[str, Any]]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in columns:
        key = col.get("key") or ""
        col_type = (col.get("type") or "string").lower()
        raw = row.get(key)
        if col_type == "number":
            num = _parse_adhoc_number(raw)
            out[key] = num if num is not None else 0
        elif raw is None:
            out[key] = ""
        else:
            out[key] = str(raw)
    return out


def _adhoc_table_element(
    table: dict[str, Any] | None,
    *,
    element_id: str,
    max_rows: int = 40,
    freeze_first_column: bool = True,
) -> dict[str, Any] | None:
    """飞书原生 table 组件（text/number 列，首列可冻结）。"""
    if not table:
        return None
    cols = table.get("columns") or []
    rows = table.get("rows") or []
    if not rows:
        return None
    if not cols:
        cols = [{"key": k, "label": k, "type": "string"} for k in rows[0].keys()]
    feishu_cols = [
        _adhoc_column_def(c, is_first=(i == 0)) for i, c in enumerate(cols)
    ]
    display = rows[:max_rows]
    native_rows = [_adhoc_row_native(r, cols) for r in display]
    page_size = max(1, min(_FEISHU_TABLE_PAGE_SIZE_MAX, len(native_rows)))
    el: dict[str, Any] = {
        "tag": "table",
        "element_id": element_id,
        "margin": "4px 0 8px 0",
        "page_size": page_size,
        "row_height": "auto",
        "row_max_height": "80px",
        "freeze_first_column": freeze_first_column and len(feishu_cols) > 1,
        "header_style": {
            "text_align": "left",
            "text_size": "normal",
            "background_style": "grey",
            "text_color": "default",
            "bold": True,
            "lines": 1,
        },
        "columns": feishu_cols,
        "rows": native_rows,
    }
    return el


def _wow_week_compare_table_element(
    compare_rows: list[dict[str, Any]], *, element_id: str
) -> dict[str, Any] | None:
    if not compare_rows:
        return None
    cols = [
        {
            "name": "metric",
            "display_name": "指标",
            "data_type": "text",
            "width": "auto",
            "vertical_align": "top",
        },
        {
            "name": "p1",
            "display_name": "上上周",
            "data_type": "text",
            "width": "auto",
            "horizontal_align": "right",
        },
        {
            "name": "p2",
            "display_name": "上一周",
            "data_type": "text",
            "width": "auto",
            "horizontal_align": "right",
        },
        {
            "name": "delta",
            "display_name": "环比",
            "data_type": "text",
            "width": "auto",
            "horizontal_align": "right",
        },
    ]
    rows = [
        {
            "metric": str(r.get("metric") or ""),
            "p1": str(r.get("p1") or ""),
            "p2": str(r.get("p2") or ""),
            "delta": str(r.get("delta") or ""),
        }
        for r in compare_rows
    ]
    return {
        "tag": "table",
        "element_id": element_id,
        "margin": "4px 0 8px 0",
        "page_size": max(1, min(_FEISHU_TABLE_PAGE_SIZE_MAX, len(rows))),
        "row_height": "auto",
        "freeze_first_column": True,
        "header_style": {
            "text_align": "left",
            "text_size": "normal",
            "background_style": "grey",
            "bold": True,
        },
        "columns": cols,
        "rows": rows,
    }


def _append_native_table_or_markdown(
    elements: list[dict[str, Any]],
    *,
    table: dict[str, Any] | None = None,
    compare_rows: list[dict[str, Any]] | None = None,
    heading: str | None = None,
    table_seq: list[int],
    native_budget: list[int],
) -> None:
    """优先原生 table；超出单卡 5 表上限时回退 Markdown。"""
    if heading:
        elements.append({"tag": "markdown", "content": f"**{heading}**"})
    if compare_rows is not None:
        if native_budget[0] > 0:
            el = _wow_week_compare_table_element(
                compare_rows, element_id=_feishu_table_element_id(table_seq[0])
            )
            if el:
                elements.append(el)
                table_seq[0] += 1
                native_budget[0] -= 1
                return
        md = _wow_week_compare_table_md(compare_rows)
        if md:
            elements.append({"tag": "markdown", "content": md.strip()})
        return
    if not table:
        return
    if native_budget[0] > 0:
        el = _adhoc_table_element(
            table,
            element_id=_feishu_table_element_id(table_seq[0]),
            freeze_first_column=True,
        )
        if el:
            elements.append(el)
            table_seq[0] += 1
            native_budget[0] -= 1
            row_count = int(table.get("row_count") or len(table.get("rows") or []))
            truncated = bool(table.get("truncated")) or row_count > len(el["rows"])
            if truncated:
                elements.append(
                    {
                        "tag": "markdown",
                        "content": (
                            f"<font color='grey'>共 {row_count} 行"
                            f"（表格每页最多 {_FEISHU_TABLE_PAGE_SIZE_MAX} 行，可翻页查看）。</font>"
                        ),
                    }
                )
            return
    table_md = _adhoc_table_markdown(table, heading=None)
    if table_md:
        elements.append({"tag": "markdown", "content": table_md})


def _format_adhoc_cell(value: Any, col_type: str) -> str:
    if value is None:
        return "—"
    if col_type == "number":
        try:
            num = float(value)
            if abs(num) >= 1000:
                return f"{num:,.0f}"
            if num == int(num):
                return str(int(num))
            return f"{num:.2f}"
        except (TypeError, ValueError):
            return str(value)
    text = str(value)
    if len(text) > 48:
        return text[:45] + "…"
    return text


def _wow_week_compare_table_md(compare_rows: list[dict[str, Any]]) -> str:
    """双周流水对比表（上上周 vs 上一周）。"""
    if not compare_rows:
        return ""
    lines = [
        "",
        "| 指标 | 上上周 | 上一周 | 环比 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for r in compare_rows:
        lines.append(
            "| {metric} | {p1} | {p2} | {delta} |".format(
                metric=r.get("metric") or "",
                p1=r.get("p1") or "",
                p2=r.get("p2") or "",
                delta=r.get("delta") or "",
            )
        )
    return "\n".join(lines)


def _adhoc_table_markdown(
    table: dict[str, Any] | None,
    *,
    max_rows: int = 40,
    heading: str | None = None,
) -> str:
    """Generic markdown table from platform answer.adhoc_table."""
    if not table:
        return ""
    cols = table.get("columns") or []
    rows = table.get("rows") or []
    if not rows:
        return f"**{heading or '查询结果'}**\n<font color='grey'>无匹配行。</font>"
    if not cols:
        cols = [{"key": k, "label": k, "type": "string"} for k in rows[0].keys()]
    headers = [c.get("label") or c.get("key") or "?" for c in cols]
    title = heading or "查询结果"
    lines = [
        f"**{title}**",
        "<font color='grey'>按需 SQL 查询；下表为平台返回的原始行（最多展示 "
        f"{max_rows} 行）。</font>",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    display = rows[:max_rows]
    for row in display:
        cells = [
            _format_adhoc_cell(row.get(c.get("key", "")), c.get("type", "string"))
            for c in cols
        ]
        lines.append("| " + " | ".join(cells) + " |")
    row_count = int(table.get("row_count") or len(rows))
    truncated = bool(table.get("truncated")) or len(rows) > max_rows
    if truncated:
        lines.append("")
        lines.append(
            f"<font color='grey'>共 {row_count} 行"
            f"{'（已截断展示）' if truncated else ''}。</font>"
        )
    return "\n".join(lines)


def _adhoc_trace_block(answer: dict[str, Any], trace_id: str, template_id: str) -> str:
    meta = answer.get("adhoc_meta") or {}
    attempts = meta.get("attempts")
    codes = meta.get("codes") or []
    extra = ""
    if attempts:
        extra += f"\n生成轮次 {attempts}"
    if codes:
        extra += f"\n审核码 {', '.join(str(c) for c in codes[:5])}"
    return (
        f"**追溯信息**\n"
        f"trace `{trace_id}` · 模式 `adhoc` · 模板 `{template_id}`{extra}\n"
        f"口径 {answer.get('methodology', '')}\n"
        f"SQL digest `{answer.get('sql_digest', '')}`"
    )


def build_adhoc_result_card_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Feishu card for query_mode=adhoc (catalog.adhoc)."""
    answer = payload.get("answer") or {}
    rendering = payload.get("rendering") or {}
    preferred = rendering.get("preferred", "table")
    charts = answer.get("charts") or []
    trace_id = payload.get("trace_id", "")
    session_id = payload.get("session_id", "")
    template_id = answer.get("template_id", "catalog.adhoc")
    summary = answer.get("summary", "")
    facts = answer.get("facts") or []
    facts_md = "\n".join(f"• {f}" for f in facts[:5])

    chart_only = preferred == "chart" and charts and (charts[0].get("type") or "") == "pie"

    elements: list[dict[str, Any]] = [
        {"tag": "markdown", "content": f"**摘要**\n{summary or '（无摘要）'}"},
    ]
    _append_answer_notices(elements, answer)
    if charts:
        _append_chart_blocks(
            elements,
            charts,
            max_charts=3,
            heading="**图表**",
            trace_id=trace_id,
        )
    sections = answer.get("sections") or []
    table_seq = [0]
    native_budget = [_MAX_FEISHU_NATIVE_TABLES]
    if not chart_only and sections:
        for sec in sections:
            title = sec.get("title") or (sec.get("stage_label") or "")
            elements.append(_section_header_element(sec))
            if sec.get("compare_rows"):
                _append_native_table_or_markdown(
                    elements,
                    compare_rows=sec.get("compare_rows") or [],
                    heading=None,
                    table_seq=table_seq,
                    native_budget=native_budget,
                )
            if sec.get("adhoc_table"):
                _append_native_table_or_markdown(
                    elements,
                    table=sec.get("adhoc_table"),
                    heading=title,
                    table_seq=table_seq,
                    native_budget=native_budget,
                )
            sec_charts = sec.get("charts") or []
            if sec_charts:
                _append_chart_blocks(
                    elements,
                    sec_charts,
                    max_charts=1,
                    heading=f"**{title} · 图表**",
                    trace_id=trace_id,
                )
    elif not chart_only:
        adhoc_tbl = answer.get("adhoc_table")
        if adhoc_tbl:
            _append_native_table_or_markdown(
                elements,
                table=adhoc_tbl,
                heading="查询结果",
                table_seq=table_seq,
                native_budget=native_budget,
            )
        elif facts_md and not charts:
            elements.append({"tag": "markdown", "content": f"**说明**\n{facts_md}"})
        if facts_md and adhoc_tbl:
            elements.append({"tag": "markdown", "content": f"**要点**\n{facts_md}"})
    elif facts_md:
        elements.append({"tag": "markdown", "content": f"**要点**\n{facts_md}"})
    if facts_md and sections:
        elements.append({"tag": "markdown", "content": f"**要点**\n{facts_md}"})

    rag_md = _lineage_rag_block(answer.get("rag_citations") or [])
    if rag_md:
        elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": rag_md})
    exp_md = _lineage_experience_block(answer.get("experience_reuse"))
    if exp_md:
        elements.append({"tag": "markdown", "content": exp_md})
    elements.append({"tag": "hr"})
    elements.append(
        {"tag": "markdown", "content": _adhoc_trace_block(answer, trace_id, template_id)}
    )
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
        _feedback_button("有用", "useful", trace_id, session_id, template_id, primary=True),
        _feedback_button("Bad Case", "bad_case", trace_id, session_id, template_id),
        _feedback_button(
            "沉淀模板候选", "save_template_candidate", trace_id, session_id, template_id
        ),
    ]
    elements.append(
        {
            "tag": "column_set",
            "flex_mode": "none",
            "horizontal_spacing": "default",
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

    card = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": answer.get("title", "按需查询结果")},
            "subtitle": {
                "tag": "plain_text",
                "content": "按需查询 · 数据表",
            },
            "template": "wathet",
        },
        "body": {"elements": elements},
    }
    log_card_build(payload, card, part=1, parts=1)
    return card



def log_card_build(
    payload: dict[str, Any],
    card: dict[str, Any],
    *,
    part: int = 1,
    parts: int = 1,
) -> None:
    answer = payload.get("answer") or {}
    rendering = payload.get("rendering") or {}
    header = card.get("header") or {}
    body = card.get("body") or {}
    elements = body.get("elements") or []
    ncharts = _count_chart_elements(elements)
    part_s = f" part={part}/{parts}" if parts > 1 else ""
    adhoc_table = answer.get("adhoc_table") or {}
    logger.info(
        "[game_data_ai] card.build "
        f"trace={payload.get('trace_id')} "
        f"query_mode={answer.get('query_mode', 'template')} "
        f"mode={rendering.get('preferred', 'table')} "
        f"title={answer.get('title', '')} "
        f"metrics={len(answer.get('metrics') or [])} "
        f"chart_points={len(answer.get('chart_series') or [])} "
        f"adhoc_rows={adhoc_table.get('row_count', 0)} "
        f"elements={len(elements)} charts={ncharts}{part_s} "
        f"header_template={header.get('template', 'blue')}"
    )
    logger.info(
        "[game_data_ai] card.answer "
        f"summary={answer.get('summary', '')[:120]} "
        f"notices={len(answer.get('notices') or [])} "
        f"facts={answer.get('facts') or []} "
        f"chart_series={answer.get('chart_series') or []} "
        f"rag_citations={len(answer.get('rag_citations') or [])} "
        f"experience_reuse={bool(answer.get('experience_reuse'))}"
    )


def build_report_card_json(payload: dict[str, Any]) -> dict[str, Any]:
    """结构化报告卡片：按 answer.report 分章节渲染（标题整行背景色、字号一致）。"""
    answer = payload.get("answer") or {}
    report = answer.get("report") or {}
    elements = _report_elements(report)
    _append_card_footer(elements, payload, with_feedback=True)
    card = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": answer.get("title", "分析报告")},
            "subtitle": {
                "tag": "plain_text",
                "content": report.get("title") or "结构化分析报告",
            },
            "template": "blue",
        },
        "body": {"elements": elements},
    }
    log_card_build(payload, card, part=1, parts=1)
    return card


def build_result_card_json(payload: dict[str, Any]) -> dict[str, Any]:
    answer = payload.get("answer") or {}
    if answer.get("query_mode") == "adhoc" or answer.get("adhoc_table"):
        return build_adhoc_result_card_json(payload)
    report = answer.get("report") or {}
    if report.get("sections"):
        return build_report_card_json(payload)
    rendering = payload.get("rendering") or {}
    trace_id = payload.get("trace_id", "")
    session_id = payload.get("session_id", "")
    template_id = answer.get("template_id", "")
    preferred = rendering.get("preferred", "table")
    facts = answer.get("facts") or []
    metrics = answer.get("metrics") or []
    chart_series = answer.get("chart_series") or []
    daily_rows = answer.get("daily_rows") or []
    charts = answer.get("charts") or []

    summary = answer.get("summary", "")
    sections = answer.get("sections") or []
    head_facts, _ = _split_decline_facts(facts)
    facts_md = "\n".join(f"• {f}" for f in head_facts[:5])
    trace_block = (
        f"**追溯信息**\n"
        f"trace `{trace_id}` · 模板 `{template_id}`\n"
        f"口径 {answer.get('methodology', '')}\n"
        f"SQL digest `{answer.get('sql_digest', '')}`"
    )

    is_chart = preferred == "chart"
    used_chart_element_ids: set[str] = set()
    elements: list[dict[str, Any]] = []

    if sections:
        elements.append(
            {"tag": "markdown", "content": f"**摘要**\n{summary or '（无摘要）'}"}
        )
        for sec in sections:
            label = sec.get("stage_label") or ""
            title = sec.get("title") or label
            sec_summary = sec.get("summary", "")
            sec_facts = sec.get("facts") or []
            block = f"**{label}** {title}\n{sec_summary}"
            if sec_facts:
                block += "\n" + "\n".join(f"• {f}" for f in sec_facts[:3])
            elements.append({"tag": "markdown", "content": block})
            sec_charts = sec.get("charts") or []
            if sec_charts:
                _append_section_charts(
                    elements,
                    sec_charts,
                    trace_id=trace_id,
                    used_chart_ids=used_chart_element_ids,
                )
            elif sec.get("metrics"):
                elements.extend(_metric_columns(sec.get("metrics") or [])[:4])
    elif is_chart:
        elements.append(
            {"tag": "markdown", "content": f"**摘要**\n{summary or '（无摘要）'}"}
        )
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
            elements.extend(
                build_charts_elements(charts, trace_id=trace_id, used_ids=used_chart_element_ids)
            )
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
        elements.extend(_metric_columns(metrics[:2]))
        if facts_md:
            decline_md = _decline_explore_block(facts)
            body = f"**结论摘要**\n{facts_md}"
            if decline_md:
                body += f"\n\n{decline_md}"
            elements.append({"tag": "markdown", "content": body})
    else:
        elements.append(
            {"tag": "markdown", "content": f"**摘要**\n{summary or '（无摘要）'}"}
        )
        # 表格视图（无 sections）：KPI + 日表 + 图表
        elements.extend(_metric_columns(metrics))
        period_tables = _daily_pay_tables_by_period(daily_rows)
        if period_tables:
            for tbl in period_tables:
                elements.append({"tag": "markdown", "content": tbl})
        elif chart_series:
            elements.append(
                {"tag": "markdown", "content": _chart_series_data_table(chart_series)}
            )
        else:
            daily_md = _daily_pay_table(daily_rows)
            if daily_md:
                elements.append({"tag": "markdown", "content": daily_md})
        if charts:
            _append_chart_blocks(
                elements,
                charts,
                max_charts=6,
                trace_id=trace_id,
                used_chart_ids=used_chart_element_ids,
            )
        if facts_md or facts:
            label = "**Phase 2 · 结论摘要**" if sections else "**关键事实**"
            body = f"{label}\n{facts_md}" if facts_md else label
            decline_md = _decline_explore_block(facts)
            if decline_md:
                body += f"\n\n{decline_md}"
            elements.append({"tag": "markdown", "content": body})
        hint = _table_mode_hint(chart_series)
        if hint and not daily_rows and not charts:
            elements.append({"tag": "markdown", "content": hint})

    _append_card_footer(elements, payload, with_feedback=True)

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
    log_card_build(payload, card, part=1, parts=1)
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
