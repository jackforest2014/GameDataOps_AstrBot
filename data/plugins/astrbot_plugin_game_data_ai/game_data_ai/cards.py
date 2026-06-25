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
    rag_md = _lineage_rag_block(answer.get("rag_citations") or [])
    if rag_md:
        elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": rag_md})
    exp_md = _lineage_experience_block(answer.get("experience_reuse"))
    if exp_md:
        elements.append({"tag": "markdown", "content": exp_md})
    # 卡片末尾「反馈与沉淀」文案与按钮（有用/有问题/沉淀模板候选）暂时下线（用户要求）。
    return


def _section_header_md(sec: dict[str, Any], *, text_color: str | None = None) -> str:
    label = sec.get("stage_label") or ""
    title = sec.get("title") or label
    # 章节标签（流水构成/异常/涨跌榜/下钻）仅用于底色区分，不再拼进标题文本，避免
    # 形如「流水构成 · 消耗对比 · 广告消耗(投放)」的冗长前缀（链路点3）。
    header = f"**{title}**"
    if sec.get("summary"):
        header += f"\n{sec['summary']}"
    if text_color:
        return f"<font color='{text_color}'>{header}</font>"
    return header


# 深色底用浅色(白)字、浅色底(grey)用默认深字，保证对比度（用户第三轮反馈）。
_DARK_SECTION_BG = {"blue", "red", "purple", "green", "carmine", "indigo", "turquoise"}


def _tinted_section_header(sec: dict[str, Any], bg_color: str) -> dict[str, Any]:
    """整行底色标题块：column_set 单列 + background_style + 按底色深浅选字色。

    历史教训（用户三轮反馈）：
    1. 早期「底色 + 白字」——当时部分主题色客户端呈浅色填充，白字看不清。
    2. 随后去掉底色、改纯着色文字——用户希望把底色加回来。
    3. 加回底色后改默认深字——但 blue/red/purple/green 在客户端实际渲染为**深**底，
       深字落在深底上对比度差、看不清。
    本版：按底色深浅选字色——深底(blue/red/purple/green)用**白字**、浅底(grey)用默认深字。
    """
    label = sec.get("stage_label") or ""
    title = sec.get("title") or label
    light_text = bg_color in _DARK_SECTION_BG
    # 加粗放在 <font> 外层（飞书 markdown 不支持 ** 嵌在 <font> 内）。
    title_md = f"**{title}**"
    if light_text:
        title_md = f"**<font color='white'>{title}</font>**"
    content = title_md
    if sec.get("summary"):
        summary = sec["summary"]
        if light_text:
            summary = f"<font color='white'>{summary}</font>"
        content += f"\n{summary}"
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": bg_color,
        "horizontal_spacing": "default",
        "margin": "8px 0 4px 0",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "elements": [{"tag": "markdown", "content": content}],
            }
        ],
    }


# 章节底色（链路点5/6：用底色区分章节）。优先匹配标题里的涨/跌幅贡献，其次按 stage_label
# 给「流水构成 / 异常 / 涨跌榜」上不同底色，下钻子章节用灰底，普通段落不上底色。
# 取值均为飞书主题浅色填充，配默认深色加粗标题文字保证可读。
_SECTION_STAGE_BG: dict[str, str] = {
    "流水构成": "blue",
    "异常": "red",
    "涨跌榜": "purple",
    "下钻": "grey",
}


def _section_header_element(sec: dict[str, Any]) -> dict[str, Any]:
    """Section title element with a per-chapter tinted background (链路点5/6)."""
    title = str(sec.get("title") or "")
    if "涨幅贡献" in title:
        return _tinted_section_header(sec, "green")
    if "跌幅贡献" in title:
        return _tinted_section_header(sec, "red")
    stage = str(sec.get("stage_label") or "")
    if stage in _SECTION_STAGE_BG:
        return _tinted_section_header(sec, _SECTION_STAGE_BG[stage])
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

# bullet source（来源分级，见 docs/mvp/design/19 与 apiv1.ReportBullet.Source）：
# 事实有数仓/文档支撑，保留 kind 配色；推断/经验为模型生成，统一弱化为灰字并加来源前缀，
# 避免与「事实」在卡片里争夺同等视觉权重（T0.4）。
_REPORT_SOURCE_TAGS: dict[str, str] = {
    "doc_fact": "事实",
    "inference": "推断",
    "model_prior": "经验",
}
_REPORT_WEAKENED_SOURCES: frozenset[str] = frozenset({"inference", "model_prior"})

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


# 条目前缀（发现/假设/待验证/预判…）：加粗以与正文区分，便于快速扫读分组。
_REPORT_LEAD_PREFIXES: tuple[str, ...] = ("发现", "假设", "待验证", "预判", "预期")


def _bold_lead_prefix(text: str) -> str:
    """把条目开头的「发现：/假设：/待验证：/预判：」前缀加粗，其余文本不变。
    注意：只在不需要 <font> 色包裹时调用（** 在 <font> 内飞书不支持，会渲染成字面量 **）。
    """
    for p in _REPORT_LEAD_PREFIXES:
        for sep in ("：", ":"):
            head = p + sep
            if text.startswith(head):
                return f"**{head}**" + text[len(head):]
    return text


_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def _strip_md_bold(text: str) -> str:
    """移除 ** 加粗标记——飞书 markdown 在 <font> 标签内不支持 **，会渲染成字面量 ** 号。"""
    return _MD_BOLD_RE.sub(r"\1", text)


def _report_bullet_line(bullet: dict[str, Any], *, check_idx: int = 0) -> str:
    raw_text = str(bullet.get("text") or "").strip()
    source = str(bullet.get("source") or "")
    kind = str(bullet.get("kind") or "plain")
    tag = _REPORT_SOURCE_TAGS.get(source)
    # 来源小标签：加粗放在 <font> 外面（飞书 markdown 不支持 ** 嵌套在 <font> 内）。
    tag_prefix = f"**[{tag}]** " if tag else ""
    # to_verify 条目：加序号使其与「结论自验证」卡片中的 check_index 形成显式对应。
    idx_prefix = f"**{check_idx}.** " if check_idx > 0 else ""
    # 推断/经验：整体灰字弱化；先剥去 LLM 自带的 ** 号，否则 <font> 内 ** 渲染成字面量。
    if source in _REPORT_WEAKENED_SOURCES:
        clean = _strip_md_bold(raw_text)
        return f"• {idx_prefix}{tag_prefix}<font color='grey'>{clean}</font>"
    color = _REPORT_BULLET_COLORS.get(kind)
    if color:
        # 有颜色：同样不能在 <font> 内用 **，剥去后以颜色区分。
        clean = _strip_md_bold(raw_text)
        return f"• {idx_prefix}{tag_prefix}<font color='{color}'>{clean}</font>"
    # 无颜色包裹（plain kind / to_verify）：可安全加粗条目前缀。
    return f"• {idx_prefix}{tag_prefix}{_bold_lead_prefix(raw_text)}"


def _is_report_group_start(bullet: dict[str, Any]) -> bool:
    """分组起点：以「事实/发现」或「预判」开头，其后的假设/待验证/经验归入同组（#2）。"""
    kind = str(bullet.get("kind") or "")
    source = str(bullet.get("source") or "")
    return kind in ("finding", "forecast") or source == "doc_fact"


def _grouped_bullet_lines(bullets: list[dict[str, Any]]) -> list[str]:
    """渲染 bullet，并在不同分组之间插入空行，避免密密麻麻一整块。
    to_verify 类条目额外加序号，以便与「结论自验证」卡片中的 check_index 对应。
    """
    lines: list[str] = []
    to_verify_idx = 0
    for i, b in enumerate(bullets):
        if i > 0 and _is_report_group_start(b):
            lines.append("")  # 组间空行
        if str(b.get("kind") or "") == "to_verify":
            to_verify_idx += 1
            lines.append(_report_bullet_line(b, check_idx=to_verify_idx))
        else:
            lines.append(_report_bullet_line(b))
    return lines


def _summary_paragraph_md(paragraphs: list[str]) -> str:
    """结论概述：先一两句话的概述，再把其余句子拆成列表，避免一大段密集文字（#2）。"""
    text = " ".join(_report_strip_heading(p) for p in paragraphs if str(p).strip())
    sentences = [s.strip() for s in re.split(r"(?<=[。！？!?])", text) if s.strip()]
    if len(sentences) <= 2:
        return _REPORT_INDENT + text
    lead_n = 2 if len(sentences) >= 4 else 1
    lead = "".join(sentences[:lead_n])
    rest = sentences[lead_n:]
    body = [_REPORT_INDENT + lead, ""]
    body.extend(f"• {s}" for s in rest)
    return "\n".join(body)


def _report_section_elements(section: dict[str, Any]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    title = str(section.get("title") or "").strip()
    level = int(section.get("level") or 1)
    if title:
        elements.append(_report_header_element(title, level))
    raw_paragraphs = [p for p in (section.get("paragraphs") or []) if str(p).strip()]
    if raw_paragraphs:
        if "概述" in title:
            content = _summary_paragraph_md(raw_paragraphs)
        else:
            content = "\n\n".join(_report_paragraph_md(p) for p in raw_paragraphs)
        elements.append({"tag": "markdown", "content": content})
    bullets = section.get("bullets") or []
    if bullets:
        lines = "\n".join(_grouped_bullet_lines(bullets))
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
    qm = answer.get("query_mode") or ""
    if qm in ("adhoc", "realtime_consume") or answer.get("adhoc_table"):
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


def _render_illustrated_facts(
    elements: list[dict[str, Any]],
    illustrated_facts: list[dict[str, Any]],
    trace_id: str = "",
) -> None:
    """渲染「要点」区块：每个 fact 配一个小型竖直柱状图（上期 vs 本期），图在上、文字在下。
    若 fact 没有 chart 则只输出文字。
    """
    from game_data_ai.charts import _feishu_element_id, chart_spec_to_feishu_element

    if not illustrated_facts:
        return
    elements.append({"tag": "markdown", "content": "**要点**"})
    # Feishu chart element_id 限 20 字符、须字母开头、仅字母数字下划线；务必经
    # _feishu_element_id 归一化，否则后端较长的 chart_id（如 company_realtime_revenue）
    # 会触发 300301 卡片创建失败。
    seen: set[str] = set()
    seq = 0
    for item in illustrated_facts:
        text = str(item.get("text") or "").strip()
        chart = item.get("chart")
        if chart:
            cid = str(chart.get("chart_id") or "gd_cmp")
            eid = _feishu_element_id(cid, seq=seq)
            while eid in seen:
                seq += 1
                eid = _feishu_element_id(cid, seq=seq)
            seen.add(eid)
            seq += 1
            el = chart_spec_to_feishu_element(chart, element_id=eid)
            if el:
                elements.append(el)
        if text:
            elements.append({"tag": "markdown", "content": f"• {text}"})


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


_TABLE_SEP_RE = re.compile(r"^\|?[\s:|\-]+\|?$")


def _clean_citation_snippet(snippet: str) -> str:
    """把原始表格 markdown 压成一行可读摘要：去掉 `| --- |` 分隔行、标题井号，
    单元格竖线转成轻量分隔符，多余空白折叠（#3 防御兜底）。"""
    parts: list[str] = []
    for ln in snippet.splitlines():
        s = ln.strip()
        if not s or _TABLE_SEP_RE.match(s):
            continue
        s = s.lstrip("#").strip()
        s = re.sub(r"\s*\|\s*", " · ", s).strip(" ·")
        if s:
            parts.append(s)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


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
        snippet = _clean_citation_snippet(c.get("snippet") or "")
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


def _adhoc_index_column(col: dict[str, Any]) -> bool:
    key = (col.get("key") or "").lower()
    label = (col.get("display_name") or col.get("label") or "").strip()
    return key in ("idx", "index", "seq", "序号") or label in ("#", "序号")


def _adhoc_column_def(col: dict[str, Any], *, is_first: bool) -> dict[str, Any]:
    key = col.get("key") or ""
    label = col.get("display_name") or col.get("label") or key
    col_type = (col.get("type") or "string").lower()
    if _adhoc_index_column(col):
        col_type = "string"
    width = col.get("width") or ("auto" if _adhoc_index_column(col) else ("140px" if is_first else "auto"))
    if col_type == "number":
        return {
            "name": key,
            "display_name": label,
            "data_type": "number",
            "width": width,
            "horizontal_align": "right",
            "format": {"separator": True, "precision": 2},
        }
    align = "center" if _adhoc_index_column(col) else "left"
    return {
        "name": key,
        "display_name": label,
        "data_type": "text",
        "width": width,
        "vertical_align": "top",
        "horizontal_align": align,
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
            # Allow two-line headers so role+date (e.g. "对比日" / "2026-05-30")
            # wrap instead of truncating behind the column edge.
            "lines": 2,
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
    # render_mode=markdown：单元格带 <font> 着色/ <br> 多行（如「变化量+变化率」红跌绿涨），
    # 飞书原生 table 单元格是纯文本不渲染富文本，故强制走 Markdown（不占用原生表配额）。
    force_md = str(table.get("render_mode") or "").lower() == "markdown"
    if not force_md and native_budget[0] > 0:
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
    table_md = _adhoc_table_markdown(table, heading=None, rich=force_md)
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
    rich: bool = False,
) -> str:
    """Generic markdown table from platform answer.adhoc_table.

    rich=True (render_mode=markdown): cells are already Markdown-ready and may
    carry inline <font>/<br> (e.g. colored 变化量+变化率). Such cells must NOT be
    run through _format_adhoc_cell (which truncates at 48 chars and would corrupt
    the markup); only a raw pipe is escaped and \n is normalized to <br>.
    """
    if not table:
        return ""
    cols = table.get("columns") or []
    rows = table.get("rows") or []
    if not rows:
        return f"**{heading or '查询结果'}**\n<font color='grey'>无匹配行。</font>"
    if not cols:
        cols = [{"key": k, "label": k, "type": "string"} for k in rows[0].keys()]

    # Markdown table cells/headers must be single-line and not contain a raw pipe,
    # else the row breaks across lines (curated 2-line headers like "对比日\n2026-06-01"
    # otherwise split into phantom rows). Native tables handle \n; the Markdown
    # fallback (when the 5-native-table budget is spent) must sanitize it.
    def _md_cell(value: Any) -> str:
        return str(value if value is not None else "").replace("\n", " ").replace("|", "/").strip()

    # Rich cells keep <font>/<br>; an embedded \n becomes <br> (line break in cell).
    def _rich_cell(value: Any) -> str:
        return str(value if value is not None else "").replace("|", "/").replace("\n", "<br>").strip()

    headers = [_md_cell(c.get("label") or c.get("key") or "?") for c in cols]
    lines: list[str] = []
    # heading=None means a section already rendered its own title above — avoid a
    # redundant "查询结果" line. Curated section tables are NOT raw SQL dumps, so the
    # misleading "原始行（最多展示 N 行）" caption is dropped here.
    if heading:
        lines.append(f"**{heading}**")
    lines.extend(
        [
            "",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
    )
    display = rows[:max_rows]
    for row in display:
        if rich:
            cells = [_rich_cell(row.get(c.get("key", ""))) for c in cols]
        else:
            cells = [
                _md_cell(
                    _format_adhoc_cell(row.get(c.get("key", "")), c.get("type", "string"))
                )
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


def build_adhoc_result_card_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Feishu card for query_mode=adhoc (catalog.adhoc)."""
    answer = payload.get("answer") or {}
    rendering = payload.get("rendering") or {}
    preferred = rendering.get("preferred", "table")
    charts = answer.get("charts") or []
    illustrated_facts = answer.get("illustrated_facts") or []
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
    sections = answer.get("sections") or []
    table_seq = [0]
    native_budget = [_MAX_FEISHU_NATIVE_TABLES]
    # 整张卡片共享一个图表 ElementID 去重集合，保证 ID 全局唯一。
    used_section_chart_ids: set[str] = set()
    # 顶层 charts 与各 section 的图必须共用同一个去重集合：多维拆分（adhoc_multidim）时
    # 顶层 charts 是第 1 个维度的图、后续维度在 sections 里，两处若各用一套集合都从 seq=0
    # 起算，且多维图 chart_id（multidim_*）归一化后同为「multid」，会生成相同 ElementID
    #（如 gmultid0），触发飞书 300301「Duplicate ID」整卡创建失败。
    # 只在没有 illustrated_facts（每指标内嵌图）时才渲染顶层汇总图表块。
    if charts and not illustrated_facts:
        _append_chart_blocks(
            elements,
            charts,
            max_charts=3,
            heading="**图表**",
            trace_id=trace_id,
            used_chart_ids=used_section_chart_ids,
        )
    if not chart_only:
        adhoc_tbl = answer.get("adhoc_table")
        if adhoc_tbl:
            # Main comparison table ALWAYS renders first — drill-down sections
            # must not suppress the root table (previously an `if sections /
            # elif` made the root table vanish whenever a section existed).
            _append_native_table_or_markdown(
                elements,
                table=adhoc_tbl,
                heading="查询结果",
                table_seq=table_seq,
                native_budget=native_budget,
            )
            if facts_md and not illustrated_facts and not sections:
                elements.append({"tag": "markdown", "content": f"**要点**\n{facts_md}"})
        elif facts_md and not charts and not sections:
            elements.append({"tag": "markdown", "content": f"**说明**\n{facts_md}"})
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
                # heading=None: _section_header_element(sec) 上面已渲染过 sec.title，
                # 这里再传 heading 会把同一标题打印第二遍（用户反馈「表格标题重复了一遍」）。
                _append_native_table_or_markdown(
                    elements,
                    table=sec.get("adhoc_table"),
                    heading=None,
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
                    used_chart_ids=used_section_chart_ids,
                )
    elif facts_md and not illustrated_facts:
        elements.append({"tag": "markdown", "content": f"**要点**\n{facts_md}"})
    # illustrated_facts: 每个指标带一个内嵌小图，放在 sections 之后、引用之前。
    if illustrated_facts:
        _render_illustrated_facts(elements, illustrated_facts, trace_id)
    elif facts_md and sections:
        elements.append({"tag": "markdown", "content": f"**要点**\n{facts_md}"})

    rag_md = _lineage_rag_block(answer.get("rag_citations") or [])
    if rag_md:
        elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": rag_md})
    exp_md = _lineage_experience_block(answer.get("experience_reuse"))
    if exp_md:
        elements.append({"tag": "markdown", "content": exp_md})
    # 卡片末尾「反馈与沉淀」文案与按钮（有用/Bad Case/沉淀模板候选）暂时下线（用户要求）。

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


# ---------------------------------------------------------------------------
# Self-verification cards (SSE: document.verification.result)
# Backend emits apiv1.VerificationCard[]; one追发卡片汇总每条假设的回算结论。
# See docs/mvp/design/19-自验证闭环归因-方案设计.md.
# ---------------------------------------------------------------------------

# verdict → (徽标文案, 字色)
_VERDICT_BADGES: dict[str, tuple[str, str]] = {
    "confirmed": ("✅ 已证实", "green"),
    "refuted": ("❌ 已证伪", "red"),
    "inconclusive": ("➖ 数据不确定", "grey"),
    "unverifiable": ("⚠️ 暂无法验证", "grey"),
    "listed": ("🕓 待验证（超预算未执行）", "grey"),
}


_GW_ENCODING_ERR_RE = re.compile(r"unsupported format character", re.IGNORECASE)
_GW_RAW_ERR_RE = re.compile(r"[：:]\s*8380 error:.*", re.DOTALL)


def _clean_caliber(caliber: str) -> str:
    """将网关原始错误消息（JSON blob）替换为对用户可读的说明。"""
    if not caliber.startswith("执行失败"):
        return caliber
    if _GW_ENCODING_ERR_RE.search(caliber):
        return "执行失败：查询含特殊字符（中文 LIKE 条件），数据网关暂不支持；可手动从文档查找相关活动配置"
    # 去除 8380 error: {...} 原始 JSON，保留前缀说明
    cleaned = _GW_RAW_ERR_RE.sub("：数据网关返回错误，无法执行此查询", caliber, count=1)
    return cleaned


def _verification_item_md(card: dict[str, Any]) -> str:
    verdict = str(card.get("verdict") or "listed")
    label, color = _VERDICT_BADGES.get(verdict, _VERDICT_BADGES["listed"])
    hypothesis = str(card.get("hypothesis") or "").strip()
    question = str(card.get("question") or "").strip()
    check_index = int(card.get("check_index") or 0)
    # 序号引用：与上文「建议核对的数据」中同编号条目显式呼应。
    idx_ref = f"**{check_index}.** " if check_index > 0 else ""
    # 首行：序号 + 判定徽章 + 假设摘要
    head = hypothesis or question
    lines = [f"{idx_ref}<font color='{color}'>**{label}**</font> **验证假设：**{head}"]
    # 当有独立的假设原文时，把实际查询做法另起一行
    if hypothesis and question and question != hypothesis:
        lines.append(f"<font color='grey'>验证做法：{question}</font>")
    evidence = str(card.get("evidence") or "").strip()
    if evidence:
        lines.append(f"<font color='grey'>证据数据：{evidence}</font>")
    caliber = _clean_caliber(str(card.get("caliber") or "").strip())
    if caliber:
        lines.append(f"<font color='grey'>口径：{caliber}</font>")
    need_fields = [str(x) for x in (card.get("need_fields") or []) if str(x).strip()]
    if need_fields:
        lines.append(f"<font color='grey'>需补字段：{', '.join(need_fields)}</font>")
    digest = str(card.get("sql_digest") or "").strip()
    if digest:
        lines.append(f"<font color='grey'>SQL digest `{digest}`</font>")
    return "\n".join(lines)


def build_verification_cards_json(payload: dict[str, Any]) -> dict[str, Any]:
    """结论自验证追发卡片：汇总每条可核假设的数仓回算结论（SSE 追发）。"""
    cards = payload.get("cards") or []
    trace_id = str(payload.get("trace_id") or "")
    elements: list[dict[str, Any]] = [
        {
            "tag": "markdown",
            "content": (
                "<font color='grey'>承接上文「建议核对的数据」：系统用真实数仓数据，"
                "对结论中每条可核假设做了自动回算。"
                "**下列各条编号与上文「建议核对的数据」序号一一对应**，"
                "可据「证据数据」自行复核。</font>"
            ),
        }
    ]
    for i, card in enumerate(cards):
        if i:
            elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": _verification_item_md(card)})
    if trace_id:
        elements.append({"tag": "hr"})
        elements.append(
            {"tag": "markdown", "content": f"<font color='grey'>trace `{trace_id}`</font>"}
        )
    return _make_feishu_card(
        title="结论自验证",
        subtitle="闭环归因 · 数仓回算",
        elements=elements,
        template="turquoise",
    )


def build_result_card_json(payload: dict[str, Any]) -> dict[str, Any]:
    answer = payload.get("answer") or {}
    qm = answer.get("query_mode") or ""
    if qm in ("adhoc", "realtime_consume") or answer.get("adhoc_table"):
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


def build_progress_card(content: str = "") -> dict[str, Any]:
    """A lightweight 处理中 card for paths that can't use the streaming card
    (e.g. card.action.trigger 澄清按钮回调)，so点击按钮后立刻有「正在分析」反馈，
    避免长查询期间用户以为机器人挂掉。"""
    text = (content or "").strip() or "已收到，正在汇总数据，请稍候…"
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "正在分析"},
            "template": "blue",
        },
        "body": {
            "elements": [
                {"tag": "markdown", "content": f"⏳ {text}"},
            ]
        },
    }


def build_p2p_only_plain() -> str:
    return "【当前仅支持飞书单聊】\n请在飞书应用中与机器人单聊提问，群聊暂不支持问数（p2p_only）。"


def card_json_to_plain_fallback(card: dict[str, Any]) -> str:
    return json.dumps(card, ensure_ascii=False, indent=2)[:3500]
