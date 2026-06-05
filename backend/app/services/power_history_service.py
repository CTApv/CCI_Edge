from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from time import monotonic

from app.config import settings
from app.logger import get_logger
from app.services.live_cache import PowerSample

logger = get_logger("pv_edge_manager.power_history")


class PowerHistoryService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._database_path = settings.power_history_database_path
        self._history_limit = max(settings.power_history_limit, 120)
        self._max_bytes = max(settings.power_history_max_bytes, 256 * 1024 * 1024)
        self._query_max_points = max(32, min(settings.power_history_query_max_points, 900))
        self._prune_batch_size = 50_000
        self._size_check_every_inserts = 256
        self._append_counter = 0
        self._last_size_check_monotonic = 0.0
        self._size_check_interval_seconds = 30.0
        self._estimated_row_count = 0
        try:
            self._initialize_storage()
        except sqlite3.DatabaseError as exc:
            with self._lock:
                if not self._recover_from_database_error_locked(exc):
                    raise
        self._estimated_row_count = self._read_fast_row_count_estimate()

    def append_sample(self, device_id: str, timestamp: str, power_kw: float) -> None:
        with self._lock:
            try:
                self._append_sample_locked(device_id, timestamp, power_kw)
            except sqlite3.DatabaseError as exc:
                if not self._recover_from_database_error_locked(exc):
                    logger.warning("Unable to append power history sample: %s", exc)
                    return
                try:
                    self._append_sample_locked(device_id, timestamp, power_kw)
                except sqlite3.Error as retry_exc:
                    logger.warning("Unable to append power history sample after recovery: %s", retry_exc)

    def _append_sample_locked(self, device_id: str, timestamp: str, power_kw: float) -> None:
        with self._get_connection() as connection:
            connection.execute(
                """
                INSERT INTO power_history_samples (
                    device_id,
                    timestamp,
                    power_kw
                ) VALUES (?, ?, ?)
                """,
                (device_id, timestamp, power_kw),
            )

            delete_cursor = connection.execute(
                """
                DELETE FROM power_history_samples
                WHERE sample_id IN (
                    SELECT sample_id
                    FROM power_history_samples
                    WHERE device_id = ?
                    ORDER BY sample_id ASC
                    LIMIT (
                        SELECT CASE
                            WHEN COUNT(*) > ? THEN COUNT(*) - ?
                            ELSE 0
                        END
                        FROM power_history_samples
                        WHERE device_id = ?
                    )
                )
                """,
                (device_id, self._history_limit, self._history_limit, device_id),
            )
            deleted_count = max(0, delete_cursor.rowcount or 0)

        self._estimated_row_count = max(
            0,
            self._estimated_row_count + 1 - deleted_count,
        )

        self._append_counter += 1
        now = monotonic()
        should_check_size = (
            self._append_counter >= self._size_check_every_inserts
            or (now - self._last_size_check_monotonic) >= self._size_check_interval_seconds
        )
        if should_check_size:
            self._append_counter = 0
            self._last_size_check_monotonic = now
            self._prune_to_size_locked()

    def get_device_history(
        self,
        device_id: str,
        *,
        max_points: int | None = None,
        start_timestamp: str | None = None,
        end_timestamp: str | None = None,
    ) -> list[PowerSample]:
        effective_max_points = self._normalize_max_points(max_points)
        # Read queries use dedicated SQLite connections in WAL mode, so they do not
        # need to serialize behind append_sample(). Keeping them independent avoids
        # stalling the polling loop when the dashboard refreshes the history view.
        try:
            with self._get_connection() as connection:
                total_rows = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM power_history_samples
                    WHERE device_id = ?
                      AND (? IS NULL OR timestamp >= ?)
                      AND (? IS NULL OR timestamp <= ?)
                    """,
                    (device_id, start_timestamp, start_timestamp, end_timestamp, end_timestamp),
                ).fetchone()[0]
                if total_rows == 0:
                    return []

                if total_rows <= effective_max_points:
                    rows = connection.execute(
                        """
                        SELECT timestamp, power_kw
                        FROM power_history_samples
                        WHERE device_id = ?
                          AND (? IS NULL OR timestamp >= ?)
                          AND (? IS NULL OR timestamp <= ?)
                        ORDER BY timestamp ASC
                        """,
                        (device_id, start_timestamp, start_timestamp, end_timestamp, end_timestamp),
                    ).fetchall()
                else:
                    step = math.ceil(total_rows / effective_max_points)
                    rows = connection.execute(
                        """
                        WITH ordered AS (
                            SELECT
                                timestamp,
                                power_kw,
                                ROW_NUMBER() OVER (ORDER BY timestamp ASC) AS rn,
                                COUNT(*) OVER () AS total_count
                            FROM power_history_samples
                            WHERE device_id = ?
                              AND (? IS NULL OR timestamp >= ?)
                              AND (? IS NULL OR timestamp <= ?)
                        )
                        SELECT timestamp, power_kw
                        FROM ordered
                        WHERE rn = 1 OR rn = total_count OR ((rn - 1) % ?) = 0
                        ORDER BY rn ASC
                        """,
                        (
                            device_id,
                            start_timestamp,
                            start_timestamp,
                            end_timestamp,
                            end_timestamp,
                            step,
                        ),
                    ).fetchall()
        except sqlite3.DatabaseError as exc:
            self._recover_from_database_error(exc)
            return []

        return [
            PowerSample(timestamp=row["timestamp"], power_kw=float(row["power_kw"]))
            for row in rows
        ]

    def get_fleet_timeline(
        self,
        *,
        max_points: int | None = None,
        start_timestamp: str | None = None,
        end_timestamp: str | None = None,
    ) -> list[str]:
        effective_max_points = self._normalize_max_points(max_points)
        try:
            with self._get_connection() as connection:
                total_rows = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT DISTINCT timestamp
                        FROM power_history_samples
                        WHERE (? IS NULL OR timestamp >= ?)
                          AND (? IS NULL OR timestamp <= ?)
                    )
                    """,
                    (start_timestamp, start_timestamp, end_timestamp, end_timestamp),
                ).fetchone()[0]
                if total_rows == 0:
                    return []

                if total_rows <= effective_max_points:
                    rows = connection.execute(
                        """
                        SELECT DISTINCT timestamp
                        FROM power_history_samples
                        WHERE (? IS NULL OR timestamp >= ?)
                          AND (? IS NULL OR timestamp <= ?)
                        ORDER BY timestamp ASC
                        """,
                        (start_timestamp, start_timestamp, end_timestamp, end_timestamp),
                    ).fetchall()
                else:
                    step = math.ceil(total_rows / effective_max_points)
                    rows = connection.execute(
                        """
                        WITH ordered AS (
                            SELECT
                                timestamp,
                                ROW_NUMBER() OVER (ORDER BY timestamp ASC) AS rn,
                                COUNT(*) OVER () AS total_count
                            FROM (
                                SELECT DISTINCT timestamp
                                FROM power_history_samples
                                WHERE (? IS NULL OR timestamp >= ?)
                                  AND (? IS NULL OR timestamp <= ?)
                            )
                        )
                        SELECT timestamp
                        FROM ordered
                        WHERE rn = 1 OR rn = total_count OR ((rn - 1) % ?) = 0
                        ORDER BY rn ASC
                        """,
                        (
                            start_timestamp,
                            start_timestamp,
                            end_timestamp,
                            end_timestamp,
                            step,
                        ),
                    ).fetchall()
        except sqlite3.DatabaseError as exc:
            self._recover_from_database_error(exc)
            return []

        return [str(row["timestamp"]) for row in rows]

    def get_fleet_history_matrix(
        self,
        device_ids: Sequence[str],
        *,
        max_points: int | None = None,
        start_timestamp: str | None = None,
        end_timestamp: str | None = None,
    ) -> tuple[list[str], dict[str, list[float]]]:
        effective_max_points = self._normalize_max_points(max_points)
        normalized_device_ids = [str(device_id) for device_id in device_ids if str(device_id)]
        if not normalized_device_ids:
            return [], {}

        where_clause, params = self._build_device_time_filter(
            normalized_device_ids,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
        )
        bounds_query = f"""
            SELECT
                MIN(CAST(strftime('%s', timestamp) AS INTEGER)) AS min_epoch,
                MAX(CAST(strftime('%s', timestamp) AS INTEGER)) AS max_epoch
            FROM power_history_samples
            WHERE {where_clause}
        """

        try:
            with self._get_connection() as connection:
                bounds = connection.execute(bounds_query, params).fetchone()
                min_epoch = None if bounds is None else bounds["min_epoch"]
                max_epoch = None if bounds is None else bounds["max_epoch"]
                if min_epoch is None or max_epoch is None:
                    return [], {device_id: [] for device_id in normalized_device_ids}

                start_epoch = int(min_epoch)
                end_epoch = int(max_epoch)
                bucket_seconds = max(
                    1,
                    math.ceil(max(1, end_epoch - start_epoch + 1) / effective_max_points),
                )

                bucket_query = f"""
                    WITH bucketed AS (
                        SELECT
                            device_id,
                            CAST(
                                (
                                    CAST(strftime('%s', timestamp) AS INTEGER) - ?
                                ) / ? AS INTEGER
                            ) AS bucket_index,
                            timestamp,
                            power_kw,
                            sample_id,
                            ROW_NUMBER() OVER (
                                PARTITION BY
                                    device_id,
                                    CAST(
                                        (
                                            CAST(strftime('%s', timestamp) AS INTEGER) - ?
                                        ) / ? AS INTEGER
                                    )
                                ORDER BY timestamp DESC, sample_id DESC
                            ) AS row_rank
                        FROM power_history_samples
                        WHERE {where_clause}
                    )
                    SELECT device_id, bucket_index, timestamp, power_kw
                    FROM bucketed
                    WHERE row_rank = 1
                    ORDER BY bucket_index ASC, device_id ASC
                """
                rows = connection.execute(
                    bucket_query,
                    (
                        start_epoch,
                        bucket_seconds,
                        start_epoch,
                        bucket_seconds,
                        *params,
                    ),
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            self._recover_from_database_error(exc)
            return [], {device_id: [] for device_id in normalized_device_ids}

        bucket_labels: dict[int, str] = {}
        bucket_values_by_device: dict[str, dict[int, float]] = {
            device_id: {} for device_id in normalized_device_ids
        }
        for row in rows:
            device_id = str(row["device_id"])
            bucket_index = int(row["bucket_index"])
            timestamp = str(row["timestamp"])
            power_kw = float(row["power_kw"])
            previous_label = bucket_labels.get(bucket_index)
            if previous_label is None or timestamp > previous_label:
                bucket_labels[bucket_index] = timestamp
            bucket_values_by_device.setdefault(device_id, {})[bucket_index] = power_kw

        ordered_bucket_indexes = sorted(bucket_labels)
        labels = [bucket_labels[bucket_index] for bucket_index in ordered_bucket_indexes]
        if not labels:
            return [], {device_id: [] for device_id in normalized_device_ids}

        history_matrix: dict[str, list[float]] = {}
        for device_id in normalized_device_ids:
            latest_value = 0.0
            bucket_values = bucket_values_by_device.get(device_id, {})
            aligned_values: list[float] = []
            for bucket_index in ordered_bucket_indexes:
                if bucket_index in bucket_values:
                    latest_value = bucket_values[bucket_index]
                aligned_values.append(float(latest_value))
            history_matrix[device_id] = aligned_values

        return labels, history_matrix

    def get_device_aligned_history(
        self,
        device_id: str,
        timeline: Sequence[str],
    ) -> list[float]:
        if len(timeline) == 0:
            return []

        placeholders = ", ".join(["(?)"] * len(timeline))
        query = f"""
            WITH timeline(timestamp) AS (
                VALUES {placeholders}
            )
            SELECT
                timeline.timestamp AS timestamp,
                (
                    SELECT samples.power_kw
                    FROM power_history_samples AS samples
                    WHERE samples.device_id = ?
                      AND samples.timestamp <= timeline.timestamp
                    ORDER BY samples.timestamp DESC
                    LIMIT 1
                ) AS power_kw
            FROM timeline
            ORDER BY timeline.timestamp ASC
        """
        params = [*timeline, device_id]

        try:
            with self._get_connection() as connection:
                rows = connection.execute(query, params).fetchall()
        except sqlite3.DatabaseError as exc:
            self._recover_from_database_error(exc)
            return [0.0 for _ in timeline]

        values: list[float] = []
        for row in rows:
            raw_value = row["power_kw"]
            values.append(float(raw_value) if raw_value is not None else 0.0)
        return values

    def delete_device_history(self, device_id: str) -> None:
        with self._lock:
            try:
                with self._get_connection() as connection:
                    delete_cursor = connection.execute(
                        "DELETE FROM power_history_samples WHERE device_id = ?",
                        (device_id,),
                    )
                    deleted_count = max(0, delete_cursor.rowcount or 0)
                    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    connection.execute("PRAGMA incremental_vacuum(200)")
            except sqlite3.DatabaseError as exc:
                self._recover_from_database_error_locked(exc)
                return
            self._estimated_row_count = max(0, self._estimated_row_count - deleted_count)

    def get_storage_stats(self) -> dict[str, str | int | float]:
        current_bytes = self._get_storage_size_bytes()
        row_count = self._estimated_row_count
        usage_percent = 0.0
        if self._max_bytes > 0:
            usage_percent = min(100.0, max(0.0, (current_bytes / self._max_bytes) * 100.0))

        return {
            "database_path": str(self._database_path),
            "current_bytes": current_bytes,
            "max_bytes": self._max_bytes,
            "usage_percent": usage_percent,
            "row_count": row_count,
        }

    def _read_fast_row_count_estimate(self) -> int:
        try:
            with self._get_connection() as connection:
                row = connection.execute(
                    "SELECT COALESCE(MAX(sample_id), 0) FROM power_history_samples"
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            if self._recover_from_database_error(exc):
                return 0
            logger.warning("Unable to estimate power history row count: %s", exc)
            return 0
        except sqlite3.Error as exc:
            logger.warning("Unable to estimate power history row count: %s", exc)
            return 0
        return int(row[0] or 0)

    def _normalize_max_points(self, max_points: int | None) -> int:
        if max_points is None:
            return self._query_max_points
        return max(32, min(max_points, 900))

    def _initialize_storage(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute("PRAGMA auto_vacuum = INCREMENTAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS power_history_samples (
                    sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    power_kw REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_power_history_device_timestamp
                ON power_history_samples (device_id, timestamp)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_power_history_timestamp
                ON power_history_samples (timestamp)
                """
            )

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def _recover_from_database_error(self, exc: sqlite3.DatabaseError) -> bool:
        with self._lock:
            return self._recover_from_database_error_locked(exc)

    def _recover_from_database_error_locked(self, exc: sqlite3.DatabaseError) -> bool:
        if not self._is_recoverable_database_error(exc):
            logger.warning("Power history database operation failed: %s", exc)
            return False

        suffix = datetime.now(UTC).strftime("corrupt-%Y%m%d-%H%M%S")
        moved_paths: list[str] = []
        for path in self._history_related_paths():
            if not path.exists():
                continue
            recovered_path = path.with_name(f"{path.name}.{suffix}")
            try:
                path.replace(recovered_path)
                moved_paths.append(str(recovered_path))
            except OSError as move_exc:
                logger.warning("Unable to quarantine malformed power history file %s: %s", path, move_exc)

        logger.warning(
            "Power history database was malformed and has been quarantined: %s",
            ", ".join(moved_paths) if moved_paths else "no files moved",
        )
        self._append_counter = 0
        self._estimated_row_count = 0
        self._initialize_storage()
        return True

    def _is_recoverable_database_error(self, exc: sqlite3.DatabaseError) -> bool:
        message = str(exc).lower()
        return (
            "database disk image is malformed" in message
            or "file is not a database" in message
            or "database corruption" in message
        )

    def _prune_to_size_locked(self) -> None:
        current_size = self._get_storage_size_bytes()
        if current_size <= self._max_bytes:
            return

        target_size = int(self._max_bytes * 0.92)
        logger.warning(
            "Power history storage above threshold: current=%s max=%s target=%s",
            current_size,
            self._max_bytes,
            target_size,
        )

        deleted_rows = 0
        while current_size > target_size:
            with self._get_connection() as connection:
                cursor = connection.execute(
                    """
                    DELETE FROM power_history_samples
                    WHERE sample_id IN (
                        SELECT sample_id
                        FROM power_history_samples
                        ORDER BY sample_id ASC
                        LIMIT ?
                    )
                    """,
                    (self._prune_batch_size,),
                )
                deleted_count = cursor.rowcount if cursor.rowcount is not None else 0
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                connection.execute("PRAGMA incremental_vacuum(2000)")

            deleted_rows += max(deleted_count, 0)
            if deleted_count <= 0:
                break
            current_size = self._get_storage_size_bytes()

        if deleted_rows > 0:
            self._estimated_row_count = max(0, self._estimated_row_count - deleted_rows)
            logger.info(
                "Pruned %s power history rows to contain storage growth. Current size=%s bytes.",
                deleted_rows,
                current_size,
            )

    def _get_storage_size_bytes(self) -> int:
        total_size = 0
        for path in self._history_related_paths():
            if path.exists():
                total_size += path.stat().st_size
        return total_size

    def _history_related_paths(self) -> list[Path]:
        return [
            self._database_path,
            Path(f"{self._database_path}-wal"),
            Path(f"{self._database_path}-shm"),
        ]

    def _build_device_time_filter(
        self,
        device_ids: Sequence[str],
        *,
        start_timestamp: str | None = None,
        end_timestamp: str | None = None,
    ) -> tuple[str, list[object]]:
        placeholders = ", ".join("?" for _ in device_ids)
        clauses = [f"device_id IN ({placeholders})"]
        params: list[object] = [*device_ids]
        if start_timestamp is not None:
            clauses.append("timestamp >= ?")
            params.append(start_timestamp)
        if end_timestamp is not None:
            clauses.append("timestamp <= ?")
            params.append(end_timestamp)
        return " AND ".join(clauses), params


power_history_service = PowerHistoryService()
