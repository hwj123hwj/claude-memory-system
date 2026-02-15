# Claude Code 受限智能体开发提示词（可直接给其他 Agent）

你是资深后端工程师。请从零实现一个“网页对话 + Claude Code SDK”的受限智能体系统。前端不是重点，只要可用。

## 目标

构建一个本地 Web 服务，用户在网页输入问题，后端调用 Claude Code SDK 与模型交互，并允许模型在**当前工作目录内**进行文件相关操作（读取/编辑/搜索）。  
系统必须支持多轮会话记忆、可控新会话重置、完整日志落盘。

## 强约束（必须满足）

1. 仅允许访问当前项目目录（workspace root），禁止越界路径。
2. 默认复用会话上下文；只有用户明确“新对话”才创建新 session。
3. 每次请求都写独立日志文件（jsonl），记录请求、消息流、权限决策、错误、最终回复。
4. 如果模型请求越权路径，必须拒绝并给出可追踪日志。
5. 当用户提到“记忆系统/个人记忆/memory”时，优先基于 `store_test/memory` 内容总结，而不是泛化回复“无法访问记忆”。

## 技术要求

1. 后端：Python + FastAPI
2. SDK：`claude-agent-sdk`
3. 关键模式：使用 `ClaudeSDKClient`（而不是每次 `query()` 新会话）
4. 权限控制：`can_use_tool` 回调 + 路径递归校验
5. 工具白名单建议：`Read, Write, Edit, MultiEdit, Glob, Grep, LS`
6. `max_turns` 设置为 `30`

## 核心实现点

### 1) 会话管理

1. API 请求体包含：
   - `message: str`
   - `conversation_id: str | null`
   - `new_conversation: bool`
2. 逻辑：
   - `new_conversation=false` 且有 `conversation_id` -> 复用原会话
   - 否则生成新 `conversation_id`
3. API 响应返回：
   - `reply`
   - `conversation_id`
   - `is_new_session`
   - `log_file`
   - `workspace`

### 2) 安全边界

1. 固定 `cwd=workspace_root`
2. 对工具输入递归抽取路径字段（如 `path/file_path/target_file/new_file_path/cwd/directory`）
3. 每个路径 `resolve` 后必须在 `workspace_root` 内，否则拒绝
4. 禁止 `Bash`（或明确说明为什么启用）

### 3) 日志体系

每次请求创建：`logs/chat-<timestamp>-<id>.jsonl`  
日志事件至少包含：

1. `request`（原始 prompt、effective_prompt、session_id、cwd、allowed_tools）
2. `permission_check / permission_allow / permission_deny`
3. `message`（SDK 每条消息）
4. `error`
5. `response`

要求日志序列化对复杂对象安全（不可 JSON 化对象需转换为字符串或 dict）。

### 4) 记忆场景增强

当用户问题包含“记忆/memory”等关键词时：

1. 自动读取 `store_test/memory` 下 `md/yaml/yml` 文件
2. 构建受长度控制的上下文（文件列表 + 内容片段）
3. 将上下文拼入有效 prompt，再交给 Claude 总结
4. 若目录不存在，明确报告检查路径

### 5) 前端（最小可用）

只需要：

1. 一个输入框和发送按钮
2. 一个“新对话”按钮
3. 展示回复文本、当前 `conversation_id`、本轮 `log_file`

## 验收标准

1. 用户连续两次提问（不点新对话），第二次能利用第一次上下文。
2. 点击“新对话”后，`conversation_id` 变化。
3. 请求“总结记忆系统”时，能输出基于 `store_test/memory` 的内容概要。
4. 越界路径请求被拒绝并记录日志。
5. `pytest` 全绿，至少覆盖：
   - 路径越界校验
   - 会话 ID 复用/重建
   - 日志写入与 JSON 安全
   - memory 关键词处理

## 输出要求

请输出：

1. 完整项目文件结构
2. 可运行代码
3. 启动命令与验证步骤
4. 关键安全设计说明

