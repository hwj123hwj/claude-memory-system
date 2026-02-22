from __future__ import annotations

import asyncio
import json
import logging
import os
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from app import run_agent
from chatlog_targets import ChatlogTargetStore
from runtime_config import load_runtime_config

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
        P2ImMessageReceiveV1,
    )

    FEISHU_AVAILABLE = True
except Exception:  # pragma: no cover
    lark = None
    CreateMessageRequest = None
    CreateMessageRequestBody = None
    P2ImMessageReceiveV1 = None
    FEISHU_AVAILABLE = False


WORKSPACE_ROOT = Path(__file__).resolve().parent
LOG_DIR = WORKSPACE_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
HEARTBEAT_FILE = LOG_DIR / "feishu_bridge_heartbeat.json"
CHATLOG_TARGETS_FILE = LOG_DIR / "chatlog_targets.json"
CHAT_SESSION_STATE_FILE = LOG_DIR / "feishu_chat_sessions.json"

_logger = logging.getLogger("feishu_ws_bridge")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.FileHandler(LOG_DIR / "feishu_ws_bridge.log", encoding="utf-8")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    _logger.addHandler(fh)
    _logger.addHandler(sh)


def _write_bridge_heartbeat(event: str, chat_id: str = "") -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "chat_id": chat_id,
        "pid": os.getpid(),
    }
    HEARTBEAT_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _sanitize_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    normalized = unicodedata.normalize("NFC", text)
    cleaned = normalized.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return "".join(ch for ch in cleaned if ch in {"\n", "\t"} or ord(ch) >= 32)


def _parse_text_content(raw: str) -> str:
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _sanitize_text(raw).strip()
    if isinstance(data, dict) and isinstance(data.get("text"), str):
        return _sanitize_text(data["text"]).strip()
    return _sanitize_text(raw).strip()


def _normalize_outgoing_text(text: str) -> str:
    return _sanitize_text(text)


def _latest_slash_commands_from_logs(max_files: int = 50) -> list[str]:
    files = sorted(LOG_DIR.glob("chat-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:max_files]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if row.get("event") != "message" or row.get("type") != "SystemMessage":
                continue
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("subtype") != "init":
                continue
            data = payload.get("data")
            if not isinstance(data, dict):
                continue
            slash = data.get("slash_commands")
            if isinstance(slash, list):
                cleaned = [str(x).strip() for x in slash if str(x).strip()]
                if cleaned:
                    return cleaned
    return []


def _resolve_chat_conversation_id(chat_id: str) -> str:
    state = _load_chat_session_state()
    generation = int(state.get(chat_id, 0))
    return f"feishu:{chat_id}:v{generation}"


def _load_chat_session_state() -> dict[str, int]:
    if not CHAT_SESSION_STATE_FILE.exists():
        return {}
    try:
        raw = json.loads(CHAT_SESSION_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in raw.items():
        if not isinstance(k, str):
            continue
        try:
            out[k] = max(0, int(v))
        except (TypeError, ValueError):
            continue
    return out


def _save_chat_session_state(state: dict[str, int]) -> None:
    CHAT_SESSION_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _clear_chat_session(chat_id: str) -> str:
    state = _load_chat_session_state()
    current = int(state.get(chat_id, 0))
    state[chat_id] = current + 1
    _save_chat_session_state(state)
    return f"feishu:{chat_id}:v{state[chat_id]}"


def handle_session_command(text: str, chat_id: str) -> str | None:
    normalized = text.strip().lower()
    if normalized == "/status commands":
        slash = _latest_slash_commands_from_logs()
        if not slash:
            return "未发现可用 slash_commands（尚未捕获 init 消息）。"
        lines = ["当前可用 slash_commands："]
        lines.extend([f"- /{x}" for x in slash])
        return "\n".join(lines)
    if normalized == "/clear":
        next_conversation_id = _clear_chat_session(chat_id)
        return f"会话已清空，后续将使用新会话：{next_conversation_id}"
    return None


def _parse_kv_args(parts: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in parts:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _extract_reply_suggest_target(text: str) -> str | None:
    normalized = text.strip()
    prefix = "/reply suggest"
    if not normalized.startswith(prefix):
        return None
    tail = normalized[len(prefix) :].strip()
    return tail or ""


def _parse_reply_suggest_request(text: str) -> tuple[str | None, str, dict[str, str]]:
    tail = _extract_reply_suggest_target(text)
    if tail is None:
        return None, "full", {}
    if tail == "":
        return "", "full", {}

    options: dict[str, str] = {}
    target_parts: list[str] = []
    for token in tail.split():
        if "=" in token:
            k, v = token.split("=", 1)
            if k.strip().lower() in {"mode"}:
                options[k.strip().lower()] = v.strip()
                continue
        target_parts.append(token)

    target = " ".join(target_parts).strip()
    mode_raw = options.get("mode", "full").lower()
    mode = "lite" if mode_raw == "lite" else "full"
    return target, mode, options


def _http_get_json(url: str, timeout_seconds: int = 20) -> object:
    with urlopen(url, timeout=timeout_seconds) as resp:  # noqa: S310
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def _looks_like_contact_talker(target: str) -> bool:
    if not target:
        return False
    return target.startswith("wxid_") or target.startswith("v3_")


def _resolve_reply_target(base_url: str, target: str) -> tuple[str, str] | None:
    value = target.strip()
    if not value:
        return None
    if _looks_like_contact_talker(value):
        return value, value

    url = f"{base_url.rstrip('/')}/api/v1/contact?format=json"
    data = _http_get_json(url)
    items: list[object]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and isinstance(data.get("items"), list):
        items = data.get("items", [])
    else:
        return None

    keyword = value.lower()
    for item in items:
        if not isinstance(item, dict):
            continue
        talker = ""
        for key in ("wxid", "userName", "username", "user_name", "id", "talker"):
            if isinstance(item.get(key), str) and str(item.get(key)).strip():
                talker = str(item.get(key)).strip()
                break
        if not talker:
            continue
        candidates: list[str] = []
        for key in ("remark", "nickname", "nickName", "name", "displayName", "userName"):
            raw = item.get(key)
            if isinstance(raw, str) and raw.strip():
                candidates.append(raw.strip())
        hay = " | ".join(candidates).lower()
        if keyword in hay:
            display = candidates[0] if candidates else talker
            return talker, display
    return None


def _fetch_recent_contact_messages(base_url: str, talker: str) -> list[dict[str, str | bool]]:
    now = datetime.now(timezone.utc)
    windows = (3, 30, 365)
    for days in windows:
        from_date = (now - timedelta(days=days)).date().isoformat()
        to_date = now.date().isoformat()
        date_range = f"{from_date}~{to_date}"
        query = urlencode({"talker": talker, "time": date_range, "format": "json"})
        url = f"{base_url.rstrip('/')}/api/v1/chatlog?{query}"
        data = _http_get_json(url)
        items: list[dict[str, object]] = []
        if isinstance(data, list):
            items = [x for x in data if isinstance(x, dict)]
        elif isinstance(data, dict) and isinstance(data.get("items"), list):
            items = [x for x in data.get("items", []) if isinstance(x, dict)]
        if not items:
            continue

        out: list[dict[str, str | bool]] = []
        for message in items:
            content = str(message.get("content", "")).strip()
            if not content:
                continue
            sender = str(message.get("senderName", "") or message.get("sender", "")).strip()
            msg_time = str(message.get("time", "")).strip()
            out.append(
                {
                    "content": content,
                    "sender": sender,
                    "time": msg_time,
                    "is_self": bool(message.get("isSelf", False)),
                }
            )
        if out:
            return out[-20:]
    return []


def _pick_latest_contact_side_message(messages: list[dict[str, str | bool]]) -> dict[str, str | bool] | None:
    for message in reversed(messages):
        if not bool(message.get("is_self", False)):
            return message
    return messages[-1] if messages else None


def _clean_reply_suggestion_text(raw: str) -> str:
    text = raw.strip()
    markers = ("### 对方意图", "## 对方意图", "对方意图", "### 建议回复", "## 建议回复")
    starts = [text.find(m) for m in markers if text.find(m) >= 0]
    if starts:
        text = text[min(starts) :].strip()

    blocked = ("我先", "我需要先", "让我先", "我将先", "找到相关", "memory 中", "内存中")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    cleaned: list[str] = []
    for ln in lines:
        if any(b in ln for b in blocked):
            continue
        cleaned.append(ln)

    text = "\n".join(cleaned).strip() or raw.strip()

    if "### 超短回复(15-30字)" not in text:
        short_line = "先确认你是认真考虑，还是在吐槽这个方案。"
        rows = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for i, row in enumerate(rows):
            if "建议回复" in row:
                for j in range(i + 1, len(rows)):
                    if rows[j].startswith("###"):
                        break
                    short_line = rows[j][:30]
                    break
                break
        text += f"\n\n### 超短回复(15-30字)\n{short_line}"

    if "### 需要确认的问题" in text:
        text = text.replace("\n无\n", "\n1. 你是认真考虑这个方案，还是在吐槽它的性价比？\n")
        text = text.replace("\n无。", "\n1. 你是认真考虑这个方案，还是在吐槽它的性价比？")

    return text


def _extract_markdown_section(text: str, keyword: str) -> str:
    lines = text.splitlines()
    start = -1
    for i, line in enumerate(lines):
        if keyword in line:
            start = i
            break
    if start < 0:
        return ""
    out: list[str] = [lines[start]]
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("### "):
            break
        out.append(lines[i])
    return "\n".join(x for x in out if x.strip()).strip()


def _to_lite_reply(text: str) -> str:
    main = _extract_markdown_section(text, "建议回复")
    short = _extract_markdown_section(text, "超短回复")
    parts = [x for x in (main, short) if x]
    if parts:
        return "\n\n".join(parts)
    return text


def _load_contact_memory_snippets(display_name: str, talker: str, max_items: int = 3) -> list[str]:
    base = WORKSPACE_ROOT / "memory" / "20_Connections"
    if not base.exists():
        return []

    candidates = [display_name.strip(), talker.strip()]
    snippets: list[str] = []
    files = sorted(base.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:300]:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if not any(k and k in text for k in candidates):
            continue
        lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        if not lines:
            continue
        snippet = lines[0][:160]
        snippets.append(f"- {snippet}")
        if len(snippets) >= max_items:
            break
    return snippets


def _load_contact_reply_style(talker: str) -> str:
    store = ChatlogTargetStore(CHATLOG_TARGETS_FILE)
    item = store.get_target(talker)
    if not isinstance(item, dict):
        return ""
    lines: list[str] = []
    for key in ("reply_style", "relationship_note", "etiquette_preferences", "tone_preference"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            lines.append(f"- {key}: {val.strip()}")
    return "\n".join(lines)


def _build_reply_suggest_prompt(
    display_name: str,
    talker: str,
    latest_message: dict[str, str | bool],
    context_messages: list[dict[str, str | bool]],
    memory_snippets: list[str],
    reply_style_profile: str,
    output_mode: str,
) -> str:
    context_lines: list[str] = []
    for msg in context_messages[-10:]:
        who = "我" if bool(msg.get("is_self", False)) else "对方"
        content = str(msg.get("content", ""))
        context_lines.append(f"[{who}] {content}")
    context_block = "\n".join(context_lines)
    memory_block = "\n".join(memory_snippets) if memory_snippets else "- 暂无联系人记忆"
    style_block = reply_style_profile if reply_style_profile else "- 暂无显式风格配置"

    return (
        "你是聊天回复助手。请基于最近多轮对话，不要只看单条消息。\n"
        f"联系人: {display_name} ({talker})\n"
        f"对方最新消息: {latest_message.get('content', '')}\n"
        f"消息时间: {latest_message.get('time', '')}\n"
        "最近对话摘录(双方近10条):\n"
        f"{context_block}\n\n"
        "联系人记忆摘要:\n"
        f"{memory_block}\n\n"
        "联系人沟通风格偏好:\n"
        f"{style_block}\n\n"
        f"输出模式: {output_mode}\n"
        "只输出最终结果，不要输出过程话术（例如“我先搜索/让我查看”）。\n"
        "严格按以下结构输出:\n"
        "### 对方意图\n"
        "...\n\n"
        "### 建议回复(可直接发, 30-80字)\n"
        "...\n\n"
        "### 备选回复(更温和)\n"
        "...\n\n"
        "### 超短回复(15-30字)\n"
        "...\n\n"
        "### 需要确认的问题\n"
        "1. ...\n"
        "至少给1条，不允许写“无”。\n"
    )


async def handle_reply_suggest_command(
    text: str,
    *,
    chat_id: str,
    agent_timeout_seconds: int,
) -> str | None:
    target, output_mode, _ = _parse_reply_suggest_request(text)
    if target is None:
        return None
    if target == "":
        return "用法: /reply suggest <联系人昵称或wxid>"

    cfg = load_runtime_config(WORKSPACE_ROOT / ".env")
    if not cfg.chatlog_enabled or not cfg.chatlog_base_url:
        return "chatlog 未启用，无法生成回复建议。"

    resolved = await asyncio.to_thread(_resolve_reply_target, cfg.chatlog_base_url, target)
    if not resolved:
        return f"未找到联系人: {target}"
    talker, display_name = resolved
    if talker.endswith("@chatroom"):
        return "当前仅支持联系人回复建议，不支持群聊。"

    recent_messages = await asyncio.to_thread(_fetch_recent_contact_messages, cfg.chatlog_base_url, talker)
    latest_message = _pick_latest_contact_side_message(recent_messages)
    if not latest_message:
        return f"未找到 {display_name} 的最近聊天消息。"
    if bool(latest_message.get("is_self", False)):
        return (
            f"{display_name} 最近可用消息是你自己发出的，暂无对方新消息。\n"
            f"你最近发送: {latest_message.get('content', '')}\n"
            "请等待对方新消息后再试。"
        )

    memory_snippets = await asyncio.to_thread(_load_contact_memory_snippets, display_name, talker)
    reply_style_profile = await asyncio.to_thread(_load_contact_reply_style, talker)
    prompt = _build_reply_suggest_prompt(
        display_name,
        talker,
        latest_message,
        recent_messages,
        memory_snippets,
        reply_style_profile,
        output_mode,
    )
    conversation_id = _resolve_chat_conversation_id(chat_id)
    reply, _ = await asyncio.wait_for(
        run_agent(prompt, conversation_id, False),
        timeout=agent_timeout_seconds,
    )
    cleaned_reply = _clean_reply_suggestion_text(reply)
    if output_mode == "lite":
        cleaned_reply = _to_lite_reply(cleaned_reply)
    return (
        f"回复建议对象: {display_name} ({talker})\n"
        "最近消息发送方: 对方\n"
        f"对方最新消息: {latest_message.get('content', '')}\n\n"
        f"{cleaned_reply}\n\n"
        "提示: 这是建议草稿，不会自动发送。"
    )


def handle_memory_group_command(text: str) -> str | None:
    normalized = text.strip()
    if not normalized.startswith("/memory group"):
        return None

    parts = normalized.split()
    if len(parts) < 3:
        return "命令格式错误。示例：/memory group list"

    store = ChatlogTargetStore(CHATLOG_TARGETS_FILE)
    action = parts[2].lower()

    if action == "list":
        items = store.list_targets()
        if not items:
            return "当前没有已配置的群/联系人。"
        lines = ["已配置对象："]
        for it in items:
            lines.append(
                f"- {it.get('talker')} type={it.get('group_type')} enabled={it.get('enabled')} importance={it.get('importance')}"
            )
        return "\n".join(lines)

    if action == "show" and len(parts) >= 4:
        talker = parts[3]
        item = store.get_target(talker)
        if not item:
            return f"未找到配置：{talker}"
        return json.dumps(item, ensure_ascii=False, indent=2)

    if action in {"add", "update"} and len(parts) >= 4:
        talker = parts[3]
        kv = _parse_kv_args(parts[4:])
        updates: dict[str, object] = {}
        if "type" in kv:
            updates["group_type"] = kv["type"]
        if "importance" in kv:
            try:
                updates["importance"] = int(kv["importance"])
            except ValueError:
                pass
        if "bucket" in kv:
            updates["default_memory_bucket"] = kv["bucket"]
        if "enabled" in kv:
            updates["enabled"] = kv["enabled"].lower() in {"1", "true", "yes", "on"}
        if "topics" in kv:
            updates["focus_topics"] = [x for x in kv["topics"].split(",") if x]
        if "policy" in kv:
            updates["capture_policy"] = kv["policy"]
        if "capture_policy" in kv:
            updates["capture_policy"] = kv["capture_policy"]
        if "noise" in kv:
            updates["noise_tolerance"] = kv["noise"]
        if "noise_tolerance" in kv:
            updates["noise_tolerance"] = kv["noise_tolerance"]
        if "reply_style" in kv:
            updates["reply_style"] = kv["reply_style"]
        if "relationship_note" in kv:
            updates["relationship_note"] = kv["relationship_note"]
        if "etiquette_preferences" in kv:
            updates["etiquette_preferences"] = kv["etiquette_preferences"]
        if "tone_preference" in kv:
            updates["tone_preference"] = kv["tone_preference"]
        item = store.upsert_target(talker, updates)
        return f"已更新：{item.get('talker')} type={item.get('group_type')} bucket={item.get('default_memory_bucket')}"

    if action == "people" and len(parts) >= 5:
        talker = parts[3]
        sub = parts[4].lower()
        item = store.get_target(talker)
        if not item:
            item = store.upsert_target(talker, {})
        current = item.get("important_people", [])
        if not isinstance(current, list):
            current = []
        existing = [str(x) for x in current if str(x).strip()]

        if sub == "show":
            if not existing:
                return f"{talker} 当前没有 important_people。"
            return f"{talker} important_people: {', '.join(existing)}"

        if len(parts) < 6:
            return "people 命令格式错误。示例：/memory group people <talker> add 张三,李四"
        raw_people = " ".join(parts[5:])
        people = [x.strip() for x in raw_people.split(",") if x.strip()]
        if not people:
            return "未提供有效人员列表。"

        if sub == "add":
            merged = existing[:]
            for p in people:
                if p not in merged:
                    merged.append(p)
        elif sub == "remove":
            remove_set = set(people)
            merged = [x for x in existing if x not in remove_set]
        elif sub == "set":
            merged = people
        else:
            return "不支持的 people 子命令。支持：add/remove/set/show"

        updated = store.upsert_target(talker, {"important_people": merged})
        return f"已更新：{talker} important_people={', '.join(updated.get('important_people', []))}"

    if action in {"remove", "delete"} and len(parts) >= 4:
        talker = parts[3]
        ok = store.remove_target(talker)
        return f"已删除：{talker}" if ok else f"未找到：{talker}"

    return "不支持的命令。支持：list/show/add/update/remove"


def _split_sentences(text: str) -> list[str]:
    boundaries = {"。", "！", "？", "!", "?", ";", "；", ".", "\n"}
    parts: list[str] = []
    current: list[str] = []
    for ch in text:
        current.append(ch)
        if ch in boundaries:
            sentence = "".join(current).strip()
            if sentence:
                parts.append(sentence)
            current = []
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _split_block_semantic(block: str, max_chars: int) -> list[str]:
    if len(block) <= max_chars:
        return [block]

    chunks: list[str] = []
    current = ""
    for sentence in _split_sentences(block):
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(sentence), max_chars):
                piece = sentence[i : i + max_chars].strip()
                if piece:
                    chunks.append(piece)
            continue

        if not current:
            current = sentence
            continue
        candidate = f"{current}{sentence}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)
    return chunks


def _split_text_for_feishu(text: str, max_chars: int) -> list[str]:
    normalized = _normalize_outgoing_text(text).strip()
    if max_chars <= 0:
        max_chars = 1500
    if not normalized:
        return [""]
    if len(normalized) <= max_chars:
        return [normalized]

    parts: list[str] = []
    current = ""
    paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
    for paragraph in paragraphs:
        paragraph_chunks = _split_block_semantic(paragraph, max_chars)
        for idx, piece in enumerate(paragraph_chunks):
            if not current:
                current = piece
                continue
            sep = "\n\n" if idx == 0 else "\n"
            candidate = f"{current}{sep}{piece}"
            if len(candidate) <= max_chars:
                current = candidate
            else:
                parts.append(current)
                current = piece

    if current:
        parts.append(current)
    return parts


class FeishuWSBridge:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        encrypt_key: str = "",
        verification_token: str = "",
        agent_timeout_seconds: int = 120,
        max_reply_chars: int = 1500,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.encrypt_key = encrypt_key
        self.verification_token = verification_token
        self.agent_timeout_seconds = max(1, int(agent_timeout_seconds))
        self.max_reply_chars = max(1, int(max_reply_chars))
        self._chat_locks: dict[str, asyncio.Lock] = {}
        self._chat_locks_guard = asyncio.Lock()
        self._client = None
        self._ws_client = None

    def _send_text_once(self, chat_id: str, text: str) -> None:
        _write_bridge_heartbeat("send_start", chat_id)
        _logger.info("send -> chat_id=%s text=%s", chat_id, text[:200])
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        resp = self._client.im.v1.message.create(request)
        _logger.info("send <- chat_id=%s code=%s", chat_id, getattr(resp, "code", None))
        _write_bridge_heartbeat("send_ok", chat_id)

    def _send_text(self, chat_id: str, text: str) -> None:
        chunks = _split_text_for_feishu(text, self.max_reply_chars)
        for chunk in chunks:
            self._send_text_once(chat_id, chunk)

    async def _handle_text_async(self, chat_id: str, text: str) -> None:
        try:
            session_reply = handle_session_command(text, chat_id)
            if session_reply is not None:
                self._send_text(chat_id, session_reply)
                return
            command_reply = handle_memory_group_command(text)
            if command_reply is not None:
                self._send_text(chat_id, command_reply)
                return
            reply_suggest = await handle_reply_suggest_command(
                text,
                chat_id=chat_id,
                agent_timeout_seconds=self.agent_timeout_seconds,
            )
            if reply_suggest is not None:
                self._send_text(chat_id, reply_suggest)
                return
            conversation_id = _resolve_chat_conversation_id(chat_id)
            try:
                reply, log_path = await asyncio.wait_for(
                    run_agent(text, conversation_id, False),
                    timeout=self.agent_timeout_seconds,
                )
            except asyncio.TimeoutError:
                _logger.warning(
                    "agent timeout chat_id=%s after %ss, retry with new client",
                    chat_id,
                    self.agent_timeout_seconds,
                )
                _write_bridge_heartbeat("agent_timeout_retry", chat_id)
                reply, log_path = await asyncio.wait_for(
                    run_agent(text, conversation_id, True),
                    timeout=self.agent_timeout_seconds,
                )
            _logger.info("agent <- chat_id=%s log=%s", chat_id, log_path)
            _write_bridge_heartbeat("agent_ok", chat_id)
            self._send_text(chat_id, reply)
        except Exception as exc:
            _logger.exception("handle_text_async error chat_id=%s: %s", chat_id, exc)
            _write_bridge_heartbeat("agent_error", chat_id)
            try:
                self._send_text(chat_id, f"处理失败：{exc}")
            except Exception:
                _logger.exception("failed to send error message chat_id=%s", chat_id)

    async def _get_chat_lock(self, chat_id: str) -> asyncio.Lock:
        async with self._chat_locks_guard:
            lock = self._chat_locks.get(chat_id)
            if lock is None:
                lock = asyncio.Lock()
                self._chat_locks[chat_id] = lock
            return lock

    async def _handle_text_serialized(self, chat_id: str, text: str) -> None:
        lock = await self._get_chat_lock(chat_id)
        async with lock:
            await self._handle_text_async(chat_id, text)

    def _event_handler(self, data) -> None:  # type: ignore[no-untyped-def]
        try:
            if P2ImMessageReceiveV1 is None or not isinstance(data, P2ImMessageReceiveV1):
                _logger.warning("recv <- unexpected event type=%s", type(data))
                return
            event = data.event
            message = event.message if event else None
            sender = event.sender if event else None
            if sender and getattr(sender, "sender_type", None) == "bot":
                return
            if not message:
                return
            chat_id = message.chat_id
            message_type = message.message_type
            content = _parse_text_content(message.content or "") if message_type == "text" else ""
            _logger.info("recv <- chat_id=%s type=%s content=%s", chat_id, message_type, content[:200])
            if message_type != "text" or not chat_id or not content:
                return
            _write_bridge_heartbeat("recv_text", chat_id)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                loop.create_task(self._handle_text_serialized(chat_id, content))
            else:
                asyncio.run(self._handle_text_serialized(chat_id, content))
        except Exception as exc:
            _logger.exception("event_handler error: %s", exc)
            _write_bridge_heartbeat("event_handler_error")

    def start(self) -> None:
        if not FEISHU_AVAILABLE:
            raise SystemExit("lark-oapi not installed. Run: pip install lark-oapi")

        self._client = (
            lark.Client.builder()
            .app_id(self.app_id)
            .app_secret(self.app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        event_handler = (
            lark.EventDispatcherHandler.builder(self.encrypt_key, self.verification_token)
            .register_p2_im_message_receive_v1(self._event_handler)
            .build()
        )
        self._ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )
        _logger.info("websocket client started")
        _write_bridge_heartbeat("started")
        self._ws_client.start()


def main() -> None:
    cfg = load_runtime_config(WORKSPACE_ROOT / ".env")
    if not cfg.feishu_app_id or not cfg.feishu_app_secret:
        raise SystemExit("Missing FEISHU_APP_ID or FEISHU_APP_SECRET in .env")
    bridge = FeishuWSBridge(
        app_id=cfg.feishu_app_id,
        app_secret=cfg.feishu_app_secret,
        encrypt_key=cfg.feishu_encrypt_key,
        verification_token=cfg.feishu_verification_token,
        agent_timeout_seconds=cfg.feishu_agent_timeout_seconds,
        max_reply_chars=cfg.feishu_max_reply_chars,
    )
    bridge.start()


if __name__ == "__main__":
    main()




