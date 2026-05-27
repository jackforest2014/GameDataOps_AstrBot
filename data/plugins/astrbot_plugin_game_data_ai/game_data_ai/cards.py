"""Feishu card JSON builders (schema 2.0 — no motion/action/note)."""

from __future__ import annotations

import json
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


def _section_header_md(sec: dict[str, Any]) -> str:
    label = sec.get("stage_label") or ""
    title = sec.get("title") or label
    header = f"**{label}** {title}"
    if sec.get("summary"):
        header += f"\n{sec['summary']}"
    return header


def _build_pay_weekly_sec1_elements(
    sec: dict[str, Any],
    *,
    daily_rows: list[dict[str, Any]],
    trace_id: str,
    used_chart_ids: set[str],
) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    elements.append({"tag": "markdown", "content": _section_header_md(sec)})
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
        {"tag": "markdown", "content": _section_header_md(sec)},
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
    logger.info(
        "[game_data_ai] card.build "
        f"trace={payload.get('trace_id')} "
        f"mode={rendering.get('preferred', 'table')} "
        f"title={answer.get('title', '')} "
        f"metrics={len(answer.get('metrics') or [])} "
        f"chart_points={len(answer.get('chart_series') or [])} "
        f"elements={len(elements)} charts={ncharts}{part_s} "
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
