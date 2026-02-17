from prompt_builder import (
    build_effective_prompt,
    has_explicit_new_file_intent,
    has_explicit_write_intent,
)


def test_add_memory_directory_instruction_when_memory_prompt() -> None:
    out = build_effective_prompt("你可以看看我的记忆系统里面有什么吗")
    assert "`memory`" in out
    assert "必须先用文件工具检查" in out
    assert "_templates" in out
    assert "优先更新已有文件" in out
    assert "roadmap_2026.md" in out


def test_keep_non_memory_prompt_as_is() -> None:
    raw = "列出当前目录"
    out = build_effective_prompt(raw)
    assert out == raw


def test_detect_explicit_write_intent_for_save_request() -> None:
    assert has_explicit_write_intent("请把这次旅游计划保存到memory里") is True


def test_detect_no_write_intent_for_just_generating_plan() -> None:
    assert has_explicit_write_intent("帮我生成一个三天的旅游计划") is False


def test_detect_explicit_new_file_intent() -> None:
    assert has_explicit_new_file_intent("请单独新建文件保存这份计划") is True


def test_detect_no_new_file_intent_when_only_saving() -> None:
    assert has_explicit_new_file_intent("请保存到原来的文件里") is False
