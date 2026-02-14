import json
from pathlib import Path

from chat_logging import SessionLogger, serialize_message


class _Dummy:
    def __init__(self) -> None:
        self.a = 1
        self.b = "x"


def test_serialize_message_for_plain_object() -> None:
    data = serialize_message(_Dummy())
    assert data["type"] == "_Dummy"
    assert data["payload"]["a"] == 1


def test_session_logger_writes_jsonl(tmp_path: Path) -> None:
    logger = SessionLogger(log_dir=tmp_path)
    logger.log_event("request", {"prompt": "hello"})
    logger.log_event("message", {"text": "world"})
    logger.log_event("error", {"detail": "boom"})

    content = logger.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == 3

    first = json.loads(content[0])
    assert first["event"] == "request"
    assert first["prompt"] == "hello"

    third = json.loads(content[2])
    assert third["event"] == "error"
    assert third["detail"] == "boom"


def test_serialize_message_is_json_safe() -> None:
    class _HasModelDump:
        def model_dump(self):  # type: ignore[no-untyped-def]
            return {"x": object()}

    data = serialize_message(_HasModelDump())
    dumped = json.dumps(data, ensure_ascii=False)
    assert "x" in dumped
