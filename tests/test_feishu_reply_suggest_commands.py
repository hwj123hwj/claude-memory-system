import asyncio
from dataclasses import replace

import feishu_ws_bridge as bridge_mod
from runtime_config import RuntimeConfig


def test_handle_reply_suggest_command_usage_when_target_missing() -> None:
    out = asyncio.run(
        bridge_mod.handle_reply_suggest_command(
            "/reply suggest",
            chat_id="oc_chat",
            agent_timeout_seconds=5,
        )
    )
    assert out is not None
    assert "用法" in out


def test_handle_reply_suggest_command_generates_draft(monkeypatch) -> None:
    prompts: list[str] = []

    monkeypatch.setattr(
        bridge_mod,
        "load_runtime_config",
        lambda env_file: replace(  # noqa: ARG005
            RuntimeConfig(),
            chatlog_enabled=True,
            chatlog_base_url="http://127.0.0.1:5030",
        ),
    )
    monkeypatch.setattr(
        bridge_mod,
        "_resolve_reply_target",
        lambda base_url, target: ("wxid_cfz3t4h22px722", "郝睿"),
    )
    monkeypatch.setattr(
        bridge_mod,
        "_fetch_recent_contact_messages",
        lambda base_url, talker: [  # type: ignore[no-untyped-def]
            {"content": "你明天下午有空吗", "sender": "郝睿", "time": "2026-02-18T10:00:00+08:00", "is_self": False}
        ],
    )
    monkeypatch.setattr(bridge_mod, "_load_contact_memory_snippets", lambda display_name, talker: ["- 他重视长期规划"])

    async def fake_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        prompts.append(prompt)
        return "### 对方意图\n确认时间\n\n### 建议回复(可直接发, 30-80字)\n明天下午三点可以。", "logs/mock.jsonl"

    monkeypatch.setattr(bridge_mod, "run_agent", fake_run_agent)

    out = asyncio.run(
        bridge_mod.handle_reply_suggest_command(
            "/reply suggest 郝睿",
            chat_id="oc_chat",
            agent_timeout_seconds=5,
        )
    )
    assert out is not None
    assert "回复建议对象" in out
    assert "你明天下午有空吗" in out
    assert "不会自动发送" in out
    assert prompts and "联系人: 郝睿" in prompts[0]


def test_handle_reply_suggest_command_strips_process_chatter(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge_mod,
        "load_runtime_config",
        lambda env_file: replace(  # noqa: ARG005
            RuntimeConfig(),
            chatlog_enabled=True,
            chatlog_base_url="http://127.0.0.1:5030",
        ),
    )
    monkeypatch.setattr(
        bridge_mod,
        "_resolve_reply_target",
        lambda base_url, target: ("wxid_cfz3t4h22px722", "郝睿"),
    )
    monkeypatch.setattr(
        bridge_mod,
        "_fetch_recent_contact_messages",
        lambda base_url, talker: [  # type: ignore[no-untyped-def]
            {"content": "相当于30w买个户口", "sender": "郝睿", "time": "2026-02-18T10:00:00+08:00", "is_self": False}
        ],
    )
    monkeypatch.setattr(bridge_mod, "_load_contact_memory_snippets", lambda display_name, talker: [])

    async def fake_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        _ = (prompt, conversation_id, force_new_client)
        return (
            "我需要先搜索相关聊天记录。\n"
            "找到相关文件。\n\n"
            "### 对方意图\n"
            "讨论户口成本。\n\n"
            "### 建议回复(可直接发, 40-120字)\n"
            "确实成本不低，你是基于哪个城市政策算出来的？\n",
            "logs/mock.jsonl",
        )

    monkeypatch.setattr(bridge_mod, "run_agent", fake_run_agent)
    out = asyncio.run(
        bridge_mod.handle_reply_suggest_command(
            "/reply suggest 郝睿",
            chat_id="oc_chat",
            agent_timeout_seconds=5,
        )
    )
    assert out is not None
    assert "我需要先搜索" not in out
    assert "找到相关文件" not in out
    assert "对方意图" in out


def test_clean_reply_suggestion_fills_missing_ultra_short_and_questions() -> None:
    raw = (
        "### 对方意图\n"
        "在讨论户口成本。\n\n"
        "### 建议回复(可直接发, 30-80字)\n"
        "这个方案本质是拿违约金换户口，值不值看你的长期规划。\n\n"
        "### 备选回复(更温和)\n"
        "理解，这个选择确实两难。\n\n"
        "### 需要确认的问题\n"
        "无\n"
    )
    out = bridge_mod._clean_reply_suggestion_text(raw)
    assert "### 超短回复(15-30字)" in out
    assert "### 需要确认的问题" in out
    assert "\n无\n" not in out
    assert "1." in out


def test_handle_text_async_routes_reply_suggest_command(monkeypatch) -> None:
    sent: list[str] = []

    async def fake_reply_suggest(text: str, *, chat_id: str, agent_timeout_seconds: int):  # type: ignore[no-untyped-def]
        _ = (text, chat_id, agent_timeout_seconds)
        return "draft-ready"

    async def should_not_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        raise AssertionError("run_agent should not be called for handled reply command")

    monkeypatch.setattr(bridge_mod, "handle_reply_suggest_command", fake_reply_suggest)
    monkeypatch.setattr(bridge_mod, "run_agent", should_not_run_agent)

    bridge = bridge_mod.FeishuWSBridge(app_id="x", app_secret="y", agent_timeout_seconds=3)
    bridge._send_text = lambda chat_id, text: sent.append(text)  # type: ignore[method-assign]

    asyncio.run(bridge._handle_text_async("oc_chat", "/reply suggest 郝睿"))

    assert sent == ["draft-ready"]


def test_resolve_reply_target_supports_dict_items(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge_mod,
        "_http_get_json",
        lambda url: {  # noqa: ARG005
            "items": [
                {
                    "userName": "wxid_cfz3t4h22px722",
                    "remark": "郝睿",
                    "nickName": "Corwin",
                }
            ]
        },
    )
    got = bridge_mod._resolve_reply_target("http://127.0.0.1:5030", "郝睿")
    assert got == ("wxid_cfz3t4h22px722", "郝睿")


def test_fetch_recent_contact_messages_fallback_window(monkeypatch) -> None:
    calls: list[str] = []

    def fake_http_get_json(url: str, timeout_seconds: int = 20):  # type: ignore[no-untyped-def]
        _ = timeout_seconds
        calls.append(url)
        if "time=" in url and "2026-02-15~2026-02-18" in url:
            return []
        return [
            {"time": "2026-02-01T10:00:00+08:00", "content": "older text", "sender": "wxid_a", "senderName": "A"}
        ]

    class FakeDatetime:
        @classmethod
        def now(cls, tz):  # type: ignore[no-untyped-def]
            import datetime as dt

            return dt.datetime(2026, 2, 18, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(bridge_mod, "_http_get_json", fake_http_get_json)
    monkeypatch.setattr(bridge_mod, "datetime", FakeDatetime)
    got = bridge_mod._fetch_recent_contact_messages("http://127.0.0.1:5030", "wxid_x")
    assert got
    assert got[-1]["content"] == "older text"
    assert len(calls) >= 2


def test_pick_latest_contact_side_message_prefers_contact_side() -> None:
    got = bridge_mod._pick_latest_contact_side_message(
        [
            {"content": "my latest", "is_self": True},
            {"content": "contact latest", "is_self": False},
        ]
    )
    assert got is not None
    assert got["content"] == "contact latest"


def test_handle_reply_suggest_command_reports_when_only_self_message(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge_mod,
        "load_runtime_config",
        lambda env_file: replace(  # noqa: ARG005
            RuntimeConfig(),
            chatlog_enabled=True,
            chatlog_base_url="http://127.0.0.1:5030",
        ),
    )
    monkeypatch.setattr(
        bridge_mod,
        "_resolve_reply_target",
        lambda base_url, target: ("wxid_cfz3t4h22px722", "郝睿"),
    )
    monkeypatch.setattr(
        bridge_mod,
        "_fetch_recent_contact_messages",
        lambda base_url, talker: [  # type: ignore[no-untyped-def]
            {"content": "我这周比较忙，晚点聊", "sender": "me", "time": "2026-02-18T10:00:00+08:00", "is_self": True}
        ],
    )
    monkeypatch.setattr(bridge_mod, "_load_contact_memory_snippets", lambda display_name, talker: [])

    out = asyncio.run(
        bridge_mod.handle_reply_suggest_command(
            "/reply suggest 郝睿",
            chat_id="oc_chat",
            agent_timeout_seconds=5,
        )
    )
    assert out is not None
    assert "暂无对方新消息" in out


def test_reply_prompt_uses_recent_10_and_memory(monkeypatch) -> None:
    prompts: list[str] = []
    monkeypatch.setattr(
        bridge_mod,
        "load_runtime_config",
        lambda env_file: replace(  # noqa: ARG005
            RuntimeConfig(),
            chatlog_enabled=True,
            chatlog_base_url="http://127.0.0.1:5030",
        ),
    )
    monkeypatch.setattr(bridge_mod, "_resolve_reply_target", lambda base_url, target: ("wxid_x", "小瓶盖"))
    monkeypatch.setattr(
        bridge_mod,
        "_fetch_recent_contact_messages",
        lambda base_url, talker: [  # type: ignore[no-untyped-def]
            {"content": f"m{i}", "sender": "s", "time": "2026-02-18T10:00:00+08:00", "is_self": (i % 2 == 0)}
            for i in range(12)
        ],
    )
    monkeypatch.setattr(
        bridge_mod,
        "_load_contact_memory_snippets",
        lambda display_name, talker: ["- 记忆1", "- 记忆2"],
    )

    async def fake_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        _ = (conversation_id, force_new_client)
        prompts.append(prompt)
        return "### 对方意图\nok", "logs/mock.jsonl"

    monkeypatch.setattr(bridge_mod, "run_agent", fake_run_agent)
    _ = asyncio.run(
        bridge_mod.handle_reply_suggest_command(
            "/reply suggest 小瓶盖",
            chat_id="oc_chat",
            agent_timeout_seconds=5,
        )
    )
    assert prompts
    assert "最近对话摘录(双方近10条)" in prompts[0]
    assert "[对方] m11" in prompts[0]
    assert "[我] m0" not in prompts[0]
    assert "\n[对方] m1\n" not in prompts[0]
    assert "联系人记忆摘要" in prompts[0]
    assert "- 记忆1" in prompts[0]


def test_handle_reply_suggest_lite_mode_returns_short_output(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge_mod,
        "load_runtime_config",
        lambda env_file: replace(  # noqa: ARG005
            RuntimeConfig(),
            chatlog_enabled=True,
            chatlog_base_url="http://127.0.0.1:5030",
        ),
    )
    monkeypatch.setattr(bridge_mod, "_resolve_reply_target", lambda base_url, target: ("wxid_x", "小瓶盖"))
    monkeypatch.setattr(
        bridge_mod,
        "_fetch_recent_contact_messages",
        lambda base_url, talker: [  # type: ignore[no-untyped-def]
            {"content": "好吧", "sender": "对方", "time": "2026-02-18T10:00:00+08:00", "is_self": False}
        ],
    )
    monkeypatch.setattr(bridge_mod, "_load_contact_memory_snippets", lambda display_name, talker: [])
    monkeypatch.setattr(bridge_mod, "_load_contact_reply_style", lambda talker: "")

    async def fake_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        _ = (prompt, conversation_id, force_new_client)
        return (
            "### 对方意图\n对方接受。\n\n"
            "### 建议回复(可直接发, 30-80字)\n收到，辛苦啦。\n\n"
            "### 备选回复(更温和)\n好的呀。\n\n"
            "### 超短回复(15-30字)\n好的收到。\n\n"
            "### 需要确认的问题\n1. 是否还要补充？\n",
            "logs/mock.jsonl",
        )

    monkeypatch.setattr(bridge_mod, "run_agent", fake_run_agent)
    out = asyncio.run(
        bridge_mod.handle_reply_suggest_command(
            "/reply suggest 小瓶盖 mode=lite",
            chat_id="oc_chat",
            agent_timeout_seconds=5,
        )
    )
    assert out is not None
    assert "建议回复(可直接发" in out
    assert "超短回复" in out
    assert "对方意图" not in out
    assert "需要确认的问题" not in out


def test_reply_prompt_includes_contact_style_profile(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(bridge_mod, "CHATLOG_TARGETS_FILE", tmp_path / "targets.json")
    store = bridge_mod.ChatlogTargetStore(bridge_mod.CHATLOG_TARGETS_FILE)
    store.upsert_target(
        "wxid_x",
        {
            "reply_style": "polite_refuse",
            "relationship_note": "长辈亲属，重礼仪",
            "etiquette_preferences": "拒绝时先感谢再婉拒",
        },
    )

    monkeypatch.setattr(
        bridge_mod,
        "load_runtime_config",
        lambda env_file: replace(  # noqa: ARG005
            RuntimeConfig(),
            chatlog_enabled=True,
            chatlog_base_url="http://127.0.0.1:5030",
        ),
    )
    monkeypatch.setattr(bridge_mod, "_resolve_reply_target", lambda base_url, target: ("wxid_x", "小瓶盖"))
    monkeypatch.setattr(
        bridge_mod,
        "_fetch_recent_contact_messages",
        lambda base_url, talker: [  # type: ignore[no-untyped-def]
            {"content": "好吧", "sender": "对方", "time": "2026-02-18T10:00:00+08:00", "is_self": False}
        ],
    )
    monkeypatch.setattr(bridge_mod, "_load_contact_memory_snippets", lambda display_name, talker: [])
    prompts: list[str] = []

    async def fake_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        _ = (conversation_id, force_new_client)
        prompts.append(prompt)
        return "### 建议回复(可直接发, 30-80字)\n收到。", "logs/mock.jsonl"

    monkeypatch.setattr(bridge_mod, "run_agent", fake_run_agent)
    _ = asyncio.run(
        bridge_mod.handle_reply_suggest_command(
            "/reply suggest 小瓶盖",
            chat_id="oc_chat",
            agent_timeout_seconds=5,
        )
    )
    assert prompts
    assert "联系人沟通风格偏好" in prompts[0]
    assert "polite_refuse" in prompts[0]
