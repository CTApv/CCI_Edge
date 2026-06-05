import json
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from app.database import get_connection
from app.logger import get_logger
from app.schemas.device_schemas import DeviceCreate, DeviceResponse, DeviceUpdate
from app.core.connection_settings import normalize_persisted_connection_settings
from app.services.device_runtime import build_poll_endpoint_key, resolve_runtime_status
from app.services.inverter_profile_resolver import inverter_profile_resolver
from app.services.live_cache import live_cache
from app.services.power_history_service import power_history_service

logger = get_logger("pv_edge_manager.devices")


class DeviceService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._initialize_storage()
        self._devices = self._load_devices()

    def list_devices(self) -> list[DeviceResponse]:
        with self._lock:
            endpoint_counts = self._build_endpoint_device_counts(self._devices)
            return [
                self._with_runtime_status(
                    device,
                    endpoint_device_count=self._endpoint_device_count(
                        device,
                        endpoint_counts,
                    ),
                )
                for device in self._devices
            ]

    def get_device(self, device_id: str) -> DeviceResponse | None:
        with self._lock:
            endpoint_counts = self._build_endpoint_device_counts(self._devices)
            for device in self._devices:
                if device.device_id == device_id:
                    return self._with_runtime_status(
                        device,
                        endpoint_device_count=self._endpoint_device_count(
                            device,
                            endpoint_counts,
                        ),
                    )
        return None

    def _with_runtime_status(
        self,
        device: DeviceResponse,
        *,
        endpoint_device_count: int = 1,
    ) -> DeviceResponse:
        if device.protocol not in {"modbus_tcp", "modbus_rtu", "sunspec", "aurora", "delta_rs485"}:
            return device

        cache_entry = live_cache.get(device.device_id)
        lifecycle = live_cache.get_connection_lifecycle(device.device_id)
        status = resolve_runtime_status(
            device,
            cache_entry,
            lifecycle,
            endpoint_device_count=endpoint_device_count,
        )

        return device.model_copy(update={"status": status})

    def _build_endpoint_device_counts(
        self,
        devices: list[DeviceResponse],
    ) -> dict[tuple[str, str], int]:
        endpoint_counts: dict[tuple[str, str], int] = {}
        for device in devices:
            endpoint = build_poll_endpoint_key(device)
            if endpoint is None:
                continue
            endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1
        return endpoint_counts

    def _endpoint_device_count(
        self,
        device: DeviceResponse,
        endpoint_counts: dict[tuple[str, str], int],
    ) -> int:
        endpoint = build_poll_endpoint_key(device)
        if endpoint is None:
            return 1
        return max(1, endpoint_counts.get(endpoint, 1))

    def _initialize_storage(self) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    brand TEXT NOT NULL,
                    model TEXT NOT NULL,
                    protocol TEXT NOT NULL,
                    transport TEXT NOT NULL,
                    connection_settings TEXT NOT NULL,
                    profile_overrides TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _load_devices(self) -> list[DeviceResponse]:
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
                    connection_settings,
                    profile_overrides,
                    status,
                    created_at
                FROM devices
                ORDER BY created_at ASC
                """
            ).fetchall()

        devices: list[DeviceResponse] = []
        for row in rows:
            try:
                devices.append(self._row_to_device(row))
            except Exception as exc:
                logger.warning(
                    "Skipping invalid persisted device device_id=%s: %s",
                    row["device_id"],
                    exc,
                )
        return devices

    def _row_to_device(self, row: object) -> DeviceResponse:
        protocol = row["protocol"]
        transport = row["transport"]
        connection_settings = normalize_persisted_connection_settings(
            protocol=protocol,
            transport=transport,
            settings=json.loads(row["connection_settings"]),
        )
        return DeviceResponse(
            device_id=row["device_id"],
            name=row["name"],
            brand=row["brand"],
            model=row["model"],
            protocol=protocol,
            transport=transport,
            connection_settings=connection_settings,
            profile_overrides=json.loads(row["profile_overrides"]),
            status=row["status"],
            created_at=row["created_at"],
        )

    def _persist_device(self, device: DeviceResponse) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO devices (
                    device_id,
                    name,
                    brand,
                    model,
                    protocol,
                    transport,
                    connection_settings,
                    profile_overrides,
                    status,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    name = excluded.name,
                    brand = excluded.brand,
                    model = excluded.model,
                    protocol = excluded.protocol,
                    transport = excluded.transport,
                    connection_settings = excluded.connection_settings,
                    profile_overrides = excluded.profile_overrides,
                    status = excluded.status,
                    created_at = excluded.created_at
                """,
                (
                    device.device_id,
                    device.name,
                    device.brand,
                    device.model,
                    device.protocol,
                    device.transport,
                    json.dumps(device.connection_settings),
                    json.dumps(device.profile_overrides),
                    device.status,
                    device.created_at,
                ),
            )

    def _delete_persisted_device(self, device_id: str) -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))

    def _delete_all_persisted_devices(self) -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM devices")

    def _cleanup_deleted_device(self, device_id: str) -> None:
        from app.services.device_command_state_service import device_command_state_service

        cleanup_steps = (
            ("live_cache", lambda: live_cache.delete(device_id)),
            (
                "power_history",
                lambda: power_history_service.delete_device_history(device_id),
            ),
            (
                "device_command_state",
                lambda: device_command_state_service.delete_device_states(device_id),
            ),
        )
        for step_name, step in cleanup_steps:
            try:
                step()
            except Exception as exc:
                logger.warning(
                    "Device cleanup failed after delete device_id=%s step=%s: %s",
                    device_id,
                    step_name,
                    exc,
                )

    def _request_dispatch_refresh(self) -> None:
        from app.services.fleet_dispatch_service import fleet_dispatch_service

        try:
            fleet_dispatch_service.request_dispatch()
        except Exception as exc:
            logger.warning("Device deletion dispatch refresh failed: %s", exc)

    def _ensure_catalog_profile_exists(
        self,
        *,
        brand: str,
        model: str,
        protocol: str,
        transport: str,
    ) -> None:
        if (
            inverter_profile_resolver.find_catalog_model(
                brand=brand,
                model=model,
                protocol=protocol,
                transport=transport,
            )
            is None
        ):
            raise ValueError("Il profilo selezionato non e disponibile nel catalogo inverter.")

    def _ensure_unique_endpoint_unit(
        self,
        candidate: DeviceCreate | DeviceUpdate,
        *,
        exclude_device_id: str | None = None,
    ) -> None:
        candidate_endpoint = self._addressed_endpoint_key(candidate)
        candidate_unit_id = self._addressed_unit_id(candidate.connection_settings)
        if candidate_endpoint is None or candidate_unit_id is None:
            return

        for device in self._devices:
            if exclude_device_id is not None and device.device_id == exclude_device_id:
                continue
            if self._addressed_endpoint_key(device) != candidate_endpoint:
                continue
            if self._addressed_unit_id(device.connection_settings) != candidate_unit_id:
                continue

            endpoint_label = self._format_addressed_endpoint(candidate_endpoint)
            raise ValueError(
                f"Unit ID {candidate_unit_id} gia configurato su {endpoint_label} "
                f"per \"{device.name}\". Usa un ID diverso o un endpoint diverso."
            )

    def _addressed_endpoint_key(self, device: object) -> tuple[str, str] | None:
        protocol = getattr(device, "protocol", None)
        transport = getattr(device, "transport", None)
        if protocol not in {"modbus_rtu", "modbus_tcp", "sunspec"}:
            return None

        connection_settings = getattr(device, "connection_settings", {})
        if not isinstance(connection_settings, dict):
            return None

        if transport == "serial":
            port = str(connection_settings.get("port", "")).strip()
            if not port:
                return None
            return "serial", port

        if transport == "tcp":
            host = str(connection_settings.get("host", "")).strip()
            port = connection_settings.get("port")
            if not host or port in {None, ""}:
                return None
            try:
                normalized_port = int(port)
            except (TypeError, ValueError):
                return None
            return "tcp", f"{host}:{normalized_port}"

        return None

    def _addressed_unit_id(self, connection_settings: dict[str, object]) -> int | None:
        for key in ("unit_id", "slave_id", "address"):
            value = connection_settings.get(key)
            if value in {None, ""}:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        return None

    def _format_addressed_endpoint(self, endpoint: tuple[str, str]) -> str:
        endpoint_type, endpoint_label = endpoint
        return endpoint_label if endpoint_type == "tcp" else f"porta {endpoint_label}"

    def create_device(self, payload: DeviceCreate) -> DeviceResponse:
        self._ensure_catalog_profile_exists(
            brand=payload.brand,
            model=payload.model,
            protocol=payload.protocol,
            transport=payload.transport,
        )
        with self._lock:
            self._ensure_unique_endpoint_unit(payload)
        device = DeviceResponse(
            device_id=str(uuid4()),
            status="pending",
            created_at=datetime.now(UTC).isoformat(),
            **payload.model_dump(),
        )
        self._persist_device(device)
        with self._lock:
            self._devices.append(device)
        live_cache.delete(device.device_id)
        from app.services.fleet_dispatch_service import fleet_dispatch_service

        fleet_dispatch_service.request_dispatch()
        return device

    def update_device(self, device_id: str, payload: DeviceUpdate) -> DeviceResponse | None:
        self._ensure_catalog_profile_exists(
            brand=payload.brand,
            model=payload.model,
            protocol=payload.protocol,
            transport=payload.transport,
        )
        with self._lock:
            self._ensure_unique_endpoint_unit(payload, exclude_device_id=device_id)
            for index, device in enumerate(self._devices):
                if device.device_id == device_id:
                    updated_device = DeviceResponse(
                        device_id=device_id,
                        created_at=device.created_at,
                        **payload.model_dump(),
                    )
                    self._persist_device(updated_device)
                    self._devices[index] = updated_device
                    live_cache.delete(device_id)
                    from app.services.fleet_dispatch_service import fleet_dispatch_service

                    fleet_dispatch_service.request_dispatch()
                    return updated_device
        return None

    def delete_device(self, device_id: str) -> bool:
        with self._lock:
            for index, device in enumerate(self._devices):
                if device.device_id == device_id:
                    self._delete_persisted_device(device_id)
                    del self._devices[index]
                    self._cleanup_deleted_device(device_id)
                    self._request_dispatch_refresh()
                    return True
        return False

    def delete_all_devices(self) -> int:
        with self._lock:
            device_ids = [device.device_id for device in self._devices]
            if not device_ids:
                return 0

            self._delete_all_persisted_devices()
            self._devices = []

        for device_id in device_ids:
            self._cleanup_deleted_device(device_id)

        self._request_dispatch_refresh()
        return len(device_ids)


device_service = DeviceService()
