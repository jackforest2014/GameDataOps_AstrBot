from game_data_ai.overseas_scope_card import build_overseas_scope_clarify_card


def test_overseas_scope_card_has_buttons():
    card = build_overseas_scope_clarify_card(
        {
            "trace_id": "tr_1",
            "session_id": "sess_oc_1",
            "clarification": {
                "kind": "overseas_scope",
                "prompt": "请选择",
                "options": [
                    {"id": "overseas_scope_project", "label": "仙魔 · 仅海外端"},
                    {"id": "overseas_scope_company", "label": "全公司 · 所有海外项目"},
                ],
            },
        }
    )
    body = card.get("body") or {}
    elements = body.get("elements") or []
    assert any(el.get("tag") == "column_set" for el in elements)


def test_overseas_scope_card_disabled_project_no_button():
    card = build_overseas_scope_clarify_card(
        {
            "trace_id": "tr_1",
            "clarification": {
                "prompt": "请选择",
                "options": [
                    {"id": "overseas_scope_project", "label": "仙魔 · 无海外端（不可选）", "disabled": True},
                    {"id": "overseas_scope_company", "label": "全公司 · 所有海外项目"},
                ],
            },
        }
    )
    body = card.get("body") or {}
    elements = body.get("elements") or []
    markdown = " ".join(
        el.get("content", "") for el in elements if el.get("tag") == "markdown"
    )
    assert "不可选" in markdown
    column_sets = [el for el in elements if el.get("tag") == "column_set"]
    assert len(column_sets) == 1
    buttons = column_sets[0].get("columns") or []
    assert len(buttons) == 1
