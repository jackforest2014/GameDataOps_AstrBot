"""Unit tests for KG candidate-selection card (document.kg.candidates)."""

from game_data_ai.kg_candidate_card import build_kg_candidate_card


def _payload() -> dict:
    return {
        "trace_id": "tr_kg",
        "document_id": "docsrc_1",
        "candidates": [
            {
                "entity_id": "ent_a",
                "edge_id": "edge_a",
                "name": "神龙祖直售礼包",
                "kind": "billing_point",
                "aliases": ["神龙祖礼包"],
                "table": "user_infull_detail",
                "column": "prop_name",
                "value": "神龙祖礼包·直购",
            }
        ],
    }


def _buttons(card: dict) -> list[dict]:
    out: list[dict] = []
    for el in card["body"]["elements"]:
        if el.get("tag") == "column_set":
            for col in el["columns"]:
                out.extend(e for e in col["elements"] if e.get("tag") == "button")
    return out


def test_candidate_card_has_approve_reject_buttons_with_ids():
    card = build_kg_candidate_card(_payload())
    assert card["schema"] == "2.0"
    buttons = _buttons(card)
    actions = {b["value"]["action"] for b in buttons}
    assert actions == {"kg_approve", "kg_reject"}
    for b in buttons:
        assert b["value"]["source"] == "game_data_ai"
        assert b["value"]["entity_id"] == "ent_a"
        assert b["value"]["edge_id"] == "edge_a"


def test_candidate_card_renders_mapping_target():
    card = build_kg_candidate_card(_payload())
    body = "\n".join(
        e.get("content", "") for e in card["body"]["elements"] if e.get("tag") == "markdown"
    )
    assert "神龙祖直售礼包" in body
    assert "user_infull_detail.prop_name" in body
    assert "神龙祖礼包·直购" in body
    assert "计费点" in body  # kind label


def test_candidate_card_empty_is_valid():
    card = build_kg_candidate_card({"candidates": []})
    assert card["header"]["title"]["content"] == "知识图谱 · 候选映射待确认"
