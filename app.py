from __future__ import annotations

import asyncio
import shlex
from contextlib import suppress
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_security import is_tool_input_within_root
from chat_logging import SessionLogger, serialize_message
from conversation_session import resolve_session_id
from memory_context import build_memory_context
from memory_index import write_memory_index
from memory_stage1 import create_inbox_note, ensure_memory_layout
from prompt_builder import build_effective_prompt
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
RUNTIME_CONFIG = load_runtime_config(WORKSPACE_ROOT / ".env")

ALLOWED_TOOLS = ["Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "LS"]

SYSTEM_PROMPT = (
    "You are a file assistant. You can only read or write files inside the current workspace. "
    "Never access paths outside workspace. Keep responses concise. "
    "If user asks about memory system or personal memory summary, inspect files under memory first."
)

app = FastAPI(title="Claude Code Web Agent")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

CURRENT_LOGGER: ContextVar[SessionLogger | None] = ContextVar("CURRENT_LOGGER", default=None)
CLIENT: ClaudeSDKClient | None = None
ACTIVE_CONVERSATION_ID: str | None = None
STALE_CLIENTS: list[ClaudeSDKClient] = []
STALE_CLEANUP_TASK: asyncio.Task | None = None
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
    log_path: Path,
) -> str:
    reply = "\n".join(x for x in chunks if x and x.strip()).strip()
    if reply:
        return reply

    if tool_errors:
        return f"执行失败：{tool_errors[-1]}\n日志文件：{log_path}"

    if interrupted or result_is_error or result_subtype == "error_during_execution":
        return f"执行中断，未产生可显示文本输出。日志文件：{log_path}"

    return f"已完成请求，但没有可显示的文本输出。日志文件：{log_path}"


def _looks_like_path_token(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    token = token.strip().strip("\"'")
    if not token:
        return False
    return ("\\" in token) or ("/" in token) or ("." in Path(token).name)


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
            options = ClaudeAgentOptions(
                system_prompt=SYSTEM_PROMPT,
                cwd=str(WORKSPACE_ROOT),
                allowed_tools=ALLOWED_TOOLS,
                can_use_tool=can_use_tool,
                permission_mode="default",
                max_turns=RUNTIME_CONFIG.max_turns,
                setting_sources=["project"],
            )
            client = ClaudeSDKClient(options=options)
            await client.connect()
            CLIENT = client
    return CLIENT


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global CLIENT
    global STALE_CLEANUP_TASK
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
    ensure_memory_layout(WORKSPACE_ROOT)


async def run_agent(prompt: str, conversation_id: str, force_new_client: bool) -> tuple[str, Path]:
    effective_prompt = build_effective_prompt(prompt)
    memory_ctx = await build_memory_context_async(
        WORKSPACE_ROOT,
        RUNTIME_CONFIG.memory_index_max_entries,
    )
    effective_prompt = (
        f"{effective_prompt}\n\n"
        "以下是已从工作区读取到的 memory 索引上下文，请先基于索引判断相关文件，再按需用 Read 工具读取正文：\n"
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
            "conversation_id": conversation_id,
            "force_new_client": force_new_client,
        },
    )

    token = CURRENT_LOGGER.set(logger)
    chunks: list[str] = []
    tool_errors: list[str] = []
    interrupted = False
    result_is_error = False
    result_subtype: str | None = None

    try:
        client = await get_client(force_new=force_new_client)
        async with CLIENT_QUERY_LOCK:
            await client.query(effective_prompt)
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
                if hasattr(message, "is_error") and isinstance(getattr(message, "is_error"), bool):
                    result_is_error = bool(getattr(message, "is_error"))

                if ResultMessage is not None and isinstance(message, ResultMessage):
                    break

    except Exception as exc:
        logger.log_event("error", {"error": repr(exc)})
        return f"调用 Claude Code 失败：{exc}\n日志文件：{logger.path}", logger.path
    finally:
        CURRENT_LOGGER.reset(token)

    reply = build_reply_text(
        chunks=chunks,
        tool_errors=tool_errors,
        interrupted=interrupted,
        result_is_error=result_is_error,
        result_subtype=result_subtype,
        log_path=logger.path,
    )
    logger.log_event("response", {"reply": reply})
    return reply, logger.path


async def build_memory_context_async(root: Path, max_entries: int) -> str:
    return await asyncio.to_thread(build_memory_context, root, max_entries)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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
        message="记忆已写入 inbox。后续可再归档到 10/20/30/40 分类目录。",
    )


@app.post("/api/memory/reindex", response_model=MemoryReindexResponse)
async def memory_reindex() -> MemoryReindexResponse:
    path = await asyncio.to_thread(write_memory_index, WORKSPACE_ROOT)
    return MemoryReindexResponse(path=str(path), message="记忆索引已重建。")
