from datetime import datetime, timezone
from pathlib import Path

from chatlog_backfill import run_backfill_once
from chatlog_state_store import ChatlogStateStore


def test_run_backfill_once_updates_checkpoint_and_dedups(tmp_path: Path) -> None:
    store = ChatlogStateStore(tmp_path / "state.db")
    talkers = ["wxid_a"]

    def fetcher(talker: str, from_date: str, to_date: str) -> list[dict[str, object]]:
        _ = (talker, from_date, to_date)
        return [
            {"seq": 100, "time": "2026-02-18T10:00:00+08:00", "content": "one"},
            {"seq": 101, "time": "2026-02-18T10:05:00+08:00", "content": "two"},
        ]

    now = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    report1 = run_backfill_once(
        store=store,
        talkers=talkers,
        fetch_messages=fetcher,
        now=now,
        bootstrap_days=1,
    )
    assert report1["accepted"] == 2
    assert report1["errors"] == 0
    assert store.load_checkpoint("wxid_a") == ("2026-02-18T10:05:00+08:00", 101)

    report2 = run_backfill_once(
        store=store,
        talkers=talkers,
        fetch_messages=fetcher,
        now=now,
        bootstrap_days=1,
    )
    assert report2["accepted"] == 0
    assert report2["errors"] == 0
    assert store.load_checkpoint("wxid_a") == ("2026-02-18T10:05:00+08:00", 101)


def test_run_backfill_once_fetch_error_keeps_checkpoint(tmp_path: Path) -> None:
    store = ChatlogStateStore(tmp_path / "state.db")
    store.advance_checkpoint("wxid_a", "2026-02-18T10:05:00+08:00", 101)

    def fetcher(talker: str, from_date: str, to_date: str) -> list[dict[str, object]]:
        _ = (talker, from_date, to_date)
        raise RuntimeError("boom")

    now = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    report = run_backfill_once(
        store=store,
        talkers=["wxid_a"],
        fetch_messages=fetcher,
        now=now,
        bootstrap_days=1,
    )
    assert report["accepted"] == 0
    assert report["errors"] == 1
    assert store.load_checkpoint("wxid_a") == ("2026-02-18T10:05:00+08:00", 101)


def test_run_backfill_once_respects_message_filter(tmp_path: Path) -> None:
    store = ChatlogStateStore(tmp_path / "state.db")

    def fetcher(talker: str, from_date: str, to_date: str) -> list[dict[str, object]]:
        _ = (talker, from_date, to_date)
        return [
            {"seq": 1, "time": "2026-02-18T10:00:00+08:00", "senderName": "路人甲", "content": "hi"},
            {"seq": 2, "time": "2026-02-18T10:01:00+08:00", "senderName": "郝睿", "content": "重点信息"},
        ]

    def only_hao(talker: str, message: dict[str, object]) -> bool:
        _ = talker
        return str(message.get("senderName", "")) == "郝睿"

    now = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    report = run_backfill_once(
        store=store,
        talkers=["48651409135@chatroom"],
        fetch_messages=fetcher,
        now=now,
        bootstrap_days=1,
        should_accept_message=only_hao,
    )
    assert report["accepted"] == 1
    assert report["errors"] == 0


def test_run_backfill_once_applies_capture_policy_modes(tmp_path: Path) -> None:
    import app

    store = ChatlogStateStore(tmp_path / "state.db")
    target_map = {
        "summary@chatroom": {"group_type": "learning", "capture_policy": "summary_only", "important_people": []},
        "events@chatroom": {"group_type": "info_gap", "capture_policy": "key_events", "important_people": []},
        "hybrid@chatroom": {"group_type": "info_gap", "capture_policy": "hybrid", "important_people": ["VIP"]},
    }

    def fetcher(talker: str, from_date: str, to_date: str) -> list[dict[str, object]]:
        _ = (from_date, to_date)
        if talker == "summary@chatroom":
            return [{"seq": 10, "time": "2026-02-18T10:00:00+08:00", "senderName": "A", "content": "normal"}]
        if talker == "events@chatroom":
            return [{"seq": 20, "time": "2026-02-18T10:00:00+08:00", "senderName": "A", "content": "deadline soon"}]
        return [{"seq": 30, "time": "2026-02-18T10:00:00+08:00", "senderName": "VIP", "content": "routine"}]

    def policy_filter(talker: str, message: dict[str, object]) -> bool:
        target = target_map.get(talker)
        return app._should_accept_group_message(target, message)

    now = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    report = run_backfill_once(
        store=store,
        talkers=["summary@chatroom", "events@chatroom", "hybrid@chatroom"],
        fetch_messages=fetcher,
        now=now,
        bootstrap_days=1,
        should_accept_message=policy_filter,
    )
    assert report["accepted"] == 2
    assert store.load_checkpoint("summary@chatroom") == (None, None)
    assert store.load_checkpoint("events@chatroom") == ("2026-02-18T10:00:00+08:00", 20)
    assert store.load_checkpoint("hybrid@chatroom") == ("2026-02-18T10:00:00+08:00", 30)
