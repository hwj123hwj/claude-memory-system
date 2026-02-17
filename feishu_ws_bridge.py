from __future__ import annotations

import asyncio
import json
import logging
import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from app import run_agent
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
            conversation_id = f"feishu:{chat_id}"
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
