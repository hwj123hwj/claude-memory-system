from __future__ import annotations

import asyncio
import json
import logging
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


def _parse_text_content(raw: str) -> str:
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip()
    if isinstance(data, dict) and isinstance(data.get("text"), str):
        return data["text"].strip()
    return raw.strip()


class FeishuWSBridge:
    def __init__(self, app_id: str, app_secret: str, encrypt_key: str = "", verification_token: str = "") -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.encrypt_key = encrypt_key
        self.verification_token = verification_token
        self._client = None
        self._ws_client = None

    def _send_text(self, chat_id: str, text: str) -> None:
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

    async def _handle_text_async(self, chat_id: str, text: str) -> None:
        try:
            reply, log_path = await run_agent(text, f"feishu:{chat_id}", False)
            _logger.info("agent <- chat_id=%s log=%s", chat_id, log_path)
            self._send_text(chat_id, reply)
        except Exception as exc:
            _logger.exception("handle_text_async error chat_id=%s: %s", chat_id, exc)
            try:
                self._send_text(chat_id, f"处理失败：{exc}")
            except Exception:
                _logger.exception("failed to send error message chat_id=%s", chat_id)

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

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                loop.create_task(self._handle_text_async(chat_id, content))
            else:
                asyncio.run(self._handle_text_async(chat_id, content))
        except Exception as exc:
            _logger.exception("event_handler error: %s", exc)

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
    )
    bridge.start()


if __name__ == "__main__":
    main()
