from pathlib import Path

import feishu_ws_bridge as bridge_mod


def test_memory_group_command_add_list_show_remove(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(bridge_mod, "CHATLOG_TARGETS_FILE", tmp_path / "targets.json")

    out1 = bridge_mod.handle_memory_group_command(
        "/memory group add 48651409135@chatroom type=learning importance=4 bucket=10_Growth topics=python,ai"
    )
    assert out1 is not None
    assert "48651409135@chatroom" in out1

    out2 = bridge_mod.handle_memory_group_command("/memory group list")
    assert out2 is not None
    assert "48651409135@chatroom" in out2

    out3 = bridge_mod.handle_memory_group_command("/memory group show 48651409135@chatroom")
    assert out3 is not None
    assert '"group_type": "learning"' in out3

    out4 = bridge_mod.handle_memory_group_command("/memory group remove 48651409135@chatroom")
    assert out4 is not None
    assert "48651409135@chatroom" in out4


def test_memory_group_command_returns_none_for_non_command() -> None:
    assert bridge_mod.handle_memory_group_command("hello") is None


def test_memory_group_people_subcommands(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(bridge_mod, "CHATLOG_TARGETS_FILE", tmp_path / "targets.json")
    bridge_mod.handle_memory_group_command("/memory group add 48651409135@chatroom type=learning")

    out1 = bridge_mod.handle_memory_group_command(
        "/memory group people 48651409135@chatroom add VIP,Alice"
    )
    assert out1 is not None
    assert "important_people" in out1

    out2 = bridge_mod.handle_memory_group_command("/memory group show 48651409135@chatroom")
    assert out2 is not None
    assert '"important_people": [' in out2
    assert "VIP" in out2
    assert "Alice" in out2

    out3 = bridge_mod.handle_memory_group_command(
        "/memory group people 48651409135@chatroom remove Alice"
    )
    assert out3 is not None
    out4 = bridge_mod.handle_memory_group_command("/memory group show 48651409135@chatroom")
    assert out4 is not None
    assert "VIP" in out4
    assert "Alice" not in out4

    out5 = bridge_mod.handle_memory_group_command(
        "/memory group people 48651409135@chatroom set Bob,Carol"
    )
    assert out5 is not None
    out6 = bridge_mod.handle_memory_group_command(
        "/memory group people 48651409135@chatroom show"
    )
    assert out6 is not None
    assert "Bob" in out6
    assert "Carol" in out6


def test_memory_group_update_capture_policy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(bridge_mod, "CHATLOG_TARGETS_FILE", tmp_path / "targets.json")
    bridge_mod.handle_memory_group_command("/memory group add 48651409135@chatroom type=learning")

    out = bridge_mod.handle_memory_group_command(
        "/memory group update 48651409135@chatroom policy=hybrid"
    )
    assert out is not None

    show = bridge_mod.handle_memory_group_command("/memory group show 48651409135@chatroom")
    assert show is not None
    assert '"capture_policy": "hybrid"' in show


def test_memory_group_update_contact_reply_style_fields(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(bridge_mod, "CHATLOG_TARGETS_FILE", tmp_path / "targets.json")
    bridge_mod.handle_memory_group_command("/memory group add wxid_x type=relationship")

    _ = bridge_mod.handle_memory_group_command(
        "/memory group update wxid_x reply_style=polite_refuse relationship_note=elder etiquette_preferences=thanks_first"
    )
    show = bridge_mod.handle_memory_group_command("/memory group show wxid_x")
    assert show is not None
    assert '"reply_style": "polite_refuse"' in show
    assert '"relationship_note": "elder"' in show
    assert '"etiquette_preferences": "thanks_first"' in show
