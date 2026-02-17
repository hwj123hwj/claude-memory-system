from __future__ import annotations

MEMORY_HINT_KEYWORDS = ("记忆", "memory", "个人记忆", "记忆系统")

# Only explicit persistence/editing intents should unlock write tools.
WRITE_INTENT_KEYWORDS = (
    "保存",
    "写入",
    "落盘",
    "记录到",
    "创建文件",
    "新建文件",
    "生成文件",
    "写到",
    "归档",
    "更新这个文件",
    "修改这个文件",
    "覆盖文件",
)
WRITE_INTENT_TARGET_HINTS = (
    "memory",
    "inbox",
    "文件",
    "md",
    ".md",
    "yaml",
    ".yaml",
    ".yml",
)
NEW_FILE_INTENT_KEYWORDS = (
    "新建文件",
    "创建新文件",
    "另存为",
    "单独建一个文件",
    "拆成单独文件",
)


def has_explicit_write_intent(user_prompt: str) -> bool:
    text = user_prompt.strip()
    if not text:
        return False

    lower = text.lower()
    has_action = any(k in text for k in WRITE_INTENT_KEYWORDS)
    has_target = any(k in text for k in WRITE_INTENT_TARGET_HINTS) or any(
        k in lower for k in WRITE_INTENT_TARGET_HINTS
    )
    return has_action and has_target


def has_explicit_new_file_intent(user_prompt: str) -> bool:
    text = user_prompt.strip()
    if not text:
        return False
    return any(k in text for k in NEW_FILE_INTENT_KEYWORDS)


def build_effective_prompt(user_prompt: str) -> str:
    text = user_prompt.strip()
    lower = text.lower()
    if any(k in text for k in MEMORY_HINT_KEYWORDS) or any(k in lower for k in MEMORY_HINT_KEYWORDS):
        return (
            f"{text}\n\n"
            "执行要求：将“记忆系统”解释为工作区目录 `memory`。"
            "必须先用文件工具检查该目录及其子目录中的 md/yaml 内容，再给出总结。"
            "不要回答“无法访问记忆系统”，除非目录确实不存在并给出你检查过的路径。"
            "如果用户要求新增一条记忆，先检查是否已有相似内容（通过标题/标签/关键词搜索），"
            "如有重复则询问是更新现有记忆还是创建新记忆。"
            "新记忆先写入 memory/00_Inbox，organize 后必须删除 Inbox 中的原文件。"
            "涉及计划类内容时，优先使用 `_templates` 模板并优先更新已有文件，不要默认新建文件。"
            "若在 `memory/10_Growth` 新建详细计划文件，文件内必须包含"
            "`memory/10_Growth/roadmap_2026.md` 的关联回指。"
        )
    return text
