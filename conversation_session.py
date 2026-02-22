from __future__ import annotations

from uuid import uuid4


DEFAULT_SESSION_ID = "main"


def resolve_session_id(
    conversation_id: str | None,
    new_conversation: bool,
) -> tuple[str, bool]:
    if not new_conversation and conversation_id:
        return conversation_id, False
    if not new_conversation:
        return DEFAULT_SESSION_ID, False
    return uuid4().hex, True
