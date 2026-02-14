from __future__ import annotations

MEMORY_HINT_KEYWORDS = ("记忆", "memory", "个人记忆", "记忆系统")


def build_effective_prompt(user_prompt: str) -> str:
    text = user_prompt.strip()
    lower = text.lower()
    if any(k in text for k in MEMORY_HINT_KEYWORDS) or any(k in lower for k in MEMORY_HINT_KEYWORDS):
        return (
            f"{text}\n\n"
            "执行要求：将“记忆系统”解释为工作区目录 `memory`。"
            "必须先用文件工具检查该目录及其子目录中的 md/yaml 内容，再给出总结。"
            "不要回答“无法访问记忆系统”，除非目录确实不存在并给出你检查过的路径。"
            "如果用户要求新增一条记忆，先写入 memory/00_Inbox，再由用户确认是否归档。"
        )
    return text
