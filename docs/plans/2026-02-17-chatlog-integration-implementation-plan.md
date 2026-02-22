# Chatlog Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 `claude-memory-system` 中落地 Chatlog 双通道接入（Webhook 实时 + HTTP 回补），并保证幂等、防漏、可追溯。

**Architecture:** 在现有 FastAPI 服务内新增集成模块：Webhook 接收层、去重与 checkpoint 持久层、回补调度层、记忆写入层。实时消息与回补消息走同一处理流水线，统一幂等键与时间窗口语义。所有结果写入结构化表并可映射到现有 `memory` 目录。

**Tech Stack:** Python 3.12, FastAPI, SQLite (`sqlite3`), pytest, existing memory modules (`memory_stage1.py`, `memory_index.py`)

---

### Task 1: Runtime Config and Contract Types

**Files:**
- Create: `chatlog_contracts.py`
- Modify: `runtime_config.py`
- Modify: `app.py`
- Test: `tests/test_runtime_config.py`

**Step 1: Write the failing test**

在 `tests/test_runtime_config.py` 新增断言，验证新配置默认值与 env 读取：
- `chatlog_enabled`
- `chatlog_base_url`
- `chatlog_webhook_token`
- `chatlog_backfill_interval_seconds`

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runtime_config.py -q`  
Expected: FAIL，提示新字段不存在或默认值不匹配。

**Step 3: Write minimal implementation**

- 在 `runtime_config.py` 增加字段与解析逻辑（含容错默认值）。
- 在 `chatlog_contracts.py` 定义统一消息模型（如 `ChatlogMessage`, `ChatlogWebhookPayload`）。
- 在 `app.py` 只注入配置，不做行为改动。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runtime_config.py -q`  
Expected: PASS。

**Step 5: Commit**

```bash
git add runtime_config.py chatlog_contracts.py app.py tests/test_runtime_config.py
git commit -m "feat: add chatlog integration runtime config and contracts"
```

### Task 2: Idempotency and Checkpoint Store

**Files:**
- Create: `chatlog_state_store.py`
- Test: `tests/test_chatlog_state_store.py`

**Step 1: Write the failing test**

在 `tests/test_chatlog_state_store.py` 增加：
- 首次写入幂等键成功，重复写入被忽略
- checkpoint 可读写
- checkpoint 仅在“更大时间/序号”时推进

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chatlog_state_store.py -q`  
Expected: FAIL，模块或方法不存在。

**Step 3: Write minimal implementation**

在 `chatlog_state_store.py` 用 SQLite 实现：
- `processed_messages(idempotency_key primary key, talker, message_time, created_at)`
- `checkpoints(talker primary key, last_processed_time, last_processed_seq, updated_at)`
- `is_processed`, `mark_processed`, `load_checkpoint`, `advance_checkpoint`

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_chatlog_state_store.py -q`  
Expected: PASS。

**Step 5: Commit**

```bash
git add chatlog_state_store.py tests/test_chatlog_state_store.py
git commit -m "feat: add sqlite state store for idempotency and checkpoints"
```

### Task 3: Webhook Ingest Endpoint with Auth

**Files:**
- Create: `chatlog_ingest.py`
- Modify: `app.py`
- Test: `tests/test_chatlog_webhook_api.py`

**Step 1: Write the failing test**

在 `tests/test_chatlog_webhook_api.py` 覆盖：
- 缺少 token 返回 401/403
- payload 缺字段返回 400
- 合法请求返回 200，且调用统一处理函数

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chatlog_webhook_api.py -q`  
Expected: FAIL，路由不存在或鉴权不生效。

**Step 3: Write minimal implementation**

- 在 `app.py` 新增 `POST /api/integrations/chatlog/webhook`
- 在 `chatlog_ingest.py` 实现：
  - token 校验
  - payload 规范化到 `ChatlogMessage`
  - 生成幂等键：优先 `seq`，否则 hash

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_chatlog_webhook_api.py -q`  
Expected: PASS。

**Step 5: Commit**

```bash
git add app.py chatlog_ingest.py tests/test_chatlog_webhook_api.py
git commit -m "feat: add authenticated chatlog webhook ingest endpoint"
```

### Task 4: Unified Processing Pipeline and Memory Sink

**Files:**
- Modify: `chatlog_ingest.py`
- Modify: `memory_stage1.py`
- Test: `tests/test_chatlog_processing_pipeline.py`

**Step 1: Write the failing test**

在 `tests/test_chatlog_processing_pipeline.py` 覆盖：
- 重复消息只处理一次
- 联系人消息输出实时分析记录
- 群聊消息按窗口聚合后输出总结记录
- 结果可追溯到 `source_message_ids`

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chatlog_processing_pipeline.py -q`  
Expected: FAIL。

**Step 3: Write minimal implementation**

- 在 `chatlog_ingest.py` 增加统一入口 `process_messages(talker, messages, mode)`。
- 将分析结果写入 `analysis_results`（SQLite）。
- 映射写入 `memory/00_Inbox`（调用 `create_inbox_note`），并附来源区间元数据。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_chatlog_processing_pipeline.py -q`  
Expected: PASS。

**Step 5: Commit**

```bash
git add chatlog_ingest.py memory_stage1.py tests/test_chatlog_processing_pipeline.py
git commit -m "feat: add unified chatlog processing pipeline and memory sink"
```

### Task 5: Backfill Scheduler

**Files:**
- Create: `chatlog_backfill.py`
- Modify: `app.py`
- Test: `tests/test_chatlog_backfill.py`

**Step 1: Write the failing test**

在 `tests/test_chatlog_backfill.py` 覆盖：
- 启动后执行一次回补
- 定时回补间隔正确
- 回补失败时 checkpoint 不推进

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chatlog_backfill.py -q`  
Expected: FAIL。

**Step 3: Write minimal implementation**

- 在 `chatlog_backfill.py` 实现：
  - `run_backfill_once()`
  - `schedule_backfill_task()`
  - 时间窗口 `(checkpoint, now]`
- 在 `app.py` 的 startup/shutdown 钩子接入任务生命周期。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_chatlog_backfill.py -q`  
Expected: PASS。

**Step 5: Commit**

```bash
git add chatlog_backfill.py app.py tests/test_chatlog_backfill.py
git commit -m "feat: add periodic chatlog backfill scheduler"
```

### Task 6: E2E and Observability

**Files:**
- Modify: `app.py`
- Modify: `README.md`
- Create: `docs/chatlog-integration-runbook.md`
- Test: `tests/test_healthz_api.py`
- Test: `tests/test_chatlog_e2e_flow.py`

**Step 1: Write the failing test**

新增集成测试 `tests/test_chatlog_e2e_flow.py`：
- 模拟 webhook + backfill 混合输入
- 断言最终分析结果去重一致
- 断言 healthz 返回 chatlog 集成状态（最后回补时间/失败计数）

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chatlog_e2e_flow.py tests/test_healthz_api.py -q`  
Expected: FAIL。

**Step 3: Write minimal implementation**

- `app.py` 扩展 `GET /healthz` 输出 chatlog 集成指标。
- `docs/chatlog-integration-runbook.md` 增加：
  - 启停命令
  - 环境变量模板
  - 常见故障排查

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q`  
Expected: 全绿。

**Step 5: Commit**

```bash
git add app.py README.md docs/chatlog-integration-runbook.md tests/test_chatlog_e2e_flow.py tests/test_healthz_api.py
git commit -m "feat: add chatlog integration observability and e2e validation"
```

---

## Delivery Checklist

- Webhook 与 backfill 统一幂等键策略
- checkpoint 推进遵循 `(last_checkpoint, now]`
- 所有分析结果记录 `source_message_ids`
- 未授权 webhook 不能入队
- 停机恢复后可补齐消息且无重复污染

