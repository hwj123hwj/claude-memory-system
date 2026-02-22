from __future__ import annotations

import json
from pathlib import Path
from typing import Any


VALID_GROUP_TYPES = {"relationship", "notification", "learning", "info_gap"}
VALID_CAPTURE_POLICIES = {"summary_only", "key_events", "hybrid"}
VALID_NOISE_TOLERANCE = {"low", "medium", "high"}


def _default_target(talker: str) -> dict[str, Any]:
    is_group = talker.endswith("@chatroom")
    return {
        "talker": talker,
        "enabled": True,
        "group_type": "info_gap" if is_group else "relationship",
        "importance": 3,
        "default_memory_bucket": "40_ProductMind" if is_group else "20_Connections",
        "focus_topics": [],
        "important_people": [],
        "noise_tolerance": "medium",
        "capture_policy": "summary_only",
    }


class ChatlogTargetStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, dict):
                out[k] = v
        return out

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_targets(self) -> list[dict[str, Any]]:
        data = self._load()
        items = list(data.values())
        items.sort(key=lambda x: str(x.get("talker", "")))
        return items

    def get_target(self, talker: str) -> dict[str, Any] | None:
        return self._load().get(talker)

    def upsert_target(self, talker: str, updates: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        current = data.get(talker, _default_target(talker))
        merged = {**current, **updates, "talker": talker}
        merged["enabled"] = bool(merged.get("enabled", True))
        merged["group_type"] = (
            str(merged.get("group_type", "info_gap"))
            if str(merged.get("group_type", "info_gap")) in VALID_GROUP_TYPES
            else current.get("group_type", "info_gap")
        )
        try:
            merged["importance"] = max(1, min(5, int(merged.get("importance", 3))))
        except Exception:
            merged["importance"] = int(current.get("importance", 3))
        if merged.get("default_memory_bucket") not in {
            "00_Inbox",
            "10_Growth",
            "20_Connections",
            "30_Wealth",
            "40_ProductMind",
        }:
            merged["default_memory_bucket"] = current.get(
                "default_memory_bucket",
                "40_ProductMind" if talker.endswith("@chatroom") else "20_Connections",
            )
        if not isinstance(merged.get("focus_topics"), list):
            merged["focus_topics"] = current.get("focus_topics", [])
        if not isinstance(merged.get("important_people"), list):
            merged["important_people"] = current.get("important_people", [])
        noise = str(merged.get("noise_tolerance", "medium"))
        merged["noise_tolerance"] = noise if noise in VALID_NOISE_TOLERANCE else "medium"
        policy = str(merged.get("capture_policy", "summary_only"))
        merged["capture_policy"] = policy if policy in VALID_CAPTURE_POLICIES else "summary_only"
        data[talker] = merged
        self._save(data)
        return merged

    def remove_target(self, talker: str) -> bool:
        data = self._load()
        if talker not in data:
            return False
        del data[talker]
        self._save(data)
        return True

    def enabled_talkers(self) -> list[str]:
        out: list[str] = []
        for item in self.list_targets():
            if bool(item.get("enabled", True)):
                talker = str(item.get("talker", "")).strip()
                if talker:
                    out.append(talker)
        return out
