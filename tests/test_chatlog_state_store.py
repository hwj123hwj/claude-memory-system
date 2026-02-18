from pathlib import Path

from chatlog_state_store import ChatlogStateStore


def test_mark_processed_is_idempotent(tmp_path: Path) -> None:
    store = ChatlogStateStore(tmp_path / "chatlog_state.db")
    inserted1 = store.mark_processed("k1", "wxid_x", "2026-02-18T10:00:00+08:00")
    inserted2 = store.mark_processed("k1", "wxid_x", "2026-02-18T10:00:00+08:00")
    assert inserted1 is True
    assert inserted2 is False
    assert store.is_processed("k1") is True


def test_advance_checkpoint_only_moves_forward(tmp_path: Path) -> None:
    store = ChatlogStateStore(tmp_path / "chatlog_state.db")
    talker = "wxid_x"
    store.advance_checkpoint(talker, "2026-02-18T10:00:00+08:00", 10)
    assert store.load_checkpoint(talker) == ("2026-02-18T10:00:00+08:00", 10)

    store.advance_checkpoint(talker, "2026-02-18T09:00:00+08:00", 99)
    assert store.load_checkpoint(talker) == ("2026-02-18T10:00:00+08:00", 10)

    store.advance_checkpoint(talker, "2026-02-18T10:00:00+08:00", 11)
    assert store.load_checkpoint(talker) == ("2026-02-18T10:00:00+08:00", 11)
