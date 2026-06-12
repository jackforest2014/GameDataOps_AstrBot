"""Map platform answer.charts[] to Feishu VChart chart elements."""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

# 近一周 / 前一周（深蓝 + 浅蓝）
_PERIOD_COLORS = ["#3370FF", "#85A5FF"]
_PERIOD_DOMAIN = ["近一周", "前一周"]

# 当日实时四窗累积曲线配色（对齐 EPM F3）：今天=红、昨天=蓝、一周前=绿、一月前=紫，
# 跨所有指标图固定一致。公司大盘实时(company_realtime)窗名为具体星期/日期(动态)，
# 改用按 dataset 顺序的位置配色(_realtime_cum_color_scale)，与此处颜色一一对应。
_REALTIME_CONSUME_DOMAIN = ["今天", "昨天", "一周前", "一月前"]
_REALTIME_CONSUME_COLORS = ["#E53935", "#1E88E5", "#43A047", "#8E24AA"]

# 横向条形图：条厚与容器高度（飞书 chart 支持 height=NNpx 固定高度）
_BAR_MAX_WIDTH = 10
_WK_CMP_BAR_MAX_WIDTH = 18
_WK_CMP_BAR_HEIGHT_PX = 72
_WK_CMP_LEGEND_HEIGHT_PX = 34
_DAILY_BAR_BAND_PX = 14
_DAILY_BAR_BASE_PX = 28
# 少类目排行横条（如 游戏充值 Top-N）：柱体更粗、行高适中，避免被压成发丝线，
# 也不要像默认 4:3 那样把几根柱子拉得很开。
_RANK_BAR_MAX_WIDTH = 24
_RANK_BAR_BAND_PX = 40
_RANK_BAR_BASE_PX = 28
# 按日流水折线：横轴日期、留足左侧与底部标签区
_DAILY_LINE_HEIGHT_PX = 240
_DAILY_LINE_ASPECT = "5:2"


def _realtime_consume_color_scale(*, field: str = "period") -> dict[str, Any]:
    return {
        "type": "ordinal",
        "field": field,
        "domain": _REALTIME_CONSUME_DOMAIN,
        "range": _REALTIME_CONSUME_COLORS,
    }


def _realtime_cum_color_scale(datasets: list[dict[str, Any]], field: str) -> dict[str, Any]:
    """按 dataset 顺序的位置配色：第1条(今天)=红、第2=蓝、第3=绿、第4=紫。
    公司大盘实时窗名是具体星期/日期(动态)，无法用静态 domain 匹配，故按序映射，
    保证「今天恒为红」等规格在所有指标图上一致。"""
    names = [str(d.get("name") or "") for d in datasets if d.get("name")]
    rng = _REALTIME_CONSUME_COLORS
    if not names:
        return {"type": "ordinal", "field": field, "range": rng}
    return {
        "type": "ordinal",
        "field": field,
        "domain": names,
        "range": rng[: len(names)] if len(names) <= len(rng) else rng,
    }


def _realtime_consume_label_indices(labels: list[str], anchor_idx: int | None, *, step: int = 6) -> set[int]:
    """Sample ~every 3h on axis; always include anchor bucket."""
    n = len(labels)
    if n == 0:
        return set()
    show = {i for i in range(0, n, max(step, 1))}
    show.add(n - 1)
    if anchor_idx is not None and 0 <= int(anchor_idx) < n:
        show.add(int(anchor_idx))
    return show


def _realtime_consume_values_sampled(
    values: list[dict[str, Any]],
    labels: list[str],
    anchor_idx: int | None,
    *,
    series_field: str,
    label_step: int = 6,
) -> list[dict[str, Any]]:
    """Sparse value labels on the curve (today series only) to avoid clutter."""
    if not values or not labels:
        return values
    idx_by_label = {lab: i for i, lab in enumerate(labels)}
    show_idx = _realtime_consume_label_indices(labels, anchor_idx, step=label_step)
    out: list[dict[str, Any]] = []
    for row in values:
        r = dict(row)
        lab = str(r.get("label") or "")
        i = idx_by_label.get(lab)
        period = str(r.get(series_field) or "")
        if period == "今天" and i is not None and i in show_idx and "value" in r:
            r["valueLabel"] = r["value"]
        out.append(r)
    return out


def _realtime_consume_cum_chart_body(
    spec: dict[str, Any],
    values: list[dict[str, Any]],
    *,
    title: str,
    x_field: str,
    y_field: str,
    series_field: str,
) -> dict[str, Any]:
    labels = spec.get("labels") or []
    datasets = spec.get("datasets") or []
    chart_id = str(spec.get("chart_id") or "")
    # 公司大盘实时(rt_*)：点状折线、无数值标签(太密)、按序位置配色。
    is_company_rt = chart_id.startswith("rt_")
    anchor_idx = spec.get("anchor_bucket_index")
    if anchor_idx is not None:
        try:
            anchor_idx = int(anchor_idx)
        except (TypeError, ValueError):
            anchor_idx = None
    if not is_company_rt:
        values = _realtime_consume_values_sampled(
            values, labels, anchor_idx, series_field=series_field,
        )
    x_title = str(spec.get("x_axis_title") or "时间")
    y_title = str(spec.get("y_axis_title") or "累积点券（万）")
    if is_company_rt:
        color_scale = _realtime_cum_color_scale(datasets, series_field)
        point_cfg: dict[str, Any] = {"visible": True, "style": {"size": 4}}
        label_cfg: dict[str, Any] = {"visible": False}
    else:
        color_scale = _realtime_consume_color_scale(field=series_field)
        point_cfg = {"visible": False}
        label_cfg = {
            "visible": True,
            "field": "valueLabel",
            "position": "top",
            "style": {"fontSize": 9},
            "overlap": False,
        }
    body: dict[str, Any] = {
        "type": "line",
        "media": [],
        "title": {"text": title, "textStyle": {"fontSize": 12}},
        "data": {"values": values},
        "xField": x_field,
        "yField": y_field,
        "seriesField": series_field,
        "color": color_scale,
        "point": point_cfg,
        "line": {"style": {"lineWidth": 2.5, "curveType": "monotone"}},
        "label": label_cfg,
        "legends": _chart_legends(orient="top"),
        "padding": {"top": 24, "bottom": 48, "left": 56, "right": 16},
        "axes": [
            {
                "orient": "left",
                "title": {"visible": True, "text": y_title, "textStyle": {"fontSize": 10}},
                "label": {"style": {"fontSize": 10}},
            },
            {
                "orient": "bottom",
                "title": {"visible": True, "text": x_title, "textStyle": {"fontSize": 10}},
                "label": {
                    "style": {"fontSize": 9},
                    "autoHide": True,
                    "autoHideMethod": "greedy",
                },
            },
        ],
    }
    if anchor_idx is not None and 0 <= anchor_idx < len(labels):
        anchor_x = labels[anchor_idx]
        body["markLine"] = [
            {
                "x": anchor_x,
                "label": {"text": "锚点", "position": "end", "style": {"fontSize": 9}},
                "line": {"style": {"stroke": "#9E9E9E", "lineDash": [4, 4]}},
            }
        ]
    return body


def _period_color_scale(*, field: str | None = "period") -> dict[str, Any]:
    """按 period 着色；周对比子图传 field，折线 seriesField 可不传 field。"""
    scale: dict[str, Any] = {
        "type": "ordinal",
        "domain": _PERIOD_DOMAIN,
        "range": _PERIOD_COLORS,
    }
    if field:
        scale["field"] = field
    return scale


def _chart_legends(*, orient: str = "top") -> dict[str, Any]:
    return {"visible": True, "orient": orient, "position": "end"}


def _compact_chart_padding() -> dict[str, int]:
    return {"top": 2, "bottom": 2, "left": 6, "right": 8}


def _height_for_horizontal_bars(n_bands: int, *, per_band: int, base: int) -> int:
    n = max(n_bands, 1)
    return min(base + n * per_band, 200)


def _make_chart_element(
    chart_body: dict[str, Any],
    *,
    element_id: str,
    height_px: int | None = None,
    aspect_ratio: str = "4:3",
    margin: str = "0",
    color_theme: str | None = "brand",
) -> dict[str, Any]:
    el: dict[str, Any] = {
        "tag": "chart",
        "element_id": element_id,
        "preview": True,
        "margin": margin,
        "chart_spec": chart_body,
    }
    if color_theme:
        el["color_theme"] = color_theme
    if height_px and height_px > 0:
        el["height"] = f"{height_px}px"
    else:
        el["aspect_ratio"] = aspect_ratio
    return el


def _pie_values_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """双周计费点饼图：data_rows 携带完整名称与涨跌副标题（供外侧连线标签）。"""
    rows = spec.get("data_rows") or []
    if not rows:
        return []
    values: list[dict[str, Any]] = []
    for r in rows:
        name = str(r.get("label") or "").strip()
        if not name:
            continue
        detail = str(r.get("metric") or "").strip()
        val = round(float(r.get("value") or 0), 2)
        label_text = f"{name}\n{detail}" if detail else name
        values.append({"label": name, "value": val, "labelText": label_text})
    return values


def _is_wow_billing_pie(spec: dict[str, Any]) -> bool:
    cid = str(spec.get("chart_id") or "")
    return cid.startswith("wow_") and (spec.get("type") or "") == "pie"


def _chart_values_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    labels = spec.get("labels") or []
    datasets = spec.get("datasets") or []
    series_field = spec.get("series_field") or "period"
    if len(datasets) > 1 and series_field:
        values: list[dict[str, Any]] = []
        for ds in datasets:
            period = ds.get("name") or "series"
            ds_vals = ds.get("values") or []
            for i, label in enumerate(labels):
                row: dict[str, Any] = {"label": label, series_field: period}
                if i < len(ds_vals):
                    row["value"] = round(float(ds_vals[i]), 2)
                values.append(row)
        return values
    values = []
    ds0 = datasets[0] if datasets else {}
    ds_vals = ds0.get("values") or []
    for i, label in enumerate(labels):
        row: dict[str, Any] = {"label": label}
        if i < len(ds_vals):
            row["value"] = round(float(ds_vals[i]), 2)
        values.append(row)
    return values


def _metric_value_label(metric: str, value: float) -> str:
    if any(k in metric for k in ("付费率", "溢价", "留存")):
        return f"{value:.2f}%"
    return f"{value:.2f}"


def _period_panel_legends() -> dict[str, Any]:
    """显式图例项：无 seriesField 时 VChart 会用 bar_* 内部 id 当图例文案。"""
    return {
        "visible": True,
        "orient": "top",
        "position": "end",
        "padding": {"top": 0, "bottom": 2},
        "maxRow": 1,
        "autoPage": False,
        "select": False,
        "data": [
            {
                "label": "近一周",
                "value": "近一周",
                "shape": {
                    "symbolType": "square",
                    "style": {"fill": _PERIOD_COLORS[0], "size": 8},
                },
            },
            {
                "label": "前一周",
                "value": "前一周",
                "shape": {
                    "symbolType": "square",
                    "style": {"fill": _PERIOD_COLORS[1], "size": 8},
                },
            },
        ],
    }


def _period_panel_legends_hidden() -> dict[str, Any]:
    return {"visible": False}


def panel_has_week_compare_legend(elements: list[dict[str, Any]]) -> bool:
    return any(is_week_compare_legend_chart(el) for el in elements)


def is_week_compare_legend_chart(el: dict[str, Any]) -> bool:
    eid = str(el.get("element_id") or "")
    return el.get("tag") == "chart" and eid.startswith("gwkLeg")


def _week_compare_legend_chart_body() -> dict[str, Any]:
    """仅渲染图例，不占指标子图绘图区（避免挤压 Y 轴与横向宽度）。"""
    return {
        "type": "bar",
        "media": [],
        "padding": {"top": 0, "bottom": 0, "left": 4, "right": 4},
        "data": {
            "values": [
                {"period": "近一周", "value": 1},
                {"period": "前一周", "value": 1},
            ]
        },
        "direction": "horizontal",
        "xField": "value",
        "yField": "period",
        "seriesField": "period",
        "color": _period_color_scale(field="period"),
        "bar": {"style": {"fillOpacity": 0}},
        "label": {"visible": False},
        "axes": [
            {"orient": "left", "visible": False},
            {"orient": "bottom", "visible": False, "grid": {"visible": False}},
        ],
        "legends": _period_panel_legends(),
    }


def _week_compare_legend_element(*, element_id: str) -> dict[str, Any]:
    return _make_chart_element(
        _week_compare_legend_chart_body(),
        element_id=element_id,
        height_px=_WK_CMP_LEGEND_HEIGHT_PX,
        margin="0 0 4px 0",
        color_theme=None,
    )


def _prepend_week_compare_legend_block(
    elements: list[dict[str, Any]], *, element_id: str = "wk_legend"
) -> None:
    """卡片分片顶部：标题 + 独立图例条（不修改指标子图）。"""
    if any(is_week_compare_legend_chart(el) for el in elements):
        return
    insert_at = 0
    for i, el in enumerate(elements):
        if el.get("tag") == "markdown" and "周对比（7 项）" in (el.get("content") or ""):
            insert_at = i + 1
            break
        if el.get("tag") == "chart":
            insert_at = i
            break
    if not any(
        el.get("tag") == "markdown" and "周对比（7 项）" in (el.get("content") or "")
        for el in elements
    ):
        elements.insert(insert_at, {"tag": "markdown", "content": "**周对比（7 项）**"})
        insert_at += 1
    elements.insert(
        insert_at,
        _week_compare_legend_element(element_id=_feishu_element_id(element_id, seq=0)),
    )


def _normalize_week_compare_values(
    items: list[dict[str, Any]], metric: str
) -> list[dict[str, Any]]:
    """保证近一周、前一周各一条，并写入行级 fill 色（绕过飞书 brand 主题覆盖）。"""
    by_period: dict[str, float] = {}
    for it in items:
        p = str(it.get("period") or "").strip()
        if p:
            by_period[p] = round(float(it.get("value") or 0), 2)
    values: list[dict[str, Any]] = []
    for period in _PERIOD_DOMAIN:
        if period not in by_period:
            continue
        val = by_period[period]
        values.append(
            {
                "period": period,
                "value": val,
                "labelText": _metric_value_label(metric, val),
            }
        )
    return values


def _week_compare_mini_chart_body(values: list[dict[str, Any]]) -> dict[str, Any]:
    """单指标 P1 vs P2：seriesField=period 配色；图例由独立 gwkLeg 条渲染。"""
    body: dict[str, Any] = {
        "type": "bar",
        "media": [],
        "padding": {"top": 6, "bottom": 6, "left": 56, "right": 14},
        "data": {"values": values},
        "direction": "horizontal",
        "xField": "value",
        "yField": "period",
        "seriesField": "period",
        "color": _period_color_scale(field="period"),
        "barMaxWidth": _WK_CMP_BAR_MAX_WIDTH,
        "label": {"visible": True, "field": "labelText"},
        "axes": [
            {
                "orient": "left",
                "type": "band",
                "domain": _PERIOD_DOMAIN,
                "bandPaddingInner": 0.22,
                "bandPaddingOuter": 0.08,
                "label": {
                    "visible": True,
                    "style": {"fontSize": 10},
                    "flush": True,
                },
            },
            {
                "orient": "bottom",
                "label": {"style": {"fontSize": 9}},
                "grid": {"style": {"lineDash": [4, 4]}},
            },
        ],
    }
    body["legends"] = _period_panel_legends_hidden()
    return body


def annotate_first_chart_legend(elements: list[dict[str, Any]]) -> None:
    """续卡分片：顶部独立图例条，指标子图规格与首张保持一致。"""
    _prepend_week_compare_legend_block(elements)


def _group_data_rows(rows: list[dict[str, Any]]) -> OrderedDict[str, list[dict[str, Any]]]:
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for r in rows:
        metric = str(r.get("metric") or "")
        if not metric:
            continue
        grouped.setdefault(metric, []).append(r)
    return grouped


def week_compare_panel_elements(
    spec: dict[str, Any], *, element_id: str | None = None
) -> list[dict[str, Any]]:
    """表3：7 个紧凑横向子图；用固定 height 缩小飞书 chart 占位，而非仅变细条。"""
    rows = spec.get("data_rows") or []
    grouped = _group_data_rows(rows)
    if not grouped:
        return []

    base_id = element_id or spec.get("chart_id") or "wkPan"
    elements: list[dict[str, Any]] = [
        {"tag": "markdown", "content": "**周对比（7 项）**"},
        _week_compare_legend_element(
            element_id=_feishu_element_id("wk_legend", seq=0)
        ),
    ]
    for seq, (metric, items) in enumerate(grouped.items()):
        values = _normalize_week_compare_values(items, metric)
        if len(values) < 2:
            continue
        eid = _feishu_element_id(base_id, seq=seq)
        chart_body = _week_compare_mini_chart_body(values)
        height_px = _WK_CMP_BAR_HEIGHT_PX
        elements.append({"tag": "markdown", "content": f"**{metric}**"})
        elements.append(
            _make_chart_element(
                chart_body,
                element_id=eid,
                height_px=height_px,
                margin="0 0 2px 0",
                color_theme=None,
            )
        )
    return elements


def chart_spec_to_feishu_element(spec: dict[str, Any], *, element_id: str | None = None) -> dict[str, Any] | None:
    labels = spec.get("labels") or []
    datasets = spec.get("datasets") or []
    data_rows = spec.get("data_rows") or []
    if not labels and not datasets and not data_rows:
        return None
    chart_id = str(spec.get("chart_id") or "")
    chart_type = spec.get("type") or "bar"
    if chart_type == "pie" and spec.get("data_rows"):
        values = _pie_values_from_spec(spec)
    else:
        values = _chart_values_from_spec(spec)
    if not values:
        return None
    title = spec.get("title") or ""
    x_field = spec.get("x_field") or "label"
    y_field = spec.get("y_field") or "value"
    series_field = spec.get("series_field") or ""
    multi_series = len(datasets) > 1 and bool(series_field)

    ds0 = datasets[0] if datasets else {}
    y_name = ds0.get("name") or "value"
    if multi_series:
        y_name = "数值"

    # 实时累积曲线（当日点券消耗 realtime_consume_cum，以及公司大盘实时 rt_* 各指标）：
    # 统一走专用 body —— Y 轴用后端 y_axis_title(具体指标名)、四窗固定配色、今天截止
    # 锚点竖虚线。识别信号：多序列折线 + 携带 anchor_bucket_index。
    is_rt_cum_chart = (
        chart_type == "line"
        and multi_series
        and bool(series_field)
        and (chart_id == "realtime_consume_cum" or spec.get("anchor_bucket_index") is not None)
    )
    if is_rt_cum_chart:
        chart_body = _realtime_consume_cum_chart_body(
            spec,
            values,
            title=title,
            x_field=x_field,
            y_field=y_field,
            series_field=series_field,
        )
        return _make_chart_element(
            chart_body,
            element_id=element_id or chart_id or "gd_rt_cum",
            height_px=300,
            aspect_ratio="16:9",
            margin="8px 4px",
        )

    if chart_type == "pie":
        category_field = x_field or "label"
        wow_pie = _is_wow_billing_pie(spec)
        # Attach a per-slice percent string so non-wow pies can show 占比 inside
        # each slice (the user asked for in-slice percentages).
        if not wow_pie:
            total = sum(float(v.get(y_field, v.get("value", 0)) or 0) for v in values)
            if total > 0:
                for v in values:
                    raw = float(v.get(y_field, v.get("value", 0)) or 0)
                    v["percent"] = f"{raw / total * 100:.1f}%"
        chart_body: dict[str, Any] = {
            "type": "pie",
            "media": [],
            "title": {"text": title, "textStyle": {"fontSize": 12}},
            "data": {"values": values},
            "valueField": y_field,
            "categoryField": category_field,
            "outerRadius": 0.78 if wow_pie else 0.9,
            "padding": (
                {"top": 20, "bottom": 20, "left": 12, "right": 12}
                if wow_pie
                else {"top": 8, "bottom": 8, "left": 8, "right": 8}
            ),
            "label": (
                {
                    "visible": True,
                    "position": "outside",
                    "field": "labelText",
                    "style": {"fontSize": 9, "lineHeight": 13},
                    "line": {"visible": True},
                }
                if wow_pie
                else {
                    "visible": True,
                    "position": "inside",
                    "formatter": "{percent}",
                    "style": {"fill": "#ffffff", "fontSize": 10},
                }
            ),
            "legends": (
                {"visible": False}
                if wow_pie
                else {
                    "visible": True,
                    "orient": "right",
                    "position": "end",
                    "maxRow": 2,
                }
            ),
        }
        n_slices = len(values)
        if wow_pie:
            height_px = min(520, 300 + max(0, n_slices - 6) * 14)
            aspect_ratio = "4:3"
            margin = "4px 0"
        else:
            height_px = min(360, 200 + max(0, n_slices - 8) * 8)
            aspect_ratio = "1:1"
            margin = "8px 4px"
        return _make_chart_element(
            chart_body,
            element_id=element_id or chart_id or "gd_pie",
            height_px=height_px,
            aspect_ratio=aspect_ratio,
            margin=margin,
        )

    is_line = chart_type == "line"
    # "vertical" direction → column chart (x=categories, y=values).
    # Default for single-series bar is horizontal; multi-series stays vertical.
    force_vertical = spec.get("direction") == "vertical"
    use_horizontal = chart_type == "bar" and not multi_series and not force_vertical
    is_daily_revenue = chart_id in ("p1_revenue_bar", "p2_revenue_bar")
    is_daily_trend_line = is_daily_revenue and is_line

    chart_body: dict[str, Any] = {
        "type": "line" if is_line else "bar",
        "title": {"text": title, "textStyle": {"fontSize": 12}},
        "data": {"values": values},
        "label": {"visible": not is_line and not is_daily_trend_line},
    }
    height_px: int | None = None
    margin = "0"
    aspect_ratio = "4:3"

    if is_daily_trend_line:
        n_pts = max(len(labels), len(values), 1)
        chart_body["type"] = "line"
        chart_body["xField"] = x_field
        chart_body["yField"] = y_field
        chart_body["padding"] = {"top": 16, "bottom": 36, "left": 52, "right": 20}
        chart_body["point"] = {
            "visible": True,
            "style": {
                "size": 8,
                "fill": "#3370FF",
                "stroke": "#ffffff",
                "lineWidth": 1,
            },
        }
        chart_body["line"] = {"style": {"lineWidth": 2.5, "curveType": "monotone"}}
        chart_body["axes"] = [
            {
                "orient": "left",
                "title": {
                    "visible": True,
                    "text": "流水（万元）",
                    "textStyle": {"fontSize": 10},
                },
                "label": {"style": {"fontSize": 10}},
            },
            {
                "orient": "bottom",
                "title": {"visible": False},
                "label": {
                    "visible": True,
                    "style": {"fontSize": 10},
                },
                "paddingInner": 0.25,
                "paddingOuter": 0.12,
            },
        ]
        height_px = min(280, _DAILY_LINE_HEIGHT_PX + max(0, n_pts - 7) * 6)
        aspect_ratio = _DAILY_LINE_ASPECT
        margin = "8px 4px"
    elif multi_series and series_field:
        chart_body["seriesField"] = series_field
        chart_body["xField"] = x_field
        chart_body["yField"] = y_field
        chart_body["color"] = _period_color_scale(field=None)
        chart_body["legends"] = _chart_legends(orient="top")
        if is_line:
            chart_body["point"] = {"visible": True}
            chart_body["line"] = {"style": {"lineWidth": 2}}
        chart_body["axes"] = [
            {"orient": "left", "title": {"visible": True, "text": y_name}},
            {"orient": "bottom", "title": {"visible": False}},
        ]
    elif use_horizontal:
        chart_body["media"] = []
        chart_body["padding"] = _compact_chart_padding()
        chart_body["direction"] = "horizontal"
        chart_body["xField"] = y_field
        chart_body["yField"] = x_field
        chart_body["axes"] = [
            {
                "orient": "left",
                "bandPaddingInner": 0.35,
                "bandPaddingOuter": 0.12,
                "label": {"style": {"fontSize": 10}},
            },
            {
                "orient": "bottom",
                "title": {
                    "visible": True,
                    "text": y_name if "万" in y_name else f"{y_name}（万元）",
                    "textStyle": {"fontSize": 10},
                },
                "label": {"style": {"fontSize": 9}},
            },
        ]
        # Compact height for single-series horizontal bars: a tall 4:3 canvas
        # stretches a few rows far apart. Size height to band count to keep
        # spacing tight. Daily charts have many thin bars; ranking charts have a
        # few categories and need thicker, clearly-visible bars.
        if not is_line:
            if is_daily_revenue:
                chart_body["barMaxWidth"] = _BAR_MAX_WIDTH
                height_px = _height_for_horizontal_bars(
                    len(labels), per_band=_DAILY_BAR_BAND_PX, base=_DAILY_BAR_BASE_PX
                )
            else:
                chart_body["barMaxWidth"] = _RANK_BAR_MAX_WIDTH
                height_px = _height_for_horizontal_bars(
                    len(labels), per_band=_RANK_BAR_BAND_PX, base=_RANK_BAR_BASE_PX
                )
            margin = "4px 0"
        else:
            chart_body["barMaxWidth"] = _BAR_MAX_WIDTH
        if is_daily_revenue and not is_line:
            chart_body["title"] = {
                "text": title,
                "textStyle": {"fontSize": 11},
                "padding": {"bottom": 0},
            }
    elif force_vertical:
        # 竖直双柱比较图（上期 vs 本期），x=类目，y=数值。
        n_bars = len(labels) if labels else len(values)
        chart_body["xField"] = x_field
        chart_body["yField"] = y_field
        chart_body["barMaxWidth"] = 48
        chart_body["padding"] = {"top": 20, "bottom": 40, "left": 52, "right": 12}
        chart_body["axes"] = [
            {
                "orient": "left",
                "title": {"visible": True, "text": y_name, "textStyle": {"fontSize": 10}},
                "label": {"style": {"fontSize": 10}},
            },
            {
                "orient": "bottom",
                "title": {"visible": False},
                "label": {"style": {"fontSize": 10}, "autoRotate": False},
            },
        ]
        # 紧凑高度：嵌入 要点 旁边，不占太多空间
        height_px = 160 + max(0, n_bars - 2) * 20
        margin = "4px 0"
    else:
        chart_body["xField"] = x_field
        chart_body["yField"] = y_field
        chart_body["axes"] = [
            {
                "orient": "left",
                "title": {
                    "visible": True,
                    "text": y_name if ("万" in y_name or "%" in title) else y_name,
                },
            },
            {"orient": "bottom", "title": {"visible": False}},
        ]
    if is_line and not multi_series and not is_daily_trend_line:
        chart_body["point"] = {"visible": True}
        chart_body["line"] = {"style": {"lineWidth": 2}}

    return _make_chart_element(
        chart_body,
        element_id=element_id or chart_id or "gd_chart",
        height_px=height_px,
        aspect_ratio=aspect_ratio,
        margin=margin,
    )


_CHART_ID_SHORT: dict[str, str] = {
    "pay_revenue_trend": "payRev",
    "pay_rate_trend": "payRt",
    "p1_revenue_bar": "p1Rev",
    "p2_revenue_bar": "p2Rev",
    "wk_cmp_panel": "wkPan",
    "wk_legend": "wkLeg",
    "revenue_2d": "rev2d",
    "realtime_consume_cum": "rtCum",
    "company_benchmark_daily": "cbDay",
    "company_benchmark_contrib_pie": "cbPie",
}


def _feishu_element_id(chart_id: str, *, seq: int = 0) -> str:
    short = _CHART_ID_SHORT.get(chart_id or "")
    if not short:
        raw = re.sub(r"[^a-zA-Z0-9]", "", chart_id or "chart")
        short = (raw[:6] if raw else "chart").lower()
    eid = f"g{short}{seq}"
    if not eid[0].isalpha():
        eid = f"g_{short}{seq}"
    return eid[:20]


def build_charts_elements(
    charts: list[dict[str, Any]],
    *,
    max_charts: int = 8,
    trace_id: str = "",  # noqa: ARG001
    used_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    seen = used_ids if used_ids is not None else set()
    seq = len(seen)
    for idx, spec in enumerate(charts[:max_charts]):
        cid = str(spec.get("chart_id") or f"chart_{idx}")
        if spec.get("type") == "facet_bar" or cid == "wk_cmp_panel":
            eid = _feishu_element_id(cid, seq=seq)
            while eid in seen:
                seq += 1
                eid = _feishu_element_id(cid, seq=seq)
            seen.add(eid)
            seq += 1
            panel = week_compare_panel_elements(spec, element_id=eid)
            for el in panel:
                if el.get("tag") == "chart":
                    sub_id = el.get("element_id") or eid
                    while sub_id in seen:
                        seq += 1
                        sub_id = _feishu_element_id(cid, seq=seq)
                    seen.add(sub_id)
                    el["element_id"] = sub_id
                    seq += 1
            elements.extend(panel)
            continue

        eid = _feishu_element_id(cid, seq=seq)
        while eid in seen:
            seq += 1
            eid = _feishu_element_id(cid, seq=seq)
        seen.add(eid)
        seq += 1
        el = chart_spec_to_feishu_element(spec, element_id=eid)
        if el:
            elements.append(el)
    return elements
