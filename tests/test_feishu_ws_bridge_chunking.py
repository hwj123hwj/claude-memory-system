import feishu_ws_bridge as bridge_mod


def test_normalize_outgoing_text() -> None:
    raw = "a\r\nb\x00c\r\n"
    got = bridge_mod._normalize_outgoing_text(raw)
    assert got == "a\nbc\n"


def test_parse_text_content_sanitizes_controls() -> None:
    raw = "{\"text\":\"你\\u0000好\\r\\n\"}"
    got = bridge_mod._parse_text_content(raw)
    assert got == "你好"


def test_split_text_for_feishu_respects_max_chars() -> None:
    text = "12345\n67890\nabcde"
    parts = bridge_mod._split_text_for_feishu(text, max_chars=6)
    assert parts == ["12345", "67890", "abcde"]


def test_split_text_prefers_paragraph_boundary() -> None:
    text = "Para1 sentence1. Para1 sentence2.\n\nPara2 sentence1. Para2 sentence2."
    parts = bridge_mod._split_text_for_feishu(text, max_chars=35)
    assert parts == ["Para1 sentence1. Para1 sentence2.", "Para2 sentence1. Para2 sentence2."]


def test_split_text_prefers_sentence_boundary() -> None:
    text = "这是第一句。这是第二句。这是第三句。"
    parts = bridge_mod._split_text_for_feishu(text, max_chars=7)
    assert parts == ["这是第一句。", "这是第二句。", "这是第三句。"]


def test_send_text_sends_multiple_chunks(monkeypatch) -> None:
    bridge = bridge_mod.FeishuWSBridge(app_id="x", app_secret="y", max_reply_chars=5)
    sent: list[str] = []
    monkeypatch.setattr(bridge, "_send_text_once", lambda chat_id, text: sent.append(text))
    bridge._send_text("oc_chat", "1234567890")
    assert sent == ["12345", "67890"]
