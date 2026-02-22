from pathlib import Path

from chatlog_targets import ChatlogTargetStore


def test_upsert_and_list_targets(tmp_path: Path) -> None:
    store = ChatlogTargetStore(tmp_path / "targets.json")
    a = store.upsert_target("48651409135@chatroom", {"group_type": "learning", "importance": 5})
    b = store.upsert_target("wxid_cfz3t4h22px722", {"group_type": "relationship"})
    assert a["group_type"] == "learning"
    assert a["default_memory_bucket"] == "40_ProductMind"
    assert b["default_memory_bucket"] == "20_Connections"
    assert len(store.list_targets()) == 2
    assert store.enabled_talkers() == ["48651409135@chatroom", "wxid_cfz3t4h22px722"]


def test_remove_target(tmp_path: Path) -> None:
    store = ChatlogTargetStore(tmp_path / "targets.json")
    store.upsert_target("wxid_x", {"importance": 2})
    assert store.remove_target("wxid_x") is True
    assert store.remove_target("wxid_x") is False
