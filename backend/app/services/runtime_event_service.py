from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from time import monotonic

from app.config import settings
from app.database import get_connection

RuntimeEventValue = str | int | float | bool

_EVENT_LOG_LIMIT = 400


@dataclass(slots=True, frozen=True)
class RuntimeTimelineEvent:
    event_id: int
    timestamp: str
    category: str
    level: str
    title: str
    message: str
    details: dict[str, RuntimeEventValue]


@dataclass(slots=True)
class _RecentEventSignature:
    signature: str
    recorded_at_monotonic: float


class RuntimeEventService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._recent_signatures: dict[str, _RecentEventSignature] = {}
        self._initialized_database_path: str | None = None
        self._initialize_storage()

    def record_event(
        self,
        *,
        category: str,
        level: str,
        title: str,
        message: str,
        details: dict[str, RuntimeEventValue] | None = None,
        dedupe_key: str | None = None,
        dedupe_window_seconds: float = 0.0,
    ) -> RuntimeTimelineEvent | None:
        normalized_details = self._normalize_details(details)
        signature = self._build_signature(
            category=category,
            level=level,
            title=title,
            message=message,
            details=normalized_details,
        )
        if (
            dedupe_key is not None
            and dedupe_window_seconds > 0
            and self._is_recent_duplicate(
                dedupe_key=dedupe_key,
                signature=signature,
                dedupe_window_seconds=dedupe_window_seconds,
            )
        ):
            return None

        self._ensure_storage_ready()
        timestamp = datetime.now(UTC).isoformat()
        details_json = json.dumps(normalized_details, ensure_ascii=True, separators=(",", ":"))
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO runtime_event_log (
                    timestamp,
                    category,
                    level,
                    title,
                    message,
                    details_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    category.strip(),
                    level.strip(),
                    title.strip(),
                    message.strip(),
                    details_json,
                ),
            )
            event_id = int(cursor.lastrowid)
            connection.execute(
                """
                DELETE FROM runtime_event_log
                WHERE event_id NOT IN (
                    SELECT event_id
                    FROM runtime_event_log
                    ORDER BY event_id DESC
                    LIMIT ?
                )
                """,
                (_EVENT_LOG_LIMIT,),
            )

        if dedupe_key is not None and dedupe_window_seconds > 0:
            with self._lock:
                self._recent_signatures[dedupe_key] = _RecentEventSignature(
                    signature=signature,
                    recorded_at_monotonic=monotonic(),
                )

        return RuntimeTimelineEvent(
            event_id=event_id,
            timestamp=timestamp,
            category=category.strip(),
            level=level.strip(),
            title=title.strip(),
            message=message.strip(),
            details=normalized_details,
        )

    def list_recent_events(self, *, limit: int = 18) -> list[RuntimeTimelineEvent]:
        capped_limit = max(1, min(int(limit), _EVENT_LOG_LIMIT))
        self._ensure_storage_ready()
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    event_id,
                    timestamp,
                    category,
                    level,
                    title,
                    message,
                    details_json
                FROM runtime_event_log
                ORDER BY event_id DESC
                LIMIT ?
                """,
                (capped_limit,),
            ).fetchall()

        events: list[RuntimeTimelineEvent] = []
        for row in rows:
            try:
                details = json.loads(row["details_json"] or "{}")
            except json.JSONDecodeError:
                details = {}
            events.append(
                RuntimeTimelineEvent(
                    event_id=int(row["event_id"]),
                    timestamp=row["timestamp"],
                    category=row["category"],
                    level=row["level"],
                    title=row["title"],
                    message=row["message"],
                    details=self._normalize_details(details),
                )
            )
        return events

    def _initialize_storage(self) -> None:
        current_database_path = str(settings.database_path)
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_event_log (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    category TEXT NOT NULL,
                    level TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runtime_event_log_timestamp
                ON runtime_event_log (timestamp DESC, event_id DESC)
                """
            )
        self._initialized_database_path = current_database_path

    def _ensure_storage_ready(self) -> None:
        current_database_path = str(settings.database_path)
        if self._initialized_database_path == current_database_path:
            return
        with self._lock:
            if self._initialized_database_path == current_database_path:
                return
            self._initialize_storage()

    def _is_recent_duplicate(
        self,
        *,
        dedupe_key: str,
        signature: str,
        dedupe_window_seconds: float,
    ) -> bool:
        now_monotonic = monotonic()
        with self._lock:
            previous = self._recent_signatures.get(dedupe_key)
            if previous is None:
                return False
            if previous.signature != signature:
                return False
            return (now_monotonic - previous.recorded_at_monotonic) < max(
                0.0,
                float(dedupe_window_seconds),
            )

    def _normalize_details(
        self,
        details: dict[str, object] | None,
    ) -> dict[str, RuntimeEventValue]:
        if not isinstance(details, dict):
            return {}
        normalized: dict[str, RuntimeEventValue] = {}
        for raw_key, raw_value in details.items():
            key = str(raw_key).strip()
            if not key:
                continue
            if isinstance(raw_value, bool):
                normalized[key] = raw_value
                continue
            if isinstance(raw_value, int):
                normalized[key] = raw_value
                continue
            if isinstance(raw_value, float):
                normalized[key] = round(raw_value, 3)
                continue
            if raw_value is None:
                continue
            normalized[key] = str(raw_value)
        return normalized

    def _build_signature(
        self,
        *,
        category: str,
        level: str,
        title: str,
        message: str,
        details: dict[str, RuntimeEventValue],
    ) -> str:
        return "|".join(
            [
                category.strip(),
                level.strip(),
                title.strip(),
                message.strip(),
                json.dumps(details, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
            ]
        )


runtime_event_service = RuntimeEventService()
