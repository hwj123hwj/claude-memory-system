from pathlib import Path

from app import validate_memory_write_target


def test_block_new_plan_like_file_without_new_file_intent(tmp_path: Path) -> None:
    root = tmp_path
    (root / "memory" / "10_Growth").mkdir(parents=True)
    ok, reason = validate_memory_write_target(
        tool_name="Write",
        payload={"file_path": "memory/10_Growth/qinhuangdao_trip_plan.md"},
        root=root,
        allow_new_file=False,
    )
    assert ok is False
    assert "blocked by default" in reason


def test_allow_new_non_plan_file_even_without_new_file_intent(tmp_path: Path) -> None:
    root = tmp_path
    (root / "memory" / "10_Growth").mkdir(parents=True)
    ok, reason = validate_memory_write_target(
        tool_name="Write",
        payload={"file_path": "memory/10_Growth/notes.md"},
        root=root,
        allow_new_file=False,
    )
    assert ok is True
    assert reason == "ok"


def test_block_new_plan_file_when_similar_file_exists(tmp_path: Path) -> None:
    root = tmp_path
    growth = root / "memory" / "10_Growth"
    growth.mkdir(parents=True)
    existing = growth / "qinhuangdao_trip_plan_2026.md"
    existing.write_text("# existing", encoding="utf-8")

    ok, reason = validate_memory_write_target(
        tool_name="Write",
        payload={"file_path": "memory/10_Growth/qinhuangdao_trip_plan.md"},
        root=root,
        allow_new_file=True,
    )
    assert ok is False
    assert "Found similar plan files" in reason


def test_allow_inbox_new_file(tmp_path: Path) -> None:
    root = tmp_path
    (root / "memory" / "00_Inbox").mkdir(parents=True)
    ok, reason = validate_memory_write_target(
        tool_name="Write",
        payload={"file_path": "memory/00_Inbox/new_note.md"},
        root=root,
        allow_new_file=False,
    )
    assert ok is True
    assert reason == "ok"


def test_block_growth_detail_plan_without_roadmap_backlink(tmp_path: Path) -> None:
    root = tmp_path
    (root / "memory" / "10_Growth").mkdir(parents=True)
    ok, reason = validate_memory_write_target(
        tool_name="Write",
        payload={
            "file_path": "memory/10_Growth/learning_plan_backend_2026Q2.md",
            "content": "# 后端学习计划\n- 目标...",
        },
        root=root,
        allow_new_file=True,
    )
    assert ok is False
    assert "roadmap_2026.md" in reason


def test_allow_growth_detail_plan_with_roadmap_backlink(tmp_path: Path) -> None:
    root = tmp_path
    (root / "memory" / "10_Growth").mkdir(parents=True)
    ok, reason = validate_memory_write_target(
        tool_name="Write",
        payload={
            "file_path": "memory/10_Growth/learning_plan_backend_2026Q2.md",
            "content": (
                "关联总览：`memory/10_Growth/roadmap_2026.md`\n\n"
                "# 后端学习计划\n- 目标..."
            ),
        },
        root=root,
        allow_new_file=True,
    )
    assert ok is True
    assert reason == "ok"
