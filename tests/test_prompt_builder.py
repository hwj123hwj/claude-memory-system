from prompt_builder import build_effective_prompt


def test_add_memory_directory_instruction_when_memory_prompt() -> None:
    out = build_effective_prompt("你可以看看我的记忆系统里面有什么吗")
    assert "`memory`" in out
    assert "必须先用文件工具检查" in out


def test_keep_non_memory_prompt_as_is() -> None:
    raw = "列出当前目录"
    out = build_effective_prompt(raw)
    assert out == raw
