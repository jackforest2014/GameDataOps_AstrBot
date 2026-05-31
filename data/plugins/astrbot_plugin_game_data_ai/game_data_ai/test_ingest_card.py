"""Unit tests for the document ingest confirmation card."""

from game_data_ai.ingest_card import build_ingest_confirm_card


def _card() -> dict:
    return build_ingest_confirm_card(
        document_id="docsrc_1", title="仙魔业务文档", trace_id="tr_x"
    )


def test_ingest_card_drops_premature_analysis_text():
    md = _card()["body"]["elements"][0]["content"]
    # 入库卡在分析卡之上，不应声称"上方已返回分析"（#5）。
    assert "上方已根据文档内容返回本次分析" not in md
    assert "仙魔业务文档" in md
    assert "入库" in md


def test_ingest_card_buttons_intact():
    card = _card()
    cols = card["body"]["elements"][1]["columns"]
    actions = [c["elements"][0]["value"]["action"] for c in cols]
    assert actions == ["ingest_approve", "ingest_reject"]
