from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return _json_safe(value.model_dump())  # type: ignore[call-arg]
        except Exception:
            return str(value)
    if hasattr(value, "__dict__"):
        return _json_safe(dict(vars(value)))
    return str(value)


def serialize_message(message: Any) -> dict[str, Any]:
    payload: Any
    if hasattr(message, "model_dump"):
        try:
            payload = message.model_dump()  # type: ignore[call-arg]
        except Exception:
            payload = str(message)
    elif hasattr(message, "__dict__"):
        payload = dict(vars(message))
    else:
        payload = str(message)

    return {
        "type": type(message).__name__,
        "payload": _json_safe(payload),
    }


class SessionLogger:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = self.log_dir / f"chat-{stamp}-{uuid4().hex[:8]}.jsonl"

    def log_event(self, event: str, data: dict[str, Any]) -> None:
        record = {"ts": _utc_now(), "event": event, **_json_safe(data)}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
