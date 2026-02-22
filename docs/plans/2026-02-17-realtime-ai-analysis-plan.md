# Chatlog 接入 AI 记忆系统总体规划（V1）

> 文档定位：这是当前阶段的总规划文档。  
> 执行清单见：`docs/plans/2026-02-17-realtime-ai-analysis-agent-sop.md`

## 1. 目标与定位

当前系统已经具备 Claude Code 驱动的分析、整理、问答、总结能力。  
接入 `chatlog` 的目的，是新增自动化数据来源，减少你手工“口传”记忆的成本。

一句话目标：
- 以 `chatlog` 作为微信数据网关，将“重要联系人 + 重要群聊”的高价值信息，自动沉淀到现有 `memory` 体系。

## 2. 系统边界

1. 不复制 `chatlog` 源码。
2. 仅通过外部接口接入（HTTP / webhook / MCP）。
3. 可靠性主链路是 HTTP 回补，不依赖单一实时通道。
4. webhook 用于低延迟，不用于兜底正确性。
5. MCP（`/mcp` 或 `/sse`）用于交互增强，不承担防漏主链路。

## 3. 通道策略

双通道（推荐）：

1. 实时通道：Webhook（建议启用）
- 作用：新消息触发快速分析
- 目标：尽快给出摘要/建议

2. 正确性通道：HTTP 回补（必须）
- 作用：补偿停机或链路中断期间遗漏
- 目标：最终一致性

补充：
- MCP 适合按需查询，不替代回补任务。

## 4. 记忆映射策略

## 4.1 联系人（重点）

联系人消息主落点：`memory/20_Connections`。

沉淀内容：
- 关系变化（升温/降温/冲突/机会）
- 承诺与待办
- 对方近况与关键事件
- 建议回复与下一步动作

## 4.2 群聊（按类型处理）

群聊不走统一规则，按 `group_type` 选择提取器：

1. `relationship`
- 主落点：`20_Connections`
- 输出：人物动态、关系影响、关键事件

2. `notification`
- 默认不入长期记忆
- 仅高优先级通知进入短期提醒或 Inbox 待确认

3. `learning`
- 主落点：`10_Growth`
- 输出：知识点、方法、可执行学习项

4. `info_gap`
- 主落点：`40_ProductMind`
- 涉及关键人物时补充写入 `20_Connections`

## 5. 群配置卡片模型（飞书侧）

```yaml
group_id: "123456@chatroom"
group_name: "产品创业讨论群"
group_type: "info_gap"   # relationship | notification | learning | info_gap
importance: 4            # 1-5
default_memory_bucket: "40_ProductMind"
focus_topics:
  - "AI 产品"
  - "创业机会"
important_people:
  - "张三"
  - "李四"
noise_tolerance: "low"   # low | medium | high
capture_policy: "summary_only" # summary_only | key_events | hybrid
```

## 6. 过滤与入库判定（V1）

采用四层判定：

1. 范围过滤：仅重点联系人/重点群
2. 结构过滤：标准化、去重、窗口聚合
3. LLM 判定：标签 + 分数
- 标签：`todo` `commitment` `risk` `decision` `relationship_signal` `knowledge` `noise`
- 输出：`importance_score`（0-100）、`confidence`（0-1）
4. 入库门槛：
- 高分直接入记忆
- 中分进入待确认
- 低分仅短期缓存

## 7. 飞书交互形态

## 阶段 1（先做）

文本命令管理：
- `/memory group add ...`
- `/memory group update ...`
- `/memory group people ...`
- `/memory group list`

## 阶段 2（增强）

机器人卡片交互：
- 配置卡片（查看和调整群策略）
- 分析卡片（确认/忽略/升级入库）

说明：
- 飞书卡片可以在普通聊天会话中展示，不需要单独开发者界面才能使用。

## 8. 与当前项目的落地关系

现有基础：
- 服务入口：`app.py`
- 记忆写入与索引：`memory_stage1.py`、`memory_index.py`
- 配置：`runtime_config.py`
- 健康检查：`/healthz`

建议新增模块：
- `chatlog_contracts.py`（统一消息模型）
- `chatlog_state_store.py`（去重与 checkpoint）
- `chatlog_ingest.py`（Webhook/HTTP 入站）
- `chatlog_backfill.py`（回补调度）

## 9. 里程碑

1. M1：联系人 + 群聊双线最小接入
2. M2：回补、重试、死信、监控
3. M3：飞书卡片与人审流程
4. M4：建议回复能力（先人工确认，再评估自动发送）

## 10. 成功标准

1. 重点联系人消息可在可接受时延内沉淀记忆。
2. 重点群聊能稳定提取高价值内容，噪音可控。
3. 停机后可回补且不重复污染记忆。
4. 飞书可动态调整重点对象与策略。

## 11. 近期不做

1. 不做全量聊天无差别入库。
2. 不把 MCP/SSE 作为防漏主链路。
3. 初期不开放全自动代发消息。
