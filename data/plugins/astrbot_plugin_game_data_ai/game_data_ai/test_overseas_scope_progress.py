import asyncio

from game_data_ai import card_action, cards


def test_build_progress_card_shape():
    card = cards.build_progress_card("正在汇总海外大盘数据，请稍候…")
    assert card["header"]["title"]["content"] == "正在分析"
    elements = card["body"]["elements"]
    assert any("正在汇总海外大盘数据" in el.get("content", "") for el in elements)


class _FakeOperator:
    open_id = "ou_user"


class _FakeCtx:
    open_chat_id = "oc_chat"
    open_message_id = "om_1"


class _FakeInner:
    operator = _FakeOperator()
    context = _FakeCtx()


class _FakeEvent:
    def __init__(self):
        self.event = _FakeInner()


class _FakeClient:
    def __init__(self):
        self.calls = []

    async def chat_messages(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "answered", "answer": {"summary": "ok"}}


def test_overseas_scope_confirm_sends_progress_card_before_result(monkeypatch):
    # 用户反馈：点击「全公司·所有海外项目」后长时间无反馈，疑似挂掉。修复后必须在等待
    # 后端聚合前先回一张「正在分析」进度卡，再回结果卡。
    sent = []

    async def fake_send(event, card, chat_id):
        sent.append(card)

    monkeypatch.setattr(cards, "build_result_cards_json", lambda payload: [{"tag": "result"}])

    client = _FakeClient()
    value = {"option_id": "overseas_scope_company", "session_id": "sess_oc_1"}
    asyncio.run(
        card_action._handle_overseas_scope_confirm(
            client, fake_send, _FakeEvent(), value, "ou_user", "oc_chat"
        )
    )

    assert len(sent) >= 2, "expected progress card + result card"
    assert sent[0]["header"]["title"]["content"] == "正在分析", "first card must be the progress card"
    assert client.calls, "backend chat_messages must still be invoked after the progress card"
