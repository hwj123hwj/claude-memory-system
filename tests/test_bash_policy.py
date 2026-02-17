from pathlib import Path

from app import validate_bash_command


def test_allow_workspace_move_command() -> None:
    root = Path("/workspace/test").resolve()
    ok, reason = validate_bash_command(
        'mv "memory/00_Inbox/a.md" "memory/10_Growth/a.md"',
        root,
    )
    assert ok is True
    assert reason == "ok"


def test_deny_command_with_outside_path() -> None:
    root = Path("/workspace/test").resolve()
    ok, reason = validate_bash_command(
        'rm "/etc/hosts"',
        root,
    )
    assert ok is False
    assert "Path denied" in reason


def test_deny_unsafe_shell_syntax() -> None:
    root = Path("/workspace/test").resolve()
    ok, reason = validate_bash_command(
        'rm "memory/00_Inbox/a.md" && echo done',
        root,
    )
    assert ok is False
    assert "Unsafe Bash syntax" in reason
