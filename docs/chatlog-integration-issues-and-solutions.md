# Chatlog 对接开发问题与解决方案记录

## 文档目的

本文件用于记录 `claude-memory-system` 对接 `chatlog` 过程中的关键问题、根因与解决方案。  
每条记录都明确关联“当时要实现的需求/功能”，便于后续迭代快速回溯。

---

## 1. 需求：让 CI 稳定通过（安全路径相关测试）

### 问题现象
- GitHub Actions 中 `test_agent_security`、`test_bash_policy` 失败。
- 本地可过，CI（Linux）失败。

### 根因
- 测试里使用 Windows 风格路径（如 `D:\...`、`..\...`、`C:/...`）。
- Linux 下 `pathlib` 语义不同，导致路径判断与预期不一致。

### 解决方案
- 将测试改为平台无关路径和断言方式。
- 避免直接依赖 Windows 路径字面量。

### 验证
- 全量测试恢复通过。

---

## 2. 需求：支持 `/memory group list` 命令管理 chatlog 对接对象

### 问题现象
- 在飞书输入 `/memory group list`，返回 `Unknown skill: memory`。

### 根因
- 命令没有在桥接层拦截，直接进入 `run_agent`，被当作通用技能命令解析。

### 解决方案
- 在 `feishu_ws_bridge.py` 增加命令前置拦截：
  - `handle_memory_group_command(...)`
  - 命中 `/memory group ...` 时直接返回结果，不再进入 LLM 对话流。

### 验证
- 飞书可正确返回目标列表。

---

## 3. 需求：启用 webhook/backfill 实际接入能力

### 问题现象
- `/healthz` 中 `chatlog.enabled=false`。
- chatlog 同步逻辑看起来没有运行。

### 根因
- `.env` 未配置 chatlog 相关参数（或服务启动时未加载到）。

### 解决方案
- 补齐 `.env`：
  - `CHATLOG_ENABLED=true`
  - `CHATLOG_BASE_URL=http://127.0.0.1:5030`
  - `CHATLOG_WEBHOOK_TOKEN=...`
  - `CHATLOG_BACKFILL_INTERVAL_SECONDS=...`
  - `CHATLOG_MONITORED_TALKERS=...`
  - `CHATLOG_BACKFILL_BOOTSTRAP_DAYS=...`
- 重启本地 `uvicorn` 与 `feishu_ws_bridge`。

### 验证
- `/healthz` 显示 `chatlog.enabled=true`，并出现 backfill 运行状态字段。

---

## 4. 需求：本地联调服务稳定运行

### 问题现象
- 本地出现多个 Python 进程，行为混乱。
- 同类服务重复启动（多个 uvicorn / 多个 bridge）。

### 根因
- 多次手动启动，未先清理旧进程。

### 解决方案
- 先按命令行特征清理旧进程（`uvicorn app:app`、`feishu_ws_bridge.py`）。
- 再单次启动各 1 个服务。
- 通过端口级核对确认：
  - `8000 -> uvicorn`
  - `5030 -> chatlog.exe`

### 验证
- 健康检查稳定，命令行为一致。

---

## 5. 需求：将群聊配置中的中文字段正确展示（topics/people）

### 问题现象
- `show` 输出里出现 `??` 或乱码。

### 根因
- 部分中文数据在 Windows PowerShell 链路中发生编码损伤后写入配置文件。

### 解决方案
- 优先通过飞书命令更新中文字段，避免终端编码污染。
- 文档中明确：配置更新尽量走机器人命令，不走本地终端拼接中文参数。

### 验证
- 重新更新后显示恢复正常。

---

## 6. 需求：实现 webhook 幂等去重（防重复污染）

### 问题现象
- 重放同一条 webhook 时，存在重复处理风险。

### 根因
- 缺少持久化去重状态。

### 解决方案
- 新增 `chatlog_state_store.py`（SQLite）：
  - `processed_messages`
  - `checkpoints`
- 幂等键策略：
  - 优先 `seq`
  - 回退 `sha256(talker+sender+time+content)`

### 验证
- 重放请求 `accepted=0`，不会重复写入。

---

## 7. 需求：实现停机补偿（backfill）

### 问题现象
- 初次回补显示 `accepted=0`，误判为功能失效。

### 根因
- 初始回补窗口过小（例如 `bootstrap_days=1`），窗口内无新数据。

### 解决方案
- 支持并使用可配置窗口（如 `CHATLOG_BACKFILL_BOOTSTRAP_DAYS=30`）。
- 在 `/healthz` 增加最近 backfill 报告，便于判断是否真正执行过。

### 验证
- 扩窗后成功回补并推进 checkpoint。

---

## 8. 需求：群聊按业务价值过滤（减少噪音）

### 问题现象
- 群消息量大，直接沉淀会污染记忆层。

### 根因
- 缺少按群类型与关键人物的筛选策略。

### 解决方案
- 增加 `chatlog_targets` 配置层（持久化）：
  - `group_type`
  - `important_people`
  - `capture_policy`
- 策略落地：
  - `notification`：仅高价值关键词通过
  - 配置了 `important_people` 的群：关键人消息通过；高价值事件仍可通过
- 规则同时应用到 webhook 与 backfill。

### 验证
- 非关键人普通消息被过滤，关键人消息可进入沉淀流程。

---

## 9. 需求：按记忆层路由沉淀结果

### 问题现象
- 早期统一写 Inbox，后续检索和管理成本高。

### 根因
- 未按业务域路由到 `memory` 分层目录。

### 解决方案
- 在 `memory_stage1.py` 增加 `create_bucket_note(...)`。
- 路由规则：
  - 联系人 -> `20_Connections`
  - 学习群 -> `10_Growth`
  - 信息差群 -> `40_ProductMind`
  - 通知群 -> `00_Inbox`

### 验证
- 单测覆盖路由行为，写入目录符合预期。

---

## 10. 当前结论

对接链路已具备：
1. 配置管理（API + 飞书命令）
2. webhook 鉴权与幂等
3. backfill 补偿与 checkpoint
4. 群类型/关键人筛选
5. 记忆分层沉淀
6. `healthz` 可观测状态

后续重点建议：
1. 让 `capture_policy`（`summary_only/key_events/hybrid`）真正影响输出内容粒度。
2. 增加“建议回复”结构化输出与人工确认流程。
3. 增加集成告警（连续回补失败、去重异常升高、消息积压）。

---

## 11. 需求：在飞书中提供可用的“联系人回复建议”能力（/reply suggest）

### 问题现象
- 飞书输入 `/reply suggest 郝睿` 返回 `Unknown skill: reply`。

### 根因
- 命令没有在 `feishu_ws_bridge` 前置拦截，直接进入通用 `run_agent`，被当成技能命令解析。

### 解决方案
- 在桥接层新增命令处理器：`handle_reply_suggest_command(...)`。
- 在 `_handle_text_async(...)` 中优先拦截 `/reply suggest`，命中后直接回发，不再走通用对话流。

### 验证
- 单测覆盖命令路由优先级通过。
- 飞书侧不再出现 `Unknown skill: reply`。

---

## 12. 需求：支持按联系人昵称检索目标对象

### 问题现象
- `/reply suggest 郝睿` 返回 `未找到联系人: 郝睿`。

### 根因
- chatlog `/api/v1/contact` 实际返回为 `{"items": [...]}`，而解析逻辑只处理了顶层 list。

### 解决方案
- `_resolve_reply_target(...)` 同时兼容：
  - list
  - dict.items
- 增加昵称/备注等字段匹配逻辑。

### 验证
- 加入 `dict.items` 结构测试后通过。
- 昵称检索可命中并映射到 `talker(wxid)`。

---

## 13. 需求：找不到“最近聊天消息”时保持可用

### 问题现象
- `/reply suggest ...` 频繁返回 `未找到最近聊天消息`。

### 根因
- 查询窗口过窄（仅近 3 天）。
- 最近一条常见为非文本或空 content（如 type=3），被直接过滤。

### 解决方案
- 消息拉取改为回退窗口：`3天 -> 30天 -> 365天`。
- 从最近向前扫描，跳过空内容，寻找最近可用文本消息。

### 验证
- 对历史联系人可命中较早文本消息。
- 相关单测通过。

---

## 14. 需求：区分“你说的话”与“对方说的话”

### 问题现象
- 建议里有时把自己发送的消息当作“对方最新消息”。

### 根因
- 仅取最后一条可用消息，未优先 `isSelf=false`。

### 解决方案
- 优先选择对方侧消息（`isSelf=false`）。
- 若最近可用消息仅来自自己，则明确提示：`暂无对方新消息`，避免误导建议。

### 验证
- 输出增加“最近消息发送方”语义一致。
- 单测覆盖“仅 self 消息”分支通过。

---

## 15. 需求：建议输出要可直接复制，避免“过程话术”污染

### 问题现象
- 模型输出中混入“我先搜索/让我查看”等过程句，影响可读性。

### 根因
- 下游直接透传 agent 原始输出，缺少结果清洗。

### 解决方案
- 增加 `_clean_reply_suggestion_text(...)`：
  - 优先截取结构化段落（对方意图/建议回复等）。
  - 过滤过程话术行。
- 缺失关键段落时自动补齐：
  - `超短回复(15-30字)`
  - `需要确认的问题`（不允许“无”）

### 验证
- 新增测试覆盖“过程话术剔除”和“段落自动补齐”通过。

---

## 16. 需求：避免只看“最新一句”，要结合多轮语境

### 问题现象
- 对“好吧”这类短句，建议偏泛化，命中真实意图不足。

### 根因
- 早期提示词过度依赖单条最新消息。

### 解决方案
- 输入上下文升级为：
  - 双方最近 10 条对话（按说话方标注）
  - 对方最新消息作为锚点
  - 该联系人记忆摘要（`memory/20_Connections`）

### 验证
- 对短句场景的建议稳定性提升。
- 提示词构建与上下文窗口测试通过。

---

## 17. 需求：支持“完整/轻量”两种输出模式

### 问题现象
- 全量结构在高频场景下偏长，不利于快速发送。

### 根因
- 只有单一输出形态。

### 解决方案
- 新增参数：`mode=lite|full`（默认 full）。
- `lite` 只保留：
  - 建议回复
  - 超短回复

### 验证
- `/reply suggest xxx mode=lite` 可输出短格式。
- 相关测试通过。

---

## 18. 需求：引入联系人沟通风格偏好（非强模板）

### 问题现象
- 在记忆不足时，回复风格容易回落到“通用中性语气”。

### 根因
- 提示词缺少联系人风格显式输入。

### 解决方案
- 从 `chatlog_targets` 增加并读取风格字段：
  - `reply_style`
  - `relationship_note`
  - `etiquette_preferences`
  - `tone_preference`
- 注入到回复建议 prompt 的“联系人沟通风格偏好”区块。
- 同步扩展 `/memory group update` 支持以上字段。

### 验证
- 风格字段可通过命令配置并在 prompt 中生效。
- 命令与建议链路测试通过。

---

## 19. 当前结论（reply suggest 阶段）

已形成可实用闭环：
1. 飞书命令触发（联系人/昵称解析）
2. chatlog 多窗口拉取 + 对方侧优先
3. 多轮上下文 + 联系人记忆 + 风格偏好注入
4. 结构化输出与轻量模式
5. 过程话术清洗与段落补齐

后续建议：
1. 继续用真实会话反馈沉淀联系人记忆，优先补“关系/礼仪/禁忌/目标语气”。
2. 保持“先补上下文再建议”的策略，不急于做硬编码强模板。
