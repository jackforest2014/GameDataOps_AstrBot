"""Regression tests: cancel-schedule card must use buttons, never `checkboxes`.

飞书 schema 2.0 rejects `tag: checkboxes` with 10002 "not support tag: checkboxes",
so the selectable cancel card is built from one button per task + 取消全部.
"""

import json

from game_data_ai.schedule_cancel_card import build_cancel_preview_card


def _tags(card: dict) -> list[str]:
    return [el.get("tag") for el in card["body"]["elements"]]


def _assert_no_checkboxes(card: dict) -> None:
    blob = json.dumps(card, ensure_ascii=False)
    assert "checkboxes" not in blob, "card must not contain a checkboxes tag"


def test_cancel_card_uses_buttons_not_checkboxes():
    preview = {
        "action_token": "tok_1",
        "items": [
            {"schedule_id": "s1", "label": "大盘数据", "subtitle": "每天 11:00 [active]"},
            {"schedule_id": "s2", "label": "昨天大盘数据", "subtitle": "每天 11:30 [active]"},
        ],
    }
    card = build_cancel_preview_card(preview)
    _assert_no_checkboxes(card)
    tags = _tags(card)
    assert "button" in tags, "expected per-task / 取消全部 buttons"

    # Each task contributes a 取消此项 button carrying its schedule_id; plus a
    # 取消全部 button carrying all ids, plus a 放弃 button.
    buttons = [el for el in card["body"]["elements"] if el.get("tag") == "button"]
    confirm = [
        b for b in buttons
        if b["value"].get("action") == "schedule_cancel_confirm" and b["value"].get("schedule_id")
    ]
    assert len(confirm) == 2, f"want one cancel button per task, got {len(confirm)}"
    cancel_all = [b for b in buttons if b["value"].get("schedule_ids") == ["s1", "s2"]]
    assert len(cancel_all) == 1, "want a 取消全部 button carrying all ids"


def test_cancel_card_no_match_shows_view_all_button():
    card = build_cancel_preview_card(
        {"action_token": "tok_2", "items": [], "empty_reason": "no_match", "match_phrase": "大盘"}
    )
    _assert_no_checkboxes(card)
    buttons = [el for el in card["body"]["elements"] if el.get("tag") == "button"]
    assert any(b["value"].get("action") == "schedule_cancel_show_all" for b in buttons)


def test_cancel_card_single_task_has_no_cancel_all():
    card = build_cancel_preview_card(
        {"action_token": "tok_3", "items": [{"schedule_id": "s1", "label": "大盘数据"}]}
    )
    _assert_no_checkboxes(card)
    buttons = [el for el in card["body"]["elements"] if el.get("tag") == "button"]
    assert not any(b["value"].get("schedule_ids") for b in buttons), "single task needs no 取消全部"
