from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock

from app.database import get_connection
from app.logger import get_logger
from app.services.modbus_tcp_slave_config_service import modbus_tcp_slave_config_service
from app.services.runtime_event_service import runtime_event_service

DiagnosticValue = str | int | float | bool
FLEET_CONTROL_SINGLETON_KEY = "global"
SOURCE_PRIORITIES = {
    "modbus_tcp_slave": 1000,
    "api": 300,
}

logger = get_logger("pv_edge_manager.fleet_control")


@dataclass(slots=True, frozen=True)
class FleetControlState:
    active_power_limit_percent: float | None
    updated_at: str | None
    updated_source: str | None
    last_dispatch_at: str | None
    last_dispatch_ok_count: int
    last_dispatch_error_count: int
    last_dispatch_skipped_count: int
    eligible_device_count: int
    effective_source_priority: int
    last_rejected_source: str | None
    last_rejected_reason: str | None
    last_rejected_at: str | None


@dataclass(slots=True, frozen=True)
class FleetDeviceControlState:
    device_id: str
    name: str
    brand: str
    model: str
    protocol: str
    transport: str
    device_status: str
    eligibility: str
    eligibility_reason: str | None
    control_state: str
    desired_percent: float | None
    desired_updated_at: str | None
    desired_source: str | None
    desired_source_priority: int
    last_sent_percent: float | None
    last_applied_percent: float | None
    telemetry_confirmed: bool
    last_command: str | None
    last_resolved_value: float | None
    last_resolved_unit: str | None
    last_dispatch_outcome: str | None
    last_dispatch_at: str | None
    last_error: str | None
    note: str


@dataclass(slots=True, frozen=True)
class FleetDeviceDispatchResult:
    device_id: str
    name: str
    brand: str
    model: str
    protocol: str
    transport: str
    outcome: str
    success: bool
    message: str
    command: str | None
    diagnostics: dict[str, DiagnosticValue]
    timestamp: str


class FleetSetpointService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._device_results: dict[str, FleetDeviceDispatchResult] = {}
        self._initialize_storage()

    def get_state(self) -> FleetControlState:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT
                    active_power_limit_percent,
                    updated_at,
                    updated_source,
                    last_dispatch_at,
                    last_dispatch_ok_count,
                    last_dispatch_error_count,
                    last_dispatch_skipped_count,
                    eligible_device_count,
                    last_rejected_source,
                    last_rejected_reason,
                    last_rejected_at
                FROM fleet_control_state
                WHERE singleton_key = ?
                """,
                (FLEET_CONTROL_SINGLETON_KEY,),
            ).fetchone()

        if row is None:
            raise RuntimeError("Missing fleet control state row.")
        return self._row_to_state(row)

    def list_device_results(self) -> list[FleetDeviceDispatchResult]:
        with self._lock:
            return list(self._device_results.values())

    def clear_device_results(self) -> None:
        with self._lock:
            self._device_results = {}

    def list_device_control_states(self) -> list[FleetDeviceControlState]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    device_id,
                    name,
                    brand,
                    model,
                    protocol,
                    transport,
                    device_status,
                    eligibility,
                    eligibility_reason,
                    control_state,
                    desired_percent,
                    desired_updated_at,
                    desired_source,
                    desired_source_priority,
                    last_sent_percent,
                    last_applied_percent,
                    telemetry_confirmed,
                    last_command,
                    last_resolved_value,
                    last_resolved_unit,
                    last_dispatch_outcome,
                    last_dispatch_at,
                    last_error,
                    note
                FROM fleet_device_control_state
                ORDER BY
                    CASE control_state
                        WHEN 'error' THEN 0
                        WHEN 'blocked' THEN 1
                        WHEN 'pending' THEN 2
                        WHEN 'aligned' THEN 3
                        ELSE 4
                    END,
                    name COLLATE NOCASE ASC
                """
            ).fetchall()
        return [self._row_to_device_control_state(row) for row in rows]

    def set_active_power_limit_percent(
        self,
        value: float,
        *,
        source: str,
    ) -> FleetControlState:
        normalized_value = self._normalize_percent(value)
        updated_at = self._utc_now()
        updated = False
        with get_connection() as connection:
            current_row = connection.execute(
                """
                SELECT active_power_limit_percent, updated_source
                FROM fleet_control_state
                WHERE singleton_key = ?
                """,
                (FLEET_CONTROL_SINGLETON_KEY,),
            ).fetchone()
            current_source = None if current_row is None else current_row["updated_source"]
            current_target = (
                None if current_row is None else current_row["active_power_limit_percent"]
            )
            if not self._can_override_source(current_source, source, current_target is not None):
                self._record_rejected_source_locked(
                    connection,
                    source=source,
                    reason=(
                        f"Comando ignorato: la sorgente {source} ha priorita inferiore "
                        f"alla sorgente attiva {current_source}."
                    ),
                )
            elif (
                current_source == source
                and current_target is not None
                and abs(float(current_target) - normalized_value) < 0.051
            ):
                updated = False
            else:
                connection.execute(
                    """
                    UPDATE fleet_control_state
                    SET
                        active_power_limit_percent = ?,
                        updated_at = ?,
                        updated_source = ?,
                        last_rejected_source = NULL,
                        last_rejected_reason = NULL,
                        last_rejected_at = NULL
                    WHERE singleton_key = ?
                    """,
                    (
                        normalized_value,
                        updated_at,
                        source,
                        FLEET_CONTROL_SINGLETON_KEY,
                    ),
                )
                updated = True

        if updated:
            logger.info(
                "Updated fleet active power limit to %.1f%% via %s",
                normalized_value,
                source,
            )
            if source == "api":
                runtime_event_service.record_event(
                    category="setpoint",
                    level="info",
                    title="Setpoint manuale aggiornato",
                    message=f"Target globale impostato a {normalized_value:.1f}% dall'interfaccia operatore.",
                    details={
                        "source": source,
                        "requested_percent": normalized_value,
                    },
                    dedupe_key="fleet-api-setpoint",
                    dedupe_window_seconds=0.5,
                )
        return self.get_state()

    def clear_active_power_limit_percent(self, *, source: str) -> FleetControlState:
        updated_at = self._utc_now()
        cleared = False
        with get_connection() as connection:
            current_row = connection.execute(
                """
                SELECT active_power_limit_percent, updated_source
                FROM fleet_control_state
                WHERE singleton_key = ?
                """,
                (FLEET_CONTROL_SINGLETON_KEY,),
            ).fetchone()
            current_source = None if current_row is None else current_row["updated_source"]
            current_target = (
                None if current_row is None else current_row["active_power_limit_percent"]
            )
            if not self._can_override_source(current_source, source, current_target is not None):
                self._record_rejected_source_locked(
                    connection,
                    source=source,
                    reason=(
                        f"Clear ignorato: la sorgente {source} ha priorita inferiore "
                        f"alla sorgente attiva {current_source}."
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE fleet_control_state
                    SET
                        active_power_limit_percent = NULL,
                        updated_at = ?,
                        updated_source = ?,
                        last_rejected_source = NULL,
                        last_rejected_reason = NULL,
                        last_rejected_at = NULL
                    WHERE singleton_key = ?
                    """,
                    (
                        updated_at,
                        source,
                        FLEET_CONTROL_SINGLETON_KEY,
                    ),
                )
                cleared = True

        if cleared:
            logger.info("Cleared fleet active power limit via %s", source)
            runtime_event_service.record_event(
                category="setpoint",
                level="info",
                title="Setpoint globale azzerato",
                message=f"Il target globale e stato rimosso dalla sorgente {source}.",
                details={"source": source},
                dedupe_key="fleet-clear-setpoint",
                dedupe_window_seconds=0.5,
            )
        return self.get_state()

    def record_dispatch_results(
        self,
        results: list[FleetDeviceDispatchResult],
        *,
        eligible_device_count: int,
    ) -> FleetControlState:
        ok_count = sum(1 for result in results if result.outcome == "ok")
        error_count = sum(1 for result in results if result.outcome == "error")
        skipped_count = sum(1 for result in results if result.outcome in {"pending", "blocked"})
        current_state = self.get_state()
        last_dispatch_at = self._latest_dispatch_timestamp(
            results,
            fallback=current_state.last_dispatch_at,
        )

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE fleet_control_state
                SET
                    last_dispatch_at = ?,
                    last_dispatch_ok_count = ?,
                    last_dispatch_error_count = ?,
                    last_dispatch_skipped_count = ?,
                    eligible_device_count = ?
                WHERE singleton_key = ?
                """,
                (
                    last_dispatch_at,
                    ok_count,
                    error_count,
                    skipped_count,
                    eligible_device_count,
                    FLEET_CONTROL_SINGLETON_KEY,
                ),
            )

        with self._lock:
            self._device_results = {result.device_id: result for result in results}

        return self.get_state()

    def _latest_dispatch_timestamp(
        self,
        results: list[FleetDeviceDispatchResult],
        *,
        fallback: str | None,
    ) -> str | None:
        candidate_timestamps = [
            result.timestamp
            for result in results
            if not bool(result.diagnostics.get("backoff_active", False))
            and result.command is not None
            and result.timestamp is not None
        ]
        if not candidate_timestamps:
            return fallback
        return max(candidate_timestamps)

    def record_eligible_device_count(self, eligible_device_count: int) -> FleetControlState:
        current_state = self.get_state()
        if current_state.eligible_device_count == eligible_device_count:
            return current_state

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE fleet_control_state
                SET eligible_device_count = ?
                WHERE singleton_key = ?
                """,
                (eligible_device_count, FLEET_CONTROL_SINGLETON_KEY),
            )
        return self.get_state()

    def replace_device_control_states(
        self,
        states: list[FleetDeviceControlState],
        *,
        eligible_device_count: int,
    ) -> None:
        with get_connection() as connection:
            if states:
                connection.executemany(
                    """
                    INSERT INTO fleet_device_control_state (
                        device_id,
                        name,
                        brand,
                        model,
                        protocol,
                        transport,
                        device_status,
                        eligibility,
                        eligibility_reason,
                        control_state,
                        desired_percent,
                        desired_updated_at,
                        desired_source,
                        desired_source_priority,
                        last_sent_percent,
                        last_applied_percent,
                        telemetry_confirmed,
                        last_command,
                        last_resolved_value,
                        last_resolved_unit,
                        last_dispatch_outcome,
                        last_dispatch_at,
                        last_error,
                        note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        name = excluded.name,
                        brand = excluded.brand,
                        model = excluded.model,
                        protocol = excluded.protocol,
                        transport = excluded.transport,
                        device_status = excluded.device_status,
                        eligibility = excluded.eligibility,
                        eligibility_reason = excluded.eligibility_reason,
                        control_state = excluded.control_state,
                        desired_percent = excluded.desired_percent,
                        desired_updated_at = excluded.desired_updated_at,
                        desired_source = excluded.desired_source,
                        desired_source_priority = excluded.desired_source_priority,
                        last_sent_percent = excluded.last_sent_percent,
                        last_applied_percent = excluded.last_applied_percent,
                        telemetry_confirmed = excluded.telemetry_confirmed,
                        last_command = excluded.last_command,
                        last_resolved_value = excluded.last_resolved_value,
                        last_resolved_unit = excluded.last_resolved_unit,
                        last_dispatch_outcome = excluded.last_dispatch_outcome,
                        last_dispatch_at = excluded.last_dispatch_at,
                        last_error = excluded.last_error,
                        note = excluded.note
                    """,
                    [
                        (
                            state.device_id,
                            state.name,
                            state.brand,
                            state.model,
                            state.protocol,
                            state.transport,
                            state.device_status,
                            state.eligibility,
                            state.eligibility_reason,
                            state.control_state,
                            state.desired_percent,
                            state.desired_updated_at,
                            state.desired_source,
                            state.desired_source_priority,
                            state.last_sent_percent,
                            state.last_applied_percent,
                            1 if state.telemetry_confirmed else 0,
                            state.last_command,
                            state.last_resolved_value,
                            state.last_resolved_unit,
                            state.last_dispatch_outcome,
                            state.last_dispatch_at,
                            state.last_error,
                            state.note,
                        )
                        for state in states
                    ],
                )
                placeholders = ", ".join("?" for _ in states)
                connection.execute(
                    f"DELETE FROM fleet_device_control_state WHERE device_id NOT IN ({placeholders})",
                    [state.device_id for state in states],
                )
            else:
                connection.execute("DELETE FROM fleet_device_control_state")

            connection.execute(
                """
                UPDATE fleet_control_state
                SET eligible_device_count = ?
                WHERE singleton_key = ?
                """,
                (eligible_device_count, FLEET_CONTROL_SINGLETON_KEY),
            )

    def _initialize_storage(self) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS fleet_control_state (
                    singleton_key TEXT PRIMARY KEY,
                    active_power_limit_percent REAL,
                    updated_at TEXT,
                    updated_source TEXT,
                    last_dispatch_at TEXT,
                    last_dispatch_ok_count INTEGER NOT NULL DEFAULT 0,
                    last_dispatch_error_count INTEGER NOT NULL DEFAULT 0,
                    last_dispatch_skipped_count INTEGER NOT NULL DEFAULT 0,
                    eligible_device_count INTEGER NOT NULL DEFAULT 0,
                    last_rejected_source TEXT,
                    last_rejected_reason TEXT,
                    last_rejected_at TEXT
                )
                """
            )
            self._ensure_column(connection, "fleet_control_state", "last_rejected_source", "TEXT")
            self._ensure_column(connection, "fleet_control_state", "last_rejected_reason", "TEXT")
            self._ensure_column(connection, "fleet_control_state", "last_rejected_at", "TEXT")
            connection.execute(
                """
                INSERT OR IGNORE INTO fleet_control_state (
                    singleton_key,
                    active_power_limit_percent,
                    updated_at,
                    updated_source,
                    last_dispatch_at,
                    last_dispatch_ok_count,
                    last_dispatch_error_count,
                    last_dispatch_skipped_count,
                    eligible_device_count,
                    last_rejected_source,
                    last_rejected_reason,
                    last_rejected_at
                ) VALUES (?, NULL, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL)
                """,
                (FLEET_CONTROL_SINGLETON_KEY,),
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS fleet_device_control_state (
                    device_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    brand TEXT NOT NULL,
                    model TEXT NOT NULL,
                    protocol TEXT NOT NULL,
                    transport TEXT NOT NULL,
                    device_status TEXT NOT NULL,
                    eligibility TEXT NOT NULL,
                    eligibility_reason TEXT,
                    control_state TEXT NOT NULL,
                    desired_percent REAL,
                    desired_updated_at TEXT,
                    desired_source TEXT,
                    desired_source_priority INTEGER NOT NULL DEFAULT 0,
                    last_sent_percent REAL,
                    last_applied_percent REAL,
                    telemetry_confirmed INTEGER NOT NULL DEFAULT 0,
                    last_command TEXT,
                    last_resolved_value REAL,
                    last_resolved_unit TEXT,
                    last_dispatch_outcome TEXT,
                    last_dispatch_at TEXT,
                    last_error TEXT,
                    note TEXT NOT NULL
                )
                """
            )

    def _ensure_column(
        self,
        connection: object,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name in existing_columns:
            return
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )

    def _row_to_state(self, row: object) -> FleetControlState:
        active_power_limit_percent = row["active_power_limit_percent"]
        updated_source = row["updated_source"]
        return FleetControlState(
            active_power_limit_percent=(
                None if active_power_limit_percent is None else float(active_power_limit_percent)
            ),
            updated_at=row["updated_at"],
            updated_source=updated_source,
            last_dispatch_at=row["last_dispatch_at"],
            last_dispatch_ok_count=int(row["last_dispatch_ok_count"]),
            last_dispatch_error_count=int(row["last_dispatch_error_count"]),
            last_dispatch_skipped_count=int(row["last_dispatch_skipped_count"]),
            eligible_device_count=int(row["eligible_device_count"]),
            effective_source_priority=self._source_priority(updated_source),
            last_rejected_source=row["last_rejected_source"],
            last_rejected_reason=row["last_rejected_reason"],
            last_rejected_at=row["last_rejected_at"],
        )

    def _row_to_device_control_state(self, row: object) -> FleetDeviceControlState:
        return FleetDeviceControlState(
            device_id=row["device_id"],
            name=row["name"],
            brand=row["brand"],
            model=row["model"],
            protocol=row["protocol"],
            transport=row["transport"],
            device_status=row["device_status"],
            eligibility=row["eligibility"],
            eligibility_reason=row["eligibility_reason"],
            control_state=row["control_state"],
            desired_percent=(
                None if row["desired_percent"] is None else float(row["desired_percent"])
            ),
            desired_updated_at=row["desired_updated_at"],
            desired_source=row["desired_source"],
            desired_source_priority=int(row["desired_source_priority"] or 0),
            last_sent_percent=(
                None if row["last_sent_percent"] is None else float(row["last_sent_percent"])
            ),
            last_applied_percent=(
                None if row["last_applied_percent"] is None else float(row["last_applied_percent"])
            ),
            telemetry_confirmed=bool(row["telemetry_confirmed"]),
            last_command=row["last_command"],
            last_resolved_value=(
                None
                if row["last_resolved_value"] is None
                else float(row["last_resolved_value"])
            ),
            last_resolved_unit=row["last_resolved_unit"],
            last_dispatch_outcome=row["last_dispatch_outcome"],
            last_dispatch_at=row["last_dispatch_at"],
            last_error=row["last_error"],
            note=row["note"],
        )

    def _normalize_percent(self, value: float) -> float:
        return round(min(max(float(value), 0.0), 100.0), 1)

    def _source_priority(self, source: str | None) -> int:
        if source is None:
            return 0
        return SOURCE_PRIORITIES.get(source, 100)

    def _can_override_source(
        self,
        current_source: str | None,
        requested_source: str,
        has_active_target: bool,
    ) -> bool:
        if not has_active_target or current_source is None or current_source == requested_source:
            return True
        if current_source == "modbus_tcp_slave" and requested_source != "modbus_tcp_slave":
            try:
                if not modbus_tcp_slave_config_service.get_config().cci_enabled:
                    return True
            except Exception:
                pass
        return self._source_priority(requested_source) >= self._source_priority(current_source)

    def _record_rejected_source_locked(
        self,
        connection: object,
        *,
        source: str,
        reason: str,
    ) -> None:
        rejected_at = self._utc_now()
        connection.execute(
            """
            UPDATE fleet_control_state
            SET
                last_rejected_source = ?,
                last_rejected_reason = ?,
                last_rejected_at = ?
            WHERE singleton_key = ?
            """,
            (
                source,
                reason,
                rejected_at,
                FLEET_CONTROL_SINGLETON_KEY,
            ),
        )
        logger.info("%s", reason)
        runtime_event_service.record_event(
            category="setpoint",
            level="warning",
            title="Override setpoint ignorato",
            message=reason,
            details={"source": source},
            dedupe_key=f"fleet-rejected:{source}",
            dedupe_window_seconds=2.0,
        )

    def _utc_now(self) -> str:
        return datetime.now(UTC).isoformat()


fleet_setpoint_service = FleetSetpointService()
