from __future__ import annotations

from uuid import uuid4


def resolve_session_id(
    conversation_id: str | None,
    new_conversation: bool,
) -> tuple[str, bool]:
    if not new_conversation and conversation_id:
        return conversation_id, False
    return uuid4().hex, True

