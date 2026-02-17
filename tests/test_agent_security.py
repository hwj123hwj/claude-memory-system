from pathlib import Path

from agent_security import is_tool_input_within_root, resolve_candidate_path


def test_resolve_relative_path_inside_root() -> None:
    root = Path("/workspace/test")
    resolved = resolve_candidate_path("store_test/readme.md", root)
    assert resolved == (root / "store_test" / "readme.md").resolve()


def test_resolve_parent_path_outside_root() -> None:
    root = Path("/workspace/test")
    resolved = resolve_candidate_path("../outside.txt", root)
    assert resolved == (root.parent / "outside.txt").resolve()


def test_tool_input_with_single_inside_path() -> None:
    root = Path("/workspace/test")
    ok = is_tool_input_within_root({"file_path": "store_test/demo.md"}, root)
    assert ok is True


def test_tool_input_with_single_outside_path() -> None:
    root = Path("/workspace/test")
    ok = is_tool_input_within_root({"file_path": "../secret.txt"}, root)
    assert ok is False


def test_tool_input_with_nested_path_list() -> None:
    root = Path("/workspace/test")
    ok = is_tool_input_within_root(
        {
            "edits": [
                {"file_path": "store_test/demo.md"},
                {"file_path": "../secret.txt"},
            ]
        },
        root,
    )
    assert ok is False
