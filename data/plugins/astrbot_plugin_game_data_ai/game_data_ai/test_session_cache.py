from game_data_ai.session_cache import ChatSessionStore, default_session_id


def test_default_session_id_legacy():
    assert default_session_id("oc_abc") == "sess_oc_abc"


def test_chat_session_store_update_from_response():
    store = ChatSessionStore()
    assert store.get("oc_1") == "sess_oc_1"
    assert store.update("oc_1", "sess_oc_1_2") == "sess_oc_1_2"
    assert store.get("oc_1") == "sess_oc_1_2"
