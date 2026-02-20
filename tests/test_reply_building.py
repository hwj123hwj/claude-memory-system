from pathlib import Path

from app import build_reply_text


def test_build_reply_prefers_tool_error_over_empty_success() -> None:
    reply = build_reply_text(
        chunks=[],
        tool_errors=["Bash is disabled for this web agent."],
        interrupted=True,
        result_is_error=False,
        result_subtype="error_during_execution",
        compact_applied=False,
        log_path=Path("logs/test.jsonl"),
    )
    assert "执行失败" in reply
    assert "Bash is disabled for this web agent." in reply


def test_build_reply_reports_interrupted_when_no_text_or_tool_error() -> None:
    reply = build_reply_text(
        chunks=[],
        tool_errors=[],
        interrupted=True,
        result_is_error=False,
        result_subtype="error_during_execution",
        compact_applied=False,
        log_path=Path("logs/test.jsonl"),
    )
    assert "执行中断" in reply
    assert "test.jsonl" in reply


def test_build_reply_reports_compact_applied_when_no_text() -> None:
    reply = build_reply_text(
        chunks=[],
        tool_errors=[],
        interrupted=False,
        result_is_error=False,
        result_subtype="success",
        compact_applied=True,
        log_path=Path("logs/test.jsonl"),
    )
    assert "压缩完成" in reply
