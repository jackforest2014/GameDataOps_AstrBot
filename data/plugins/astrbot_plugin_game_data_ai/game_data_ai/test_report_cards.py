"""Unit tests for structured report (answer.report) Feishu card rendering."""

from game_data_ai.cards import (
    _report_bullet_line,
    _report_elements,
    _report_header_element,
    _report_paragraph_md,
    build_report_card_json,
    build_result_cards_json,
)


def _sample_payload() -> dict:
    return {
        "trace_id": "tr_x",
        "session_id": "s1",
        "answer": {
            "title": "文档问答",
            "summary": "概述句。",
            "facts": ["发现：版本空窗期"],
            "report": {
                "sections": [
                    {
                        "level": 1,
                        "title": "结论概述",
                        "paragraphs": ["数据下滑由**版本空窗**导致。"],
                    },
                    {
                        "level": 1,
                        "title": "关键发现与假设检验",
                        "bullets": [
                            {"kind": "finding", "text": "发现：版本空窗期"},
                            {"kind": "forecast", "text": "预判：v3950 减缓下滑"},
                        ],
                    },
                ]
            },
        },
        "rendering": {"preferred": "table"},
    }


def test_header_element_is_full_width_colored_bar():
    el = _report_header_element("结论概述", 1)
    assert el["tag"] == "column_set"
    assert el["background_style"] == "blue"
    md = el["columns"][0]["elements"][0]["content"]
    assert "**结论概述**" in md and "white" in md


def test_paragraph_indents_and_strips_heading():
    out = _report_paragraph_md("### 结论概述 正文")
    assert out.startswith("\u3000\u3000")
    assert "#" not in out  # markdown heading must not survive (avoids big font)


def test_bullet_kind_colors():
    assert "blue" in _report_bullet_line({"kind": "finding", "text": "发现：x"})
    assert "purple" in _report_bullet_line({"kind": "forecast", "text": "预判：y"})
    assert _report_bullet_line({"kind": "plain", "text": "z"}) == "• z"


def test_report_elements_preserve_section_order_and_bold():
    els = _report_elements(_sample_payload()["answer"]["report"])
    # header, paragraph, header, bullets
    assert els[0]["tag"] == "column_set"
    assert "**版本空窗**" in els[1]["content"]
    assert els[2]["tag"] == "column_set"


def test_build_report_card_routes_and_has_no_giant_heading():
    payload = _sample_payload()
    cards = build_result_cards_json(payload)
    assert len(cards) == 1
    card = cards[0]
    assert card["header"]["title"]["content"] == "文档问答"
    # No markdown element should carry a heading prefix that enlarges the font.
    for el in card["body"]["elements"]:
        if el.get("tag") == "markdown":
            assert not el["content"].lstrip().startswith("#")


def test_build_report_card_direct_entry():
    card = build_report_card_json(_sample_payload())
    assert card["schema"] == "2.0"
    assert any(e["tag"] == "column_set" for e in card["body"]["elements"])
