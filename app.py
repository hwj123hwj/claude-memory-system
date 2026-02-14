from __future__ import annotations

import asyncio
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
from memory_context import build_memory_context, is_memory_query
from memory_stage1 import create_inbox_note, ensure_memory_layout
from prompt_builder import build_effective_prompt

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
        if logger:
            logger.log_event("permission_deny", {"tool_name": tool_name, "reason": "bash_disabled"})
        return PermissionResultDeny(message="Bash is disabled for this web agent.", interrupt=True)

    if not is_tool_input_within_root(payload, WORKSPACE_ROOT):
        reason = f"Path denied: only files under {WORKSPACE_ROOT} are allowed."
        if logger:
            logger.log_event("permission_deny", {"tool_name": tool_name, "reason": reason})
        return PermissionResultDeny(message=reason, interrupt=True)

    if logger:
        logger.log_event("permission_allow", {"tool_name": tool_name})
    return PermissionResultAllow(updated_input=payload)


async def get_client() -> ClaudeSDKClient:
    global CLIENT
    if ClaudeSDKClient is None or ClaudeAgentOptions is None:
        raise HTTPException(
            status_code=500,
            detail="claude-agent-sdk is not installed. Run: pip install claude-agent-sdk",
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
                max_turns=30,
            )
            client = ClaudeSDKClient(options=options)
            await client.connect()
            CLIENT = client
    return CLIENT


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global CLIENT
    if CLIENT is not None:
        await CLIENT.disconnect()
        CLIENT = None


@app.on_event("startup")
async def on_startup() -> None:
    ensure_memory_layout(WORKSPACE_ROOT)


async def run_agent(prompt: str, session_id: str) -> tuple[str, Path]:
    effective_prompt = build_effective_prompt(prompt)
    if is_memory_query(prompt):
        memory_ctx = build_memory_context(WORKSPACE_ROOT)
        effective_prompt = (
            f"{effective_prompt}\n\n"
            "以下是已从工作区读取到的 memory 文件上下文，请基于这些内容给出“个人记忆概要”：\n"
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
            "session_id": session_id,
        },
    )

    token = CURRENT_LOGGER.set(logger)
    chunks: list[str] = []

    try:
        client = await get_client()
        async with CLIENT_QUERY_LOCK:
            await client.query(effective_prompt, session_id=session_id)
            async for message in client.receive_response():
                logger.log_event("message", serialize_message(message))

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

                if ResultMessage is not None and isinstance(message, ResultMessage):
                    break

    except Exception as exc:
        logger.log_event("error", {"error": repr(exc)})
        return f"调用 Claude Code 失败：{exc}\n日志文件：{logger.path}", logger.path
    finally:
        CURRENT_LOGGER.reset(token)

    reply = "\n".join(x for x in chunks if x and x.strip()).strip()
    if not reply:
        reply = f"已完成请求，但没有可显示的文本输出。日志文件：{logger.path}"
    logger.log_event("response", {"reply": reply})
    return reply, logger.path


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    session_id, is_new = resolve_session_id(payload.conversation_id, payload.new_conversation)
    reply, log_path = await run_agent(payload.message, session_id)
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
