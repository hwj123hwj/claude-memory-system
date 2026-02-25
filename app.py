from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import shlex
from contextlib import suppress
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_security import is_tool_input_within_root
from chat_logging import SessionLogger, serialize_message
from chatlog_backfill import fetch_chatlog_messages, run_backfill_once
from chatlog_state_store import ChatlogStateStore
from chatlog_targets import ChatlogTargetStore
from conversation_session import resolve_session_id
from memory_context import build_memory_context
from memory_index import write_memory_index
from memory_stage1 import create_bucket_note, create_inbox_note, ensure_memory_layout
from prompt_builder import (
    build_effective_prompt,
    has_explicit_new_file_intent,
    has_explicit_write_intent,
)
from runtime_config import load_runtime_config
from stale_client_cleanup import schedule_stale_client_cleanup

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
        TextBlock,
    )
    from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny
except Exception:  # pragma: no cover
    AssistantMessage = None
    TextBlock = None
    ResultMessage = None
    ClaudeAgentOptions = None
    ClaudeSDKClient = None
    PermissionResultAllow = None
    PermissionResultDeny = None


WORKSPACE_ROOT = Path(__file__).resolve().parent
STATIC_DIR = WORKSPACE_ROOT / "static"
LOG_DIR = WORKSPACE_ROOT / "logs"
CHATLOG_STATE_DB = LOG_DIR / "chatlog_state.db"
CHATLOG_TARGETS_FILE = LOG_DIR / "chatlog_targets.json"
BRIDGE_HEARTBEAT_FILE = LOG_DIR / "feishu_bridge_heartbeat.json"
BRIDGE_HEARTBEAT_STALE_SECONDS = 180
RUNTIME_CONFIG = load_runtime_config(WORKSPACE_ROOT / ".env")

ALLOWED_TOOLS = ["Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "LS"]
WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}

SYSTEM_PROMPT = (
    "You are a file assistant. You can only read or write files inside the current workspace. "
    "Never access paths outside workspace. Keep responses concise. "
    "If user asks about memory system or personal memory summary, inspect files under memory first."
)

app = FastAPI(title="Claude Code Web Agent")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

CURRENT_LOGGER: ContextVar[SessionLogger | None] = ContextVar("CURRENT_LOGGER", default=None)
WRITE_TOOLS_ALLOWED: ContextVar[bool] = ContextVar("WRITE_TOOLS_ALLOWED", default=False)
NEW_FILE_ALLOWED: ContextVar[bool] = ContextVar("NEW_FILE_ALLOWED", default=False)
CLIENT: ClaudeSDKClient | None = None
ACTIVE_CONVERSATION_ID: str | None = None
STALE_CLIENTS: list[ClaudeSDKClient] = []
STALE_CLEANUP_TASK: asyncio.Task | None = None
CHATLOG_BACKFILL_TASK: asyncio.Task | None = None
CHATLOG_RUNTIME: dict[str, Any] = {
    "last_webhook_at": None,
    "webhook_accepted_total": 0,
    "webhook_deduped_total": 0,
    "last_backfill_at": None,
    "last_backfill_report": None,
    "backfill_errors_total": 0,
    "backfill_consecutive_error_runs": 0,
}
CLIENT_INIT_LOCK = asyncio.Lock()
CLIENT_QUERY_LOCK = asyncio.Lock()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    new_conversation: bool = False


class ChatResponse(BaseModel):
    reply: str
    workspace: str
    log_file: str
    conversation_id: str
    is_new_session: bool


class MemoryCaptureRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    title: str = Field(default="capture", min_length=1, max_length=120)
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="chat", min_length=1, max_length=120)


class MemoryCaptureResponse(BaseModel):
    path: str
    message: str


class MemoryReindexResponse(BaseModel):
    path: str
    message: str


class ChatlogWebhookRequest(BaseModel):
    talker: str = Field(min_length=1, max_length=200)
    messages: list[dict[str, Any]] = Field(min_length=1)


class ChatlogWebhookResponse(BaseModel):
    ok: bool
    talker: str
    accepted: int
    mode: str


class ChatlogTargetUpsertRequest(BaseModel):
    talker: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    group_type: str = Field(default="info_gap", max_length=40)
    importance: int = Field(default=3, ge=1, le=5)
    default_memory_bucket: str = Field(default="40_ProductMind", max_length=40)
    focus_topics: list[str] = Field(default_factory=list)
    important_people: list[str] = Field(default_factory=list)
    noise_tolerance: str = Field(default="medium", max_length=20)
    capture_policy: str = Field(default="summary_only", max_length=30)


SAFE_BASH_COMMANDS = {
    "rm",
    "mv",
    "cp",
    "mkdir",
    "ls",
    "cat",
    "del",
    "move",
    "copy",
    "ren",
    "rename",
    "remove-item",
    "move-item",
    "copy-item",
    "new-item",
    "get-childitem",
}
UNSAFE_BASH_TOKENS = {"&&", "||", ";", "|", ">", "<", "$(", "`"}


def _block_text(block: Any) -> str | None:
    if isinstance(block, dict):
        text = block.get("text")
        if isinstance(text, str):
            return text
        content = block.get("content")
        if isinstance(content, str):
            return content
        return None
    text = getattr(block, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(block, "content", None)
    if isinstance(content, str):
        return content
    return None


def _block_is_error(block: Any) -> bool:
    if isinstance(block, dict):
        return bool(block.get("is_error"))
    return bool(getattr(block, "is_error", False))


def build_reply_text(
    chunks: list[str],
    tool_errors: list[str],
    interrupted: bool,
    result_is_error: bool,
    result_subtype: str | None,
    compact_applied: bool,
    log_path: Path,
) -> str:
    reply = "\n".join(x for x in chunks if x and x.strip()).strip()
    if reply:
        return reply

    if compact_applied:
        return f"上下文已压缩完成。日志文件：{log_path}"

    if tool_errors:
        return f"执行失败：{tool_errors[-1]}\n日志文件：{log_path}"

    if interrupted or result_is_error or result_subtype == "error_during_execution":
        return f"执行中断，未产生可显示文本输出。日志文件：{log_path}"

    return f"请求已完成，但没有可显示文本输出。日志文件：{log_path}"


def _looks_like_path_token(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    token = token.strip().strip("\"'")
    if not token:
        return False
    return ("\\" in token) or ("/" in token) or ("." in Path(token).name)


def _to_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_error_stream(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


def _format_agent_exception(exc: Exception) -> str:
    parts: list[str] = [str(exc).strip() or repr(exc)]

    stderr_text = _normalize_error_stream(getattr(exc, "stderr", None))
    stdout_text = _normalize_error_stream(getattr(exc, "stdout", None))
    if stderr_text:
        parts.append(f"stderr: {stderr_text}")
    if stdout_text:
        parts.append(f"stdout: {stdout_text}")

    return "\n".join(parts)


def _build_idempotency_key(talker: str, message: dict[str, Any]) -> str:
    seq = _to_int_or_none(message.get("seq"))
    if seq is not None:
        return f"{talker}:{seq}"
    raw = (
        f"{talker}|"
        f"{message.get('sender', '')}|"
        f"{message.get('time', '')}|"
        f"{message.get('content', '')}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_title_suffix(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value).strip("_")
    return cleaned[:40] if cleaned else "chatlog"


def _persist_chatlog_note(*, talker: str, mode: str, messages: list[dict[str, Any]], source: str) -> None:
    if not messages:
        return
    lines: list[str] = []
    for item in messages[:5]:
        ts = item.get("time", "")
        sender = item.get("senderName") or item.get("sender") or ""
        content = str(item.get("content", "")).strip().replace("\n", " ")
        lines.append(f"- [{ts}] {sender}: {content[:120]}")
    body = (
        f"talker: {talker}\n"
        f"mode: {mode}\n"
        f"accepted_count: {len(messages)}\n\n"
        "sample_messages:\n"
        + ("\n".join(lines) if lines else "- (none)")
    )
    bucket = "00_Inbox"
    if mode == "contact_realtime":
        bucket = "20_Connections"
    elif mode == "group_digest":
        targets = ChatlogTargetStore(CHATLOG_TARGETS_FILE)
        cfg = targets.get_target(talker) or {}
        group_type = str(cfg.get("group_type", "info_gap"))
        if group_type == "relationship":
            bucket = "20_Connections"
        elif group_type == "learning":
            bucket = "10_Growth"
        elif group_type == "notification":
            bucket = "00_Inbox"
        else:
            bucket = str(cfg.get("default_memory_bucket", "40_ProductMind"))
    create_bucket_note(
        root=WORKSPACE_ROOT,
        bucket=bucket,
        content=body,
        title=f"chatlog_{_safe_title_suffix(talker)}",
        tags=["chatlog", mode],
        source=source,
        memory_type="chatlog",
    )


def _build_chatlog_health() -> dict[str, Any]:
    target_store = ChatlogTargetStore(CHATLOG_TARGETS_FILE)
    accepted_total = int(CHATLOG_RUNTIME.get("webhook_accepted_total", 0))
    deduped_total = int(CHATLOG_RUNTIME.get("webhook_deduped_total", 0))
    total = accepted_total + deduped_total
    dedup_ratio = (deduped_total / total) if total > 0 else 0.0
    backfill_streak = int(CHATLOG_RUNTIME.get("backfill_consecutive_error_runs", 0))
    signals = {
        "backfill_error_alert": (
            backfill_streak >= RUNTIME_CONFIG.chatlog_backfill_consecutive_error_threshold
        ),
        "webhook_dedup_alert": (
            total >= RUNTIME_CONFIG.chatlog_webhook_dedup_min_total
            and dedup_ratio >= RUNTIME_CONFIG.chatlog_webhook_dedup_ratio_threshold
        ),
        "backfill_consecutive_error_runs": backfill_streak,
        "webhook_dedup_ratio": round(dedup_ratio, 4),
    }
    return {
        "enabled": bool(RUNTIME_CONFIG.chatlog_enabled),
        "base_url": RUNTIME_CONFIG.chatlog_base_url,
        "monitored_talkers": list(RUNTIME_CONFIG.chatlog_monitored_talkers),
        "configured_targets": target_store.list_targets(),
        "state_db": str(CHATLOG_STATE_DB),
        "targets_file": str(CHATLOG_TARGETS_FILE),
        "signals": signals,
        **CHATLOG_RUNTIME,
    }


def _is_notification_important(message: dict[str, Any]) -> bool:
    content = str(message.get("content", "")).lower()
    keywords = ("urgent", "important", "deadline", "meeting", "risk", "alert", "notice")
    return any(k in content for k in keywords)


def _hits_important_people(message: dict[str, Any], people: list[str]) -> bool:
    if not people:
        return False
    sender_name = str(message.get("senderName", ""))
    sender = str(message.get("sender", ""))
    hay = f"{sender_name}|{sender}"
    return any(p and p in hay for p in people)


def _capture_policy(target: dict[str, Any]) -> str:
    policy = str(target.get("capture_policy", "summary_only"))
    if policy in {"summary_only", "key_events", "hybrid"}:
        return policy
    return "summary_only"


def _should_accept_group_message(target: dict[str, Any] | None, message: dict[str, Any]) -> bool:
    if target is None:
        return True

    group_type = str(target.get("group_type", "info_gap"))
    if group_type == "notification":
        return _is_notification_important(message)

    policy = _capture_policy(target)
    people_raw = target.get("important_people", [])
    important_people = [str(x).strip() for x in people_raw if str(x).strip()] if isinstance(people_raw, list) else []

    if policy == "summary_only":
        return False
    if policy == "key_events":
        return _is_notification_important(message)
    if _hits_important_people(message, important_people):
        return True
    return _is_notification_important(message)


def validate_bash_command(command: str, root: Path) -> tuple[bool, str]:
    if not isinstance(command, str) or not command.strip():
        return False, "Empty Bash command."
    if any(x in command for x in UNSAFE_BASH_TOKENS):
        return False, "Unsafe Bash syntax is not allowed."

    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        return False, "Unable to parse Bash command."
    if not tokens:
        return False, "Empty Bash command."

    cmd_name = tokens[0].lower()
    if cmd_name not in SAFE_BASH_COMMANDS:
        return False, f"Bash command '{tokens[0]}' is not allowed."

    for token in tokens[1:]:
        if not _looks_like_path_token(token):
            continue
        candidate = Path(token.strip().strip("\"'"))
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        workspace = root.resolve()
        if candidate != workspace and workspace not in candidate.parents:
            return False, f"Path denied for Bash: {candidate}"

    return True, "ok"


def should_allow_write_tools(user_prompt: str) -> bool:
    return has_explicit_write_intent(user_prompt)


def should_allow_new_file_creation(user_prompt: str) -> bool:
    return has_explicit_new_file_intent(user_prompt)


def _resolve_tool_path(raw_path: str, root: Path) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def _is_memory_path(path: Path, root: Path) -> bool:
    memory_root = (root / "memory").resolve()
    path = path.resolve()
    return path == memory_root or memory_root in path.parents


def _is_inbox_path(path: Path, root: Path) -> bool:
    inbox_root = (root / "memory" / "00_Inbox").resolve()
    path = path.resolve()
    return path == inbox_root or inbox_root in path.parents


def _is_plan_like_file(path: Path) -> bool:
    name = path.name.lower()
    plan_tokens = (
        "plan",
        "roadmap",
        "itinerary",
        "travel",
        "trip",
        "learning",
        "study",
        "计划",
        "路线",
        "学习",
    )
    return any(token in name for token in plan_tokens)


def _find_similar_plan_files(target: Path, root: Path) -> list[Path]:
    memory_root = (root / "memory").resolve()
    if not memory_root.exists():
        return []
    matches: list[Path] = []
    stem_tokens = [x for x in target.stem.lower().replace("-", "_").split("_") if x]
    for candidate in memory_root.rglob("*.md"):
        if candidate.resolve() == target.resolve():
            continue
        c_name = candidate.name.lower()
        if not _is_plan_like_file(candidate):
            continue
        if any(token and token in c_name for token in stem_tokens):
            matches.append(candidate)
    return matches


def _is_growth_detail_plan_file(path: Path, root: Path) -> bool:
    growth_root = (root / "memory" / "10_Growth").resolve()
    path = path.resolve()
    if not (path == growth_root or growth_root in path.parents):
        return False
    if path.name.lower() == "roadmap_2026.md":
        return False
    return _is_plan_like_file(path)


def _has_roadmap_backlink(content: str) -> bool:
    normalized = content.replace("\\", "/").lower()
    return "memory/10_growth/roadmap_2026.md" in normalized


def validate_memory_write_target(
    *,
    tool_name: str,
    payload: dict[str, Any],
    root: Path,
    allow_new_file: bool,
) -> tuple[bool, str]:
    if tool_name != "Write":
        return True, "ok"
    raw_path = payload.get("file_path") or payload.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return True, "ok"
    target = _resolve_tool_path(raw_path, root)
    if not _is_memory_path(target, root):
        return True, "ok"
    if target.exists():
        return True, "ok"
    if _is_inbox_path(target, root):
        return True, "ok"
    if not _is_plan_like_file(target):
        return True, "ok"

    if not allow_new_file:
        return (
            False,
            "New plan-like memory file is blocked by default. "
            "Update existing file first, or explicitly ask to create a new file.",
        )
    similar_files = _find_similar_plan_files(target, root)
    if similar_files:
        return (
            False,
            "Found similar plan files: "
            + ", ".join(str(x.relative_to(root)) for x in similar_files[:3])
            + ". Please update existing file or confirm creating a separate file.",
        )
    content = payload.get("content")
    if _is_growth_detail_plan_file(target, root):
        if not isinstance(content, str) or not _has_roadmap_backlink(content):
            return (
                False,
                "Growth detail plan must include backlink to "
                "`memory/10_Growth/roadmap_2026.md`.",
            )
    return True, "ok"


async def can_use_tool(
    tool_name: str,
    input_data: dict[str, Any],
    context: dict[str, Any],
) -> Any:
    _ = context
    logger = CURRENT_LOGGER.get()
    payload = input_data or {}

    if logger:
        logger.log_event("permission_check", {"tool_name": tool_name, "input": payload})

    if tool_name in WRITE_TOOLS and not WRITE_TOOLS_ALLOWED.get():
        reason = (
            "Write/Edit/MultiEdit is blocked for this turn. "
            "Ask user to explicitly confirm save/create/update file action first."
        )
        if logger:
            logger.log_event("permission_deny", {"tool_name": tool_name, "reason": reason})
        return PermissionResultDeny(message=reason, interrupt=True)

    ok_write_target, reason_write_target = validate_memory_write_target(
        tool_name=tool_name,
        payload=payload,
        root=WORKSPACE_ROOT,
        allow_new_file=NEW_FILE_ALLOWED.get(),
    )
    if not ok_write_target:
        if logger:
            logger.log_event(
                "permission_deny",
                {"tool_name": tool_name, "reason": reason_write_target},
            )
        return PermissionResultDeny(message=reason_write_target, interrupt=True)

    if tool_name == "Bash":
        command = payload.get("command", "")
        ok, reason = validate_bash_command(str(command), WORKSPACE_ROOT)
        if not ok:
            if logger:
                logger.log_event("permission_deny", {"tool_name": tool_name, "reason": reason})
            return PermissionResultDeny(message=reason, interrupt=True)
        if logger:
            logger.log_event("permission_allow", {"tool_name": tool_name, "policy": "safe_bash_only"})
        return PermissionResultAllow(updated_input=payload)

    if not is_tool_input_within_root(payload, WORKSPACE_ROOT):
        reason = f"Path denied: only files under {WORKSPACE_ROOT} are allowed."
        if logger:
            logger.log_event("permission_deny", {"tool_name": tool_name, "reason": reason})
        return PermissionResultDeny(message=reason, interrupt=True)

    if logger:
        logger.log_event("permission_allow", {"tool_name": tool_name})
    return PermissionResultAllow(updated_input=payload)


async def get_client(force_new: bool = False) -> ClaudeSDKClient:
    global CLIENT
    global STALE_CLEANUP_TASK
    if ClaudeSDKClient is None or ClaudeAgentOptions is None:
        raise HTTPException(
            status_code=500,
            detail="claude-agent-sdk is not installed. Run: pip install claude-agent-sdk",
        )

    if force_new and CLIENT is not None:
        # Keep old client alive to avoid SDK reconnect edge-case crashes.
        # It will be cleaned up by delayed cleanup task.
        STALE_CLIENTS.append(CLIENT)
        CLIENT = None
        if STALE_CLEANUP_TASK is None or STALE_CLEANUP_TASK.done():
            STALE_CLEANUP_TASK = asyncio.create_task(
                schedule_stale_client_cleanup(
                    STALE_CLIENTS,
                    delay_seconds=RUNTIME_CONFIG.stale_client_delay_seconds,
                    sleep_func=asyncio.sleep,
                )
            )

    if CLIENT is not None:
        return CLIENT

    async with CLIENT_INIT_LOCK:
        if CLIENT is None:
            ensure_memory_layout(WORKSPACE_ROOT)
            sdk_env: dict[str, str] = {}
            if RUNTIME_CONFIG.anthropic_base_url:
                sdk_env["ANTHROPIC_BASE_URL"] = RUNTIME_CONFIG.anthropic_base_url
            if RUNTIME_CONFIG.anthropic_auth_token:
                sdk_env["ANTHROPIC_AUTH_TOKEN"] = RUNTIME_CONFIG.anthropic_auth_token
            if RUNTIME_CONFIG.anthropic_api_key:
                sdk_env["ANTHROPIC_API_KEY"] = RUNTIME_CONFIG.anthropic_api_key
            options = ClaudeAgentOptions(
                system_prompt=SYSTEM_PROMPT,
                cwd=str(WORKSPACE_ROOT),
                allowed_tools=ALLOWED_TOOLS,
                can_use_tool=can_use_tool,
                permission_mode=RUNTIME_CONFIG.permission_mode,
                max_turns=RUNTIME_CONFIG.max_turns,
                setting_sources=["project"],
                model=RUNTIME_CONFIG.claude_model or None,
                env=sdk_env,
            )
            client = ClaudeSDKClient(options=options)
            await client.connect()
            CLIENT = client
    return CLIENT


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global CLIENT
    global STALE_CLEANUP_TASK
    global CHATLOG_BACKFILL_TASK
    if CHATLOG_BACKFILL_TASK is not None:
        CHATLOG_BACKFILL_TASK.cancel()
        with suppress(Exception):
            await CHATLOG_BACKFILL_TASK
        CHATLOG_BACKFILL_TASK = None
    if STALE_CLEANUP_TASK is not None:
        STALE_CLEANUP_TASK.cancel()
        with suppress(Exception):
            await STALE_CLEANUP_TASK
        STALE_CLEANUP_TASK = None
    if CLIENT is not None:
        try:
            await CLIENT.disconnect()
        except Exception:
            pass
        CLIENT = None
    for c in STALE_CLIENTS:
        try:
            await c.disconnect()
        except Exception:
            pass
    STALE_CLIENTS.clear()


@app.on_event("startup")
async def on_startup() -> None:
    global CHATLOG_BACKFILL_TASK
    ensure_memory_layout(WORKSPACE_ROOT)
    if (
        RUNTIME_CONFIG.chatlog_enabled
        and RUNTIME_CONFIG.chatlog_base_url
        and RUNTIME_CONFIG.chatlog_monitored_talkers
    ):
        CHATLOG_BACKFILL_TASK = asyncio.create_task(_chatlog_backfill_loop())


async def _chatlog_backfill_loop() -> None:
    while True:
        store = ChatlogStateStore(CHATLOG_STATE_DB)
        target_store = ChatlogTargetStore(CHATLOG_TARGETS_FILE)
        talkers = target_store.enabled_talkers()
        if not talkers:
            await asyncio.sleep(RUNTIME_CONFIG.chatlog_backfill_interval_seconds)
            continue
        report = await asyncio.to_thread(
            run_backfill_once,
            store=store,
            talkers=talkers,
            fetch_messages=lambda talker, from_date, to_date: fetch_chatlog_messages(
                base_url=RUNTIME_CONFIG.chatlog_base_url,
                talker=talker,
                from_date=from_date,
                to_date=to_date,
            ),
            now=datetime.now(timezone.utc),
            bootstrap_days=RUNTIME_CONFIG.chatlog_backfill_bootstrap_days,
            should_accept_message=lambda talker, message: (
                _should_accept_group_message(target_store.get_target(talker), message)
                if talker.endswith("@chatroom")
                else True
            ),
        )
        CHATLOG_RUNTIME["last_backfill_at"] = datetime.now(timezone.utc).isoformat()
        CHATLOG_RUNTIME["last_backfill_report"] = report
        CHATLOG_RUNTIME["backfill_errors_total"] = int(CHATLOG_RUNTIME["backfill_errors_total"]) + int(
            report.get("errors", 0)
        )
        if int(report.get("errors", 0)) > 0:
            CHATLOG_RUNTIME["backfill_consecutive_error_runs"] = int(
                CHATLOG_RUNTIME.get("backfill_consecutive_error_runs", 0)
            ) + 1
        else:
            CHATLOG_RUNTIME["backfill_consecutive_error_runs"] = 0
        if int(report.get("accepted", 0)) > 0:
            _persist_chatlog_note(
                talker="batch_backfill",
                mode="backfill",
                messages=[
                    {
                        "time": CHATLOG_RUNTIME["last_backfill_at"],
                        "sender": "system",
                        "content": (
                            f"accepted={report.get('accepted', 0)}, "
                            f"errors={report.get('errors', 0)}, "
                            f"scanned={report.get('scanned', 0)}"
                        ),
                    }
                ],
                source="chatlog_backfill",
            )
        await asyncio.sleep(RUNTIME_CONFIG.chatlog_backfill_interval_seconds)


async def run_agent(prompt: str, conversation_id: str, force_new_client: bool) -> tuple[str, Path]:
    stripped_prompt = prompt.strip()
    is_slash_command = bool(stripped_prompt) and stripped_prompt.startswith("/") and ("\n" not in stripped_prompt)
    effective_prompt = build_effective_prompt(prompt)
    allow_write_tools = should_allow_write_tools(prompt)
    allow_new_file = should_allow_new_file_creation(prompt)
    if is_slash_command:
        # Keep slash commands intact so Claude CLI can parse them as commands.
        effective_prompt = stripped_prompt
    else:
        memory_ctx = await build_memory_context_async(
            WORKSPACE_ROOT,
            RUNTIME_CONFIG.memory_index_max_entries,
        )
        effective_prompt = (
            f"{effective_prompt}\n\n"
            "以下是从工作区读取到的 memory 索引上下文，请先基于索引判断相关文件，再按需使用 Read 工具读取正文：\n"
            f"{memory_ctx}"
        )
    logger = SessionLogger(log_dir=LOG_DIR)
    logger.log_event(
        "request",
        {
            "prompt": prompt,
            "effective_prompt": effective_prompt,
            "cwd": str(WORKSPACE_ROOT),
            "allowed_tools": ALLOWED_TOOLS,
            "write_tools_allowed": allow_write_tools,
            "new_file_allowed": allow_new_file,
            "conversation_id": conversation_id,
            "force_new_client": force_new_client,
        },
    )

    token = CURRENT_LOGGER.set(logger)
    write_token = WRITE_TOOLS_ALLOWED.set(allow_write_tools)
    new_file_token = NEW_FILE_ALLOWED.set(allow_new_file)
    chunks: list[str] = []
    tool_errors: list[str] = []
    interrupted = False
    compact_applied = False
    result_is_error = False
    result_subtype: str | None = None

    async def _query_and_collect() -> None:
        nonlocal interrupted
        nonlocal compact_applied
        nonlocal result_is_error
        nonlocal result_subtype
        client = await get_client(force_new=force_new_client)
        async with CLIENT_QUERY_LOCK:
            await client.query(effective_prompt, session_id=conversation_id)
            async for message in client.receive_response():
                logger.log_event("message", serialize_message(message))

                if hasattr(message, "content"):
                    for block in getattr(message, "content", []):
                        block_text = _block_text(block)
                        if block_text == "[Request interrupted by user for tool use]":
                            interrupted = True
                        if block_text and _block_is_error(block):
                            tool_errors.append(block_text)

                if AssistantMessage is not None and isinstance(message, AssistantMessage):
                    for block in getattr(message, "content", []):
                        if TextBlock is not None and isinstance(block, TextBlock):
                            chunks.append(block.text)
                        elif hasattr(block, "text"):
                            chunks.append(str(getattr(block, "text")))

                # Avoid duplicate text: many responses include both AssistantMessage text
                # and ResultMessage.result with same content.
                if (
                    hasattr(message, "result")
                    and isinstance(getattr(message, "result"), str)
                    and not chunks
                ):
                    chunks.append(getattr(message, "result"))

                if hasattr(message, "subtype") and isinstance(getattr(message, "subtype"), str):
                    result_subtype = getattr(message, "subtype")
                    if result_subtype == "compact_boundary":
                        compact_applied = True
                if hasattr(message, "is_error") and isinstance(getattr(message, "is_error"), bool):
                    result_is_error = bool(getattr(message, "is_error"))

                if ResultMessage is not None and isinstance(message, ResultMessage):
                    break

    try:
        await asyncio.wait_for(
            _query_and_collect(),
            timeout=RUNTIME_CONFIG.agent_run_timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.log_event(
            "timeout",
            {"timeout_seconds": RUNTIME_CONFIG.agent_run_timeout_seconds},
        )
        return (
            f"执行超时（{RUNTIME_CONFIG.agent_run_timeout_seconds}s），请重试。日志文件：{logger.path}",
            logger.path,
        )
    except asyncio.CancelledError as exc:
        logger.log_event("cancelled", {"error": repr(exc)})
        raise
    except Exception as exc:
        formatted_error = _format_agent_exception(exc)
        logger.log_event("error", {"error": repr(exc), "details": formatted_error})
        return f"Claude Code call failed: {formatted_error}\nLog file: {logger.path}", logger.path
    finally:
        NEW_FILE_ALLOWED.reset(new_file_token)
        WRITE_TOOLS_ALLOWED.reset(write_token)
        CURRENT_LOGGER.reset(token)

    reply = build_reply_text(
        chunks=chunks,
        tool_errors=tool_errors,
        interrupted=interrupted,
        result_is_error=result_is_error,
        result_subtype=result_subtype,
        compact_applied=compact_applied,
        log_path=logger.path,
    )
    logger.log_event("response", {"reply": reply})
    return reply, logger.path


async def probe_auth_context() -> dict[str, str]:
    client = await get_client(force_new=False)
    api_key_source = "unknown"
    model = ""
    error = ""

    async with CLIENT_QUERY_LOCK:
        await client.query("ping", session_id="auth-probe")
        async for message in client.receive_response():
            subtype = getattr(message, "subtype", "")
            if subtype == "init":
                data = getattr(message, "data", None)
                if isinstance(data, dict):
                    src = data.get("apiKeySource")
                    mdl = data.get("model")
                    if isinstance(src, str) and src.strip():
                        api_key_source = src.strip()
                    if isinstance(mdl, str) and mdl.strip():
                        model = mdl.strip()

            if AssistantMessage is not None and isinstance(message, AssistantMessage):
                payload_error = getattr(message, "error", None)
                if isinstance(payload_error, str) and payload_error.strip():
                    error = payload_error.strip()
                for block in getattr(message, "content", []):
                    text = _block_text(block)
                    if text and "Not logged in" in text:
                        error = "not_logged_in"

            if ResultMessage is not None and isinstance(message, ResultMessage):
                break
            if not model and hasattr(message, "model"):
                maybe_model = getattr(message, "model", "")
                if isinstance(maybe_model, str) and maybe_model.strip():
                    model = maybe_model.strip()

    return {
        "api_key_source": api_key_source,
        "model": model,
        "error": error,
    }


async def build_memory_context_async(root: Path, max_entries: int) -> str:
    return await asyncio.to_thread(build_memory_context, root, max_entries)


def _read_bridge_health() -> dict[str, Any]:
    if not BRIDGE_HEARTBEAT_FILE.exists():
        return {"status": "unknown", "detail": "heartbeat_missing"}

    try:
        data = json.loads(BRIDGE_HEARTBEAT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "unknown", "detail": "heartbeat_unreadable"}

    ts_raw = data.get("ts")
    if not isinstance(ts_raw, str):
        return {"status": "unknown", "detail": "heartbeat_invalid_ts"}

    try:
        ts = datetime.fromisoformat(ts_raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return {"status": "unknown", "detail": "heartbeat_invalid_ts"}

    now = datetime.now(timezone.utc)
    age_seconds = max(0, int((now - ts).total_seconds()))
    status = "ok" if age_seconds <= BRIDGE_HEARTBEAT_STALE_SECONDS else "stale"
    return {
        "status": status,
        "age_seconds": age_seconds,
        "last_heartbeat": ts.isoformat(),
        "event": data.get("event", ""),
        "pid": data.get("pid"),
    }


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    bridge = _read_bridge_health()
    chatlog = _build_chatlog_health()
    overall_status = "degraded" if bridge.get("status") == "stale" else "ok"
    signals = chatlog.get("signals", {})
    if isinstance(signals, dict):
        if bool(signals.get("backfill_error_alert")) or bool(signals.get("webhook_dedup_alert")):
            overall_status = "degraded"
    last_report = chatlog.get("last_backfill_report")
    if isinstance(last_report, dict) and int(last_report.get("errors", 0)) > 0:
        overall_status = "degraded"
    return {
        "status": overall_status,
        "backend": "ok",
        "bridge": bridge,
        "chatlog": chatlog,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    global ACTIVE_CONVERSATION_ID
    session_id, is_new = resolve_session_id(payload.conversation_id, payload.new_conversation)
    force_new_client = False
    if is_new or ACTIVE_CONVERSATION_ID is None:
        force_new_client = True
        ACTIVE_CONVERSATION_ID = session_id
    elif payload.conversation_id and payload.conversation_id != ACTIVE_CONVERSATION_ID:
        force_new_client = True
        ACTIVE_CONVERSATION_ID = session_id

    reply, log_path = await run_agent(payload.message, session_id, force_new_client)
    return ChatResponse(
        reply=reply,
        workspace=str(WORKSPACE_ROOT),
        log_file=str(log_path),
        conversation_id=session_id,
        is_new_session=is_new,
    )


@app.post("/api/memory/capture", response_model=MemoryCaptureResponse)
async def memory_capture(payload: MemoryCaptureRequest) -> MemoryCaptureResponse:
    path = create_inbox_note(
        root=WORKSPACE_ROOT,
        content=payload.content,
        title=payload.title,
        tags=payload.tags,
        source=payload.source,
    )
    return MemoryCaptureResponse(
        path=str(path),
        message="Memory captured to inbox. You can later route it into 10/20/30/40 buckets.",
    )


@app.post("/api/memory/reindex", response_model=MemoryReindexResponse)
async def memory_reindex() -> MemoryReindexResponse:
    path = await asyncio.to_thread(write_memory_index, WORKSPACE_ROOT)
    return MemoryReindexResponse(path=str(path), message="记忆索引已重建。")


@app.post("/api/integrations/chatlog/webhook", response_model=ChatlogWebhookResponse)
async def chatlog_webhook(
    payload: ChatlogWebhookRequest,
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
) -> ChatlogWebhookResponse:
    if not RUNTIME_CONFIG.chatlog_enabled:
        raise HTTPException(status_code=503, detail="Chatlog integration is disabled.")

    expected_token = RUNTIME_CONFIG.chatlog_webhook_token
    if not expected_token:
        raise HTTPException(status_code=500, detail="Chatlog webhook token is not configured.")

    if not x_webhook_token or not hmac.compare_digest(x_webhook_token, expected_token):
        raise HTTPException(status_code=403, detail="Invalid webhook token.")

    target_store = ChatlogTargetStore(CHATLOG_TARGETS_FILE)
    target = target_store.get_target(payload.talker)
    if target is not None and not bool(target.get("enabled", True)):
        return ChatlogWebhookResponse(
            ok=True,
            talker=payload.talker,
            accepted=0,
            mode="group_digest" if payload.talker.endswith("@chatroom") else "contact_realtime",
        )

    store = ChatlogStateStore(CHATLOG_STATE_DB)
    accepted = 0
    deduped = 0
    max_time: str | None = None
    max_seq: int | None = None
    accepted_messages: list[dict[str, Any]] = []
    for message in payload.messages:
        key = _build_idempotency_key(payload.talker, message)
        message_time = message.get("time") if isinstance(message.get("time"), str) else None
        inserted = store.mark_processed(key, payload.talker, message_time)
        if not inserted:
            deduped += 1
            continue

        if payload.talker.endswith("@chatroom") and target is not None:
            if not _should_accept_group_message(target, message):
                deduped += 1
                continue

        accepted += 1
        accepted_messages.append(message)
        seq = _to_int_or_none(message.get("seq"))
        if max_time is None or (message_time and message_time > max_time):
            max_time = message_time
            max_seq = seq
        elif message_time == max_time and seq is not None:
            old = max_seq if max_seq is not None else -1
            if seq > old:
                max_seq = seq

    if accepted > 0:
        store.advance_checkpoint(payload.talker, max_time, max_seq)
        _persist_chatlog_note(
            talker=payload.talker,
            mode="group_digest" if payload.talker.endswith("@chatroom") else "contact_realtime",
            messages=accepted_messages,
            source="chatlog_webhook",
        )

    CHATLOG_RUNTIME["last_webhook_at"] = datetime.now(timezone.utc).isoformat()
    CHATLOG_RUNTIME["webhook_accepted_total"] = int(CHATLOG_RUNTIME["webhook_accepted_total"]) + accepted
    CHATLOG_RUNTIME["webhook_deduped_total"] = int(CHATLOG_RUNTIME["webhook_deduped_total"]) + deduped

    mode = "group_digest" if payload.talker.endswith("@chatroom") else "contact_realtime"
    return ChatlogWebhookResponse(
        ok=True,
        talker=payload.talker,
        accepted=accepted,
        mode=mode,
    )


@app.get("/api/integrations/chatlog/targets")
async def list_chatlog_targets() -> dict[str, Any]:
    store = ChatlogTargetStore(CHATLOG_TARGETS_FILE)
    return {"items": store.list_targets()}


@app.post("/api/integrations/chatlog/targets/upsert")
async def upsert_chatlog_target(payload: ChatlogTargetUpsertRequest) -> dict[str, Any]:
    store = ChatlogTargetStore(CHATLOG_TARGETS_FILE)
    item = store.upsert_target(
        payload.talker,
        {
            "enabled": payload.enabled,
            "group_type": payload.group_type,
            "importance": payload.importance,
            "default_memory_bucket": payload.default_memory_bucket,
            "focus_topics": payload.focus_topics,
            "important_people": payload.important_people,
            "noise_tolerance": payload.noise_tolerance,
            "capture_policy": payload.capture_policy,
        },
    )
    return {"item": item}


@app.delete("/api/integrations/chatlog/targets/{talker}")
async def remove_chatlog_target(talker: str) -> dict[str, Any]:
    store = ChatlogTargetStore(CHATLOG_TARGETS_FILE)
    removed = store.remove_target(talker)
    return {"removed": removed}

