"""Unit tests for adhoc_table Feishu card rendering."""

from game_data_ai.cards import (
    _adhoc_table_element,
    _adhoc_table_markdown,
    _section_header_element,
    _wow_week_compare_table_element,
    build_adhoc_result_card_json,
    build_result_cards_json,
)


def test_adhoc_table_markdown_renders_columns_and_rows():
    md = _adhoc_table_markdown(
        {
            "columns": [
                {"key": "channel", "label": "渠道", "type": "string"},
                {"key": "cnt", "label": "人数", "type": "number"},
            ],
            "rows": [
                {"channel": "ios", "cnt": 120},
                {"channel": "android", "cnt": 340},
            ],
            "row_count": 2,
        }
    )
    assert "渠道" in md and "ios" in md and "340" in md


def test_adhoc_table_element_native_text_and_freeze():
    el = _adhoc_table_element(
        {
            "columns": [
                {"key": "prop_name", "label": "计费点", "type": "string"},
                {"key": "change_amount", "label": "变化金额(元)", "type": "string"},
            ],
            "rows": [
                {
                    "prop_name": "198元灵武召唤礼包",
                    "change_amount": "+160,176",
                },
            ],
            "row_count": 1,
        },
        element_id="gdTbl0",
    )
    assert el is not None
    assert el["tag"] == "table"
    assert el["freeze_first_column"] is True
    assert el["columns"][0]["data_type"] == "text"
    assert el["rows"][0]["prop_name"] == "198元灵武召唤礼包"


def test_build_adhoc_result_card_json_uses_native_table():
    card = build_adhoc_result_card_json(
        {
            "trace_id": "tr_adhoc",
            "session_id": "sess_1",
            "answer": {
                "title": "仙魔 · 按需查询",
                "summary": "返回 2 行。",
                "query_mode": "adhoc",
                "template_id": "catalog.adhoc",
                "adhoc_table": {
                    "columns": [{"key": "n", "label": "N", "type": "number"}],
                    "rows": [{"n": 1}],
                    "row_count": 1,
                },
                "methodology": "catalog.adhoc",
                "sql_digest": "abc123",
            },
        }
    )
    body = card["body"]["elements"]
    tables = [el for el in body if el.get("tag") == "table"]
    assert len(tables) == 1
    assert tables[0]["columns"][0]["data_type"] == "number"


def test_section_header_gain_loss_use_white_text_on_tint():
    gain = _section_header_element(
        {
            "stage_label": "二",
            "title": "涨幅贡献 Top（按变化金额）",
            "summary": "流水增加的计费点 Top 10。",
        }
    )
    loss = _section_header_element(
        {
            "stage_label": "三",
            "title": "跌幅贡献 Top（按变化金额）",
            "summary": "流水减少的计费点 Top 10。",
        }
    )
    for el, bg in ((gain, "green"), (loss, "red")):
        assert el["background_style"] == bg
        md = el["columns"][0]["elements"][0]["content"]
        assert "<font color='white'>" in md
        assert "Top" in md


def test_build_adhoc_sections_use_native_tables():
    card = build_adhoc_result_card_json(
        {
            "trace_id": "tr_wow",
            "session_id": "sess_1",
            "answer": {
                "summary": "双周分析",
                "query_mode": "adhoc",
                "sections": [
                    {
                        "stage_label": "步骤 1",
                        "title": "概况",
                        "adhoc_table": {
                            "columns": [{"key": "a", "label": "A", "type": "string"}],
                            "rows": [{"a": "1"}],
                            "row_count": 1,
                        },
                    },
                    {
                        "stage_label": "步骤 3",
                        "title": "对比",
                        "compare_rows": [
                            {"metric": "流水", "p1": "1", "p2": "2", "delta": "+1"},
                        ],
                    },
                ],
            },
        }
    )
    tables = [el for el in card["body"]["elements"] if el.get("tag") == "table"]
    assert len(tables) == 2
    assert _wow_week_compare_table_element(
        [{"metric": "m", "p1": "1", "p2": "2", "delta": "0"}],
        element_id="t0",
    )["freeze_first_column"]


def test_build_adhoc_result_card_json_uses_wathet_header():
    card = build_adhoc_result_card_json(
        {
            "trace_id": "tr_adhoc",
            "session_id": "sess_1",
            "answer": {
                "title": "仙魔 · 按需查询",
                "summary": "返回 2 行。",
                "query_mode": "adhoc",
                "template_id": "catalog.adhoc",
                "adhoc_table": {
                    "columns": [{"key": "n", "label": "N", "type": "number"}],
                    "rows": [{"n": 1}],
                    "row_count": 1,
                },
                "methodology": "catalog.adhoc",
                "sql_digest": "abc123",
            },
        }
    )
    assert card["header"]["template"] == "wathet"
    body = card["body"]["elements"]
    assert any(el.get("tag") == "table" for el in body)
    assert any(
        el.get("tag") == "markdown" and "查询结果" in el.get("content", "")
        for el in body
    )


def test_week_compare_change_chart_renders_chart_element():
    card = build_adhoc_result_card_json(
        {
            "trace_id": "tr_wc",
            "session_id": "sess_1",
            "answer": {
                "title": "仙魔 · 近一周付费对比",
                "summary": "本期 vs 上期，金额变化 -5.0%。",
                "query_mode": "adhoc",
                "template_id": "catalog.adhoc",
                "charts": [
                    {
                        "chart_id": "week_compare_delta",
                        "type": "bar",
                        "title": "两期核心指标环比变化（%）",
                        "labels": ["付费金额", "付费人数", "ARPPU"],
                        "datasets": [{"name": "环比%", "values": [-5.0, -2.9, -2.2]}],
                    }
                ],
                "sections": [
                    {
                        "stage_label": "一",
                        "title": "两期汇总对比",
                        "adhoc_table": {
                            "columns": [{"key": "metric", "label": "指标", "type": "string"}],
                            "rows": [{"metric": "付费金额"}],
                            "row_count": 1,
                        },
                    }
                ],
                "facts": ["上期付费金额 14,492,784，本期 13,765,204，变化 -5.0%。"],
                "methodology": "catalog.adhoc",
                "sql_digest": "abc",
            },
        }
    )
    body = card["body"]["elements"]
    # 图表先于"要点"文字出现，实现图文结合（#1）。
    assert any(el.get("tag") == "chart" for el in body)
    assert any(
        el.get("tag") == "markdown" and "要点" in el.get("content", "") for el in body
    )


def test_build_result_cards_json_routes_adhoc():
    cards = build_result_cards_json(
        {
            "trace_id": "tr_x",
            "session_id": "sess_x",
            "answer": {
                "query_mode": "adhoc",
                "summary": "未能完成。",
                "template_id": "catalog.adhoc",
                "notices": [
                    {
                        "level": "warning",
                        "code": "llm_unavailable",
                        "title": "无法生成",
                        "body": "stub",
                    }
                ],
            },
        }
    )
    assert len(cards) == 1
    assert cards[0]["header"]["template"] == "wathet"
