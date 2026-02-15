from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request


@dataclass(frozen=True)
class FeishuClient:
    app_id: str
    app_secret: str
    base_url: str = "https://open.feishu.cn/open-apis"

    def _post_json(self, path: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        merged_headers = {"Content-Type": "application/json; charset=utf-8"}
        if headers:
            merged_headers.update(headers)
        req = request.Request(url=url, data=body, headers=merged_headers, method="POST")
        try:
            with request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Feishu HTTP error: {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Feishu network error: {exc.reason}") from exc

        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Feishu response JSON decode error: {raw[:200]}") from exc

    def get_tenant_access_token(self) -> str:
        data = self._post_json(
            "/auth/v3/tenant_access_token/internal",
            {"app_id": self.app_id, "app_secret": self.app_secret},
        )
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu token error: {data}")
        token = data.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError(f"Feishu token missing: {data}")
        return token

    def send_text(self, *, receive_id: str, text: str, receive_id_type: str = "chat_id") -> dict:
        token = self.get_tenant_access_token()
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        data = self._post_json(
            f"/im/v1/messages?receive_id_type={receive_id_type}",
            payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu send message error: {data}")
        return data


def parse_feishu_text_content(content: str) -> str:
    if not isinstance(content, str):
        return ""
    stripped = content.strip()
    if not stripped:
        return ""
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if isinstance(data, dict):
        text = data.get("text", "")
        return text.strip() if isinstance(text, str) else ""
    return stripped
