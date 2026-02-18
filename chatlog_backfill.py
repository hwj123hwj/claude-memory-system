from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import urlopen

from chatlog_state_store import ChatlogStateStore


def _to_date_str(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _to_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_idempotency_key(talker: str, message: dict[str, Any]) -> str:
    seq = _to_int_or_none(message.get("seq"))
    if seq is not None:
        return str(seq)
    raw = (
        f"{talker}|"
        f"{message.get('sender', '')}|"
        f"{message.get('time', '')}|"
        f"{message.get('content', '')}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_chatlog_messages(
    *,
    base_url: str,
    talker: str,
    from_date: str,
    to_date: str,
    timeout_seconds: int = 20,
) -> list[dict[str, Any]]:
    query = urlencode(
        {
            "talker": talker,
            "time": f"{from_date}~{to_date}",
            "format": "json",
        }
    )
    url = f"{base_url.rstrip('/')}/api/v1/chatlog?{query}"
    with urlopen(url, timeout=timeout_seconds) as resp:  # noqa: S310
        payload = resp.read().decode("utf-8")
    data = json.loads(payload)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        items = data.get("items", [])
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
    return []


def run_backfill_once(
    *,
    store: ChatlogStateStore,
    talkers: list[str],
    fetch_messages: Callable[[str, str, str], list[dict[str, Any]]],
    now: datetime,
    bootstrap_days: int,
    should_accept_message: Callable[[str, dict[str, Any]], bool] | None = None,
) -> dict[str, int]:
    accepted_total = 0
    errors = 0
    scanned = 0

    for talker in talkers:
        if not talker.strip():
            continue
        scanned += 1
        checkpoint_time, _ = store.load_checkpoint(talker)
        if checkpoint_time:
            from_date = checkpoint_time[:10]
        else:
            from_date = _to_date_str(now - timedelta(days=bootstrap_days))
        to_date = _to_date_str(now)

        try:
            messages = fetch_messages(talker, from_date, to_date)
        except Exception:
            errors += 1
            continue

        accepted = 0
        max_time: str | None = None
        max_seq: int | None = None
        for message in messages:
            if should_accept_message is not None and not should_accept_message(talker, message):
                continue
            key = _build_idempotency_key(talker, message)
            message_time = message.get("time") if isinstance(message.get("time"), str) else None
            inserted = store.mark_processed(key, talker, message_time)
            if not inserted:
                continue
            accepted += 1

            seq = _to_int_or_none(message.get("seq"))
            if max_time is None or (message_time and message_time > max_time):
                max_time = message_time
                max_seq = seq
            elif message_time == max_time and seq is not None:
                old = max_seq if max_seq is not None else -1
                if seq > old:
                    max_seq = seq

        if accepted > 0:
            store.advance_checkpoint(talker, max_time, max_seq)
            accepted_total += accepted

    return {"scanned": scanned, "accepted": accepted_total, "errors": errors}
