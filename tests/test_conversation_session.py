from conversation_session import resolve_session_id


def test_reuse_existing_session_id_by_default() -> None:
    session_id, is_new = resolve_session_id("abc-123", new_conversation=False)
    assert session_id == "abc-123"
    assert is_new is False


def test_create_new_session_when_requested() -> None:
    session_id, is_new = resolve_session_id("abc-123", new_conversation=True)
    assert session_id != "abc-123"
    assert is_new is True
    assert len(session_id) > 8


def test_create_new_session_when_missing() -> None:
    session_id, is_new = resolve_session_id(None, new_conversation=False)
    assert session_id
    assert is_new is True

