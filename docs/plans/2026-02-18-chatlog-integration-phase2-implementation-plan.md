# Chatlog Integration Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the current chatlog ingestion into a production-ready loop with policy-driven filtering, reply suggestion workflow, and reliable operations.

**Architecture:** Keep current webhook + backfill + memory pipeline, then add a policy layer (`capture_policy` behavior), an optional reply-draft layer, and operational guardrails. All new behaviors are test-first and behind config/commands so rollout is safe.

**Tech Stack:** FastAPI, asyncio background loop, SQLite state store, JSON target store, pytest.

---

### Task 1: Stabilize baseline and remove noisy runtime artifacts

**Files:**
- Modify: `tests/test_healthz_api.py`
- Modify: `tests/test_memory_stage1.py`
- Optional cleanup: `memory/00_Inbox/*` (generated runtime notes)

**Step 1: Write/adjust failing tests for clean health output**
```python
def test_healthz_reports_chatlog_runtime_fields():
    ...
```

**Step 2: Run targeted tests**
Run: `pytest tests/test_healthz_api.py tests/test_memory_stage1.py -v`
Expected: Any mismatch in health/runtime fields fails first.

**Step 3: Minimal code alignment**
Align health payload and memory note metadata to match test expectations.

**Step 4: Re-run targeted tests**
Run: `pytest tests/test_healthz_api.py tests/test_memory_stage1.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add tests/test_healthz_api.py tests/test_memory_stage1.py app.py memory_stage1.py
git commit -m "test: stabilize chatlog health and memory note baseline"
```

### Task 2: Make `capture_policy` truly effective (`summary_only`/`key_events`/`hybrid`)

**Files:**
- Modify: `app.py`
- Modify: `chatlog_targets.py`
- Test: `tests/test_chatlog_webhook_api.py`
- Test: `tests/test_chatlog_backfill.py`

**Step 1: Add failing tests for 3 policy modes**
```python
def test_group_summary_only_skips_raw_messages():
    ...

def test_group_key_events_only_accepts_high_value_events():
    ...

def test_group_hybrid_accepts_key_people_and_events():
    ...
```

**Step 2: Run tests to confirm failure**
Run: `pytest tests/test_chatlog_webhook_api.py tests/test_chatlog_backfill.py -v`
Expected: FAIL because current policy behavior is incomplete.

**Step 3: Implement minimal policy evaluator**
Add one policy function used by both webhook and backfill paths.

**Step 4: Re-run tests**
Run: `pytest tests/test_chatlog_webhook_api.py tests/test_chatlog_backfill.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add app.py chatlog_targets.py tests/test_chatlog_webhook_api.py tests/test_chatlog_backfill.py
git commit -m "feat: enforce capture_policy across webhook and backfill"
```

### Task 3: Add Feishu command support for policy/person tuning

**Files:**
- Modify: `feishu_ws_bridge.py`
- Test: `tests/test_feishu_memory_group_commands.py`

**Step 1: Add failing tests for commands**
```python
def test_memory_group_update_capture_policy():
    ...

def test_memory_group_people_set_replaces_people_list():
    ...
```

**Step 2: Run tests**
Run: `pytest tests/test_feishu_memory_group_commands.py -v`
Expected: FAIL for missing parser/handler branches.

**Step 3: Implement parser and output formatting**
Keep command grammar simple and deterministic.

**Step 4: Re-run tests**
Run: `pytest tests/test_feishu_memory_group_commands.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add feishu_ws_bridge.py tests/test_feishu_memory_group_commands.py
git commit -m "feat: extend memory group commands for policy and people tuning"
```

### Task 4: Reply suggestion pipeline (draft only, no auto-send)

**Files:**
- Modify: `app.py`
- Create/Modify: `reply_building.py`
- Test: `tests/test_reply_building.py`
- Create: `tests/test_chatlog_reply_suggestion_api.py`

**Step 1: Add failing tests for suggestion generation and safety gates**
```python
def test_reply_suggestion_generated_for_enabled_contact():
    ...

def test_reply_suggestion_requires_manual_confirm_flag():
    ...
```

**Step 2: Run tests**
Run: `pytest tests/test_reply_building.py tests/test_chatlog_reply_suggestion_api.py -v`
Expected: FAIL.

**Step 3: Implement minimal draft suggestion API/object**
Return structured draft + reason + confidence; never send automatically.

**Step 4: Re-run tests**
Run: `pytest tests/test_reply_building.py tests/test_chatlog_reply_suggestion_api.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add app.py reply_building.py tests/test_reply_building.py tests/test_chatlog_reply_suggestion_api.py
git commit -m "feat: add chatlog reply suggestion draft workflow"
```

### Task 5: Operational guardrails and observability

**Files:**
- Modify: `app.py`
- Modify: `runtime_config.py`
- Test: `tests/test_runtime_config.py`
- Test: `tests/test_healthz_api.py`

**Step 1: Add failing tests for alert thresholds in health status**
```python
def test_healthz_exposes_backfill_error_threshold_state():
    ...
```

**Step 2: Run tests**
Run: `pytest tests/test_runtime_config.py tests/test_healthz_api.py -v`
Expected: FAIL.

**Step 3: Implement minimal thresholds**
Add config + counters for consecutive backfill failures and dedup anomaly ratio.

**Step 4: Re-run tests**
Run: `pytest tests/test_runtime_config.py tests/test_healthz_api.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add app.py runtime_config.py tests/test_runtime_config.py tests/test_healthz_api.py
git commit -m "feat: add chatlog operational thresholds and health signals"
```

### Task 6: End-to-end regression and docs handoff

**Files:**
- Modify: `docs/chatlog-integration-issues-and-solutions.md`
- Modify: `docs/README.md`
- Optional: `docs/plans/2026-02-17-chatlog-integration-implementation-plan.md`

**Step 1: Run full test suite**
Run: `pytest -q`
Expected: PASS.

**Step 2: Validate live flows manually**
Run webhook replay + one backfill cycle + `/memory group` command checks.

**Step 3: Update docs with what changed**
Document new policy behavior, new commands, and reply draft constraints.

**Step 4: Final commit**
```bash
git add docs/chatlog-integration-issues-and-solutions.md docs/README.md
git commit -m "docs: update phase-2 chatlog integration behavior and ops notes"
```
