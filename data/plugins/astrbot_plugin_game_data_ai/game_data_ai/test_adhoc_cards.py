"""Unit tests for adhoc_table Feishu card rendering."""

from game_data_ai.cards import (
    _adhoc_table_markdown,
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
    assert any(el.get("tag") == "markdown" and "查询结果" in el.get("content", "") for el in body)


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
