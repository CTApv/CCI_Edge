from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock

from app.database import get_connection


@dataclass(slots=True, frozen=True)
class DeviceCommandState:
    device_id: str
    command_key: str
    last_set_value: float | None
    last_set_display: str | None
    last_set_at: str | None


class DeviceCommandStateService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._initialize_storage()

    def _initialize_storage(self) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS device_command_state (
                    device_id TEXT NOT NULL,
                    command_key TEXT NOT NULL,
                    last_set_value REAL,
                    last_set_display TEXT,
                    last_set_at TEXT,
                    PRIMARY KEY (device_id, command_key)
                )
                """
            )

    def list_command_states(self, device_id: str) -> dict[str, DeviceCommandState]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    device_id,
                    command_key,
                    last_set_value,
                    last_set_display,
                    last_set_at
                FROM device_command_state
                WHERE device_id = ?
                """,
                (device_id,),
            ).fetchall()

        return {
            row["command_key"]: DeviceCommandState(
                device_id=row["device_id"],
                command_key=row["command_key"],
                last_set_value=(
                    None if row["last_set_value"] is None else float(row["last_set_value"])
                ),
                last_set_display=row["last_set_display"],
                last_set_at=row["last_set_at"],
            )
            for row in rows
        }

    def record_successful_command(
        self,
        *,
        device_id: str,
        command_key: str,
        value: float,
        display_value: str,
    ) -> None:
        timestamp = datetime.now(UTC).isoformat()
        with self._lock:
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO device_command_state (
                        device_id,
                        command_key,
                        last_set_value,
                        last_set_display,
                        last_set_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(device_id, command_key) DO UPDATE SET
                        last_set_value = excluded.last_set_value,
                        last_set_display = excluded.last_set_display,
                        last_set_at = excluded.last_set_at
                    """,
                    (device_id, command_key, value, display_value, timestamp),
                )

    def delete_device_states(self, device_id: str) -> None:
        with self._lock:
            with get_connection() as connection:
                connection.execute(
                    "DELETE FROM device_command_state WHERE device_id = ?",
                    (device_id,),
                )


device_command_state_service = DeviceCommandStateService()
