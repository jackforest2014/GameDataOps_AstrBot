"""Map platform answer.charts[] to Feishu VChart chart elements."""

from __future__ import annotations

from typing import Any


def chart_spec_to_feishu_element(spec: dict[str, Any], *, element_id: str | None = None) -> dict[str, Any] | None:
    labels = spec.get("labels") or []
    datasets = spec.get("datasets") or []
    if not labels and not datasets:
        return None
    values: list[dict[str, Any]] = []
    ds0 = datasets[0] if datasets else {}
    ds_vals = ds0.get("values") or []
    y_name = ds0.get("name") or "value"
    for i, label in enumerate(labels):
        row: dict[str, Any] = {"label": label}
        if i < len(ds_vals):
            row["value"] = float(ds_vals[i])
        values.append(row)
    chart_type = spec.get("type") or "bar"
    title = spec.get("title") or ""
    x_field = spec.get("x_field") or "label"
    y_field = spec.get("y_field") or "value"
    direction = "horizontal" if chart_type == "bar" else "vertical"
    return {
        "tag": "chart",
        "element_id": element_id or spec.get("chart_id") or "gd_chart",
        "aspect_ratio": "4:3",
        "color_theme": "brand",
        "preview": True,
        "chart_spec": {
            "type": chart_type,
            "title": {"text": title},
            "data": {"values": values},
            "direction": direction,
            "xField": y_field if direction == "horizontal" else x_field,
            "yField": x_field if direction == "horizontal" else y_field,
            "axes": [
                {
                    "orient": "bottom" if direction == "vertical" else "left",
                    "title": {"visible": True, "text": y_name},
                }
            ],
            "label": {"visible": True},
        },
    }


def build_charts_elements(
    charts: list[dict[str, Any]],
    *,
    max_charts: int = 5,
) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for idx, spec in enumerate(charts[:max_charts]):
        el = chart_spec_to_feishu_element(spec, element_id=f"gd_chart_{idx}")
        if el:
            elements.append(el)
    return elements
