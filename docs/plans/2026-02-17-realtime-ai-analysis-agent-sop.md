# Chatlog 集成 Agent 执行清单（SOP）

> 本文为执行文档。总体策略见：`docs/plans/2026-02-17-realtime-ai-analysis-plan.md`

## 0. 执行目标

在当前仓库落地最小可用接入：
- 重点联系人 + 重点群聊双线同步
- 幂等去重
- 回补防漏
- 结构化记忆沉淀

## 1. 前置约束

1. 不复制 `chatlog` 代码。
2. 仅通过外部接口接入（HTTP / webhook / MCP）。
3. 所有处理必须幂等。
4. 必须实现回补，不能只靠 webhook。
5. Webhook 必须鉴权（Token 或 HMAC）。

## 2. 环境参数

- `CHATLOG_BASE_URL`，如 `http://127.0.0.1:5030`
- `CHATLOG_ENABLED`
- `CHATLOG_WEBHOOK_TOKEN`
- `CHATLOG_BACKFILL_INTERVAL_SECONDS`
- `MONITORED_TALKERS`

## 3. 执行步骤

## Step 1：连通性检查

1. 调用 `GET /health`
2. 调用 `GET /api/v1/session`
3. 调用 `GET /api/v1/contact`
4. 对重点对象执行一次 `/api/v1/chatlog` 拉取

通过标准：接口可达，返回结构正确。

## Step 2：建立状态存储

至少包含三张表：
1. `checkpoints`
2. `processed_messages`
3. `analysis_results`

通过标准：支持去重、checkpoint 推进、结果追溯。

## Step 3：实现接收端与统一模型

1. 提供 `POST /api/integrations/chatlog/webhook`
2. 校验鉴权
3. 校验 payload
4. 标准化为统一消息模型
5. 写接收与错误日志

通过标准：
- 合法请求可入队
- 非法鉴权返回 401/403 且不入队

## Step 4：实现幂等与顺序

1. 幂等键：优先 `seq`，回退 `hash(talker+sender+time+content)`
2. 处理顺序：`message_time ASC, seq ASC`
3. 回补窗口：`(last_checkpoint, now]`（左开右闭）

通过标准：重复 webhook/回补不重复入库。

## Step 5：联系人分析

输出：
- 意图
- 情绪
- 待办
- 建议回复

主落点：`memory/20_Connections`。

## Step 6：群聊按类型处理

按 `group_type` 路由：
- `relationship` -> `20_Connections`
- `learning` -> `10_Growth`
- `info_gap` -> `40_ProductMind` + `20_Connections`
- `notification` -> 短期提醒/Inbox

## Step 7：回补任务

1. 启动时回补一次
2. 周期增量回补
3. 回补失败不推进 checkpoint
4. 回补成功推进到最大已处理游标

通过标准：停机后可补齐且无重复污染。

## 4. 飞书交互执行约定

## 阶段 1：文本命令

- `/memory group add ...`
- `/memory group update ...`
- `/memory group people ...`
- `/memory group list`

## 阶段 2：卡片交互

- 配置卡片（查看/调整群策略）
- 分析卡片（确认/忽略/升级入库）

## 5. 验收清单

1. 联系人实时分析可落库。
2. 群聊按类型落到正确记忆层。
3. 去重生效，不重复污染。
4. 停机后回补可补齐。
5. 鉴权失败请求被拒绝并可审计。

## 6. Agent 输出要求

每次任务执行后，输出：
1. 已完成步骤编号
2. 当前失败项
3. 下一步动作
4. 证据位置（日志/数据）
