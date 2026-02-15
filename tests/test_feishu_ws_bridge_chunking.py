import feishu_ws_bridge as bridge_mod


def test_normalize_outgoing_text() -> None:
    raw = "a\r\nb\x00c\r\n"
    got = bridge_mod._normalize_outgoing_text(raw)
    assert got == "a\nbc\n"


def test_split_text_for_feishu_respects_max_chars() -> None:
    text = "12345\n67890\nabcde"
    parts = bridge_mod._split_text_for_feishu(text, max_chars=6)
    assert parts == ["12345", "67890", "abcde"]


def test_send_text_sends_multiple_chunks(monkeypatch) -> None:
    bridge = bridge_mod.FeishuWSBridge(app_id="x", app_secret="y", max_reply_chars=5)
    sent: list[str] = []
    monkeypatch.setattr(bridge, "_send_text_once", lambda chat_id, text: sent.append(text))
    bridge._send_text("oc_chat", "1234567890")
    assert sent == ["12345", "67890"]
