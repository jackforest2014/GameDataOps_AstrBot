"""WoW billing pie chart Feishu mapping."""

from game_data_ai.charts import chart_spec_to_feishu_element


def test_wow_pie_hides_legend_and_uses_leader_labels():
    spec = {
        "chart_id": "wow_gain_pie",
        "type": "pie",
        "title": "涨幅贡献占比",
        "data_rows": [
            {
                "label": "198元灵武召唤礼包",
                "value": 160176,
                "metric": "+160,176 · 60.88 %",
            },
        ],
        "x_field": "label",
        "y_field": "value",
    }
    el = chart_spec_to_feishu_element(spec, element_id="gwow0")
    assert el is not None
    body = el["chart_spec"]
    assert body["legends"]["visible"] is False
    assert body["label"]["position"] == "outside"
    assert body["label"]["field"] == "labelText"
    values = body["data"]["values"]
    assert values[0]["labelText"] == "198元灵武召唤礼包\n+160,176 · 60.88 %"
