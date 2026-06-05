from __future__ import annotations

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from ipaddress import IPv4Address, ip_address
from threading import Lock
from time import perf_counter, sleep
from uuid import uuid4

from pymodbus import FramerType
from pymodbus.client import ModbusTcpClient

from app.catalog.aurora_catalog import resolve_aurora_candidate_profiles
from app.catalog.inverter_catalog import get_inverter_catalog
from app.models.inverter_model import InverterModel
from app.schemas.device_schemas import DeviceResponse
from app.schemas.protocol_schemas import (
    DeviceDiscoveryRtuRequest,
    DeviceDiscoveryRtuResponse,
    DeviceDiscoveryRtuResult,
    DeviceDiscoveryTcpRequest,
    DeviceDiscoveryTcpResponse,
    DeviceDiscoveryTcpResult,
    DiscoveryCandidateProfile,
    ModbusScanFunction,
    ProtocolOperationStateResponse,
    ProtocolTestRequest,
    ProtocolTestResponse,
    RtuReadRequest,
    RtuReadResponse,
    RtuScanMatch,
    RtuScanRequest,
    RtuScanResponse,
    TcpScanMatch,
    TcpScanRequest,
    TcpScanResponse,
)
from app.services.connection_manager import connection_manager
from app.services.aurora_service import (
    aurora_service,
    extract_aurora_exception_diagnostics,
)
from app.services.delta_rs485_service import delta_rs485_service
from app.services.inverter_io_service import inverter_io_service
from app.services.inverter_profile_resolver import inverter_profile_resolver


MODBUS_RTU_TEST_REGISTER = 0
MODBUS_RTU_TEST_COUNT = 1
MODBUS_RTU_TEST_FUNCTION: ModbusScanFunction = "holding"
MODBUS_RTU_SCAN_COUNT = 1
MODBUS_TCP_TEST_REGISTER = 0
MODBUS_TCP_TEST_COUNT = 1
MODBUS_TCP_TEST_FUNCTION: ModbusScanFunction = "holding"
MODBUS_TCP_SCAN_COUNT = 1
MODBUS_TCP_DISCOVERY_MAX_WORKERS = 16
DISCOVERY_MAX_SUCCESSFUL_PROBES_PER_NODE = 4
DISCOVERY_MAX_NO_RESPONSE_PROBES_PER_NODE = 2
PROTOCOL_OPERATION_STALE_SECONDS = 120.0
RTU_DISCOVERY_PRIORITY_MAX_SECONDS = 180.0
RTU_DISCOVERY_INGETEAM_TIMEOUT_FLOOR_SECONDS = 1.0
RTU_DISCOVERY_INGETEAM_INTER_UNIT_DELAY_SECONDS = 0.1
DELTA_DISCOVERY_REGISTER = 0
AURORA_DISCOVERY_OPCODE = 50


@dataclass(slots=True, frozen=True)
class _ProtocolRule:
    allowed_transports: tuple[str, ...]
    required_settings_by_transport: dict[str, tuple[str, ...]]


@dataclass(slots=True, frozen=True)
class _DiscoveryDescriptor:
    register: int
    function: ModbusScanFunction
    candidate_brands: tuple[str, ...]
    candidate_profiles: tuple[tuple[str, str, str, str], ...]


@dataclass(slots=True)
class _ProtocolOperation:
    operation_id: str
    kind: str
    label: str
    started_at: datetime
    updated_at: datetime
    persistent: bool
    request_count: int = 0
    active_requests: int = 0
    cancel_requested: bool = False


class ProtocolOperationBusyError(RuntimeError):
    def __init__(self, state: ProtocolOperationStateResponse) -> None:
        self.state = state
        label = state.label or state.kind or state.operation_id or "operazione protocollo"
        super().__init__(
            f"Operazione protocollo gia in corso: {label}. Ferma o attendi la fine prima di avviarne un'altra."
        )


class ProtocolOperationCancelledError(RuntimeError):
    pass


PROTOCOL_RULES: dict[str, _ProtocolRule] = {
    "modbus_rtu": _ProtocolRule(
        allowed_transports=("serial", "tcp"),
        required_settings_by_transport={
            "serial": (
                "port",
                "slave_id",
                "baud_rate",
                "parity",
                "stop_bits",
                "byte_size",
                "timeout_seconds",
                "retries",
            ),
            "tcp": ("host", "port", "unit_id", "timeout_seconds", "retries"),
        },
    ),
    "modbus_tcp": _ProtocolRule(
        allowed_transports=("tcp",),
        required_settings_by_transport={
            "tcp": ("host", "port", "unit_id", "timeout_seconds", "retries"),
        },
    ),
    "sunspec": _ProtocolRule(
        allowed_transports=("tcp",),
        required_settings_by_transport={
            "tcp": ("host", "port", "unit_id", "timeout_seconds", "retries"),
        },
    ),
    "aurora": _ProtocolRule(
        allowed_transports=("serial",),
        required_settings_by_transport={
            "serial": (
                "port",
                "address",
                "baud_rate",
                "parity",
                "stop_bits",
                "byte_size",
                "timeout_seconds",
                "retries",
            ),
        },
    ),
    "delta_rs485": _ProtocolRule(
        allowed_transports=("serial",),
        required_settings_by_transport={
            "serial": (
                "port",
                "address",
                "baud_rate",
                "parity",
                "stop_bits",
                "byte_size",
                "timeout_seconds",
                "retries",
            ),
        },
    ),
}


class ProtocolTestService:
    def __init__(self) -> None:
        self._operation_lock = Lock()
        self._active_operation: _ProtocolOperation | None = None
        self._operation_clients: set[object] = set()

    def protocol_operation_state(self) -> ProtocolOperationStateResponse:
        with self._operation_lock:
            self._clear_stale_operation_locked()
            return self._operation_state_locked()

    def cancel_protocol_operation(self, operation_id: str | None = None) -> ProtocolOperationStateResponse:
        clients: list[object] = []
        with self._operation_lock:
            self._clear_stale_operation_locked()
            if self._active_operation is None:
                return self._operation_state_locked()
            if operation_id and self._active_operation.operation_id != operation_id:
                return self._operation_state_locked()
            self._active_operation.cancel_requested = True
            self._active_operation.updated_at = self._now()
            clients = list(self._operation_clients)

        for client in clients:
            try:
                close = getattr(client, "close", None)
                if callable(close):
                    close()
            except Exception:
                continue

        with self._operation_lock:
            self._release_operation_if_idle_locked()
            return self._operation_state_locked()

    def finish_protocol_operation(self, operation_id: str | None = None) -> ProtocolOperationStateResponse:
        with self._operation_lock:
            self._clear_stale_operation_locked()
            if self._active_operation is not None and (
                operation_id is None or self._active_operation.operation_id == operation_id
            ):
                self._active_operation.persistent = False
                self._active_operation.updated_at = self._now()
                self._release_operation_if_idle_locked()
            return self._operation_state_locked()

    @contextmanager
    def _protocol_operation_scope(self, *, operation_id: str | None, kind: str, label: str):
        normalized_operation_id = (operation_id or "").strip() or uuid4().hex
        persistent = bool((operation_id or "").strip())
        with self._operation_lock:
            self._clear_stale_operation_locked()
            if (
                self._active_operation is not None
                and self._active_operation.operation_id != normalized_operation_id
            ):
                raise ProtocolOperationBusyError(self._operation_state_locked())
            if self._active_operation is None:
                now = self._now()
                self._active_operation = _ProtocolOperation(
                    operation_id=normalized_operation_id,
                    kind=kind,
                    label=label,
                    started_at=now,
                    updated_at=now,
                    persistent=persistent,
                )
            elif self._active_operation.cancel_requested:
                raise ProtocolOperationCancelledError("Operazione protocollo in fase di arresto.")
            self._active_operation.persistent = self._active_operation.persistent or persistent
            self._active_operation.request_count += 1
            self._active_operation.active_requests += 1
            self._active_operation.updated_at = self._now()

        try:
            self._raise_if_protocol_operation_cancelled()
            yield
        finally:
            with self._operation_lock:
                if (
                    self._active_operation is not None
                    and self._active_operation.operation_id == normalized_operation_id
                ):
                    self._active_operation.active_requests = max(0, self._active_operation.active_requests - 1)
                    self._active_operation.updated_at = self._now()
                    if not persistent:
                        self._active_operation.persistent = False
                    self._release_operation_if_idle_locked()

    def _operation_state_locked(self) -> ProtocolOperationStateResponse:
        if self._active_operation is None:
            return ProtocolOperationStateResponse(active=False)
        operation = self._active_operation
        return ProtocolOperationStateResponse(
            active=True,
            operation_id=operation.operation_id,
            kind=operation.kind,
            label=operation.label,
            status="cancelling" if operation.cancel_requested else "running",
            started_at=operation.started_at.isoformat(),
            updated_at=operation.updated_at.isoformat(),
            request_count=operation.request_count,
            active_requests=operation.active_requests,
            active_connections=len(self._operation_clients),
            cancel_requested=operation.cancel_requested,
        )

    def _release_operation_if_idle_locked(self) -> None:
        if self._active_operation is None:
            return
        if (
            self._active_operation.active_requests == 0
            and not self._operation_clients
            and (self._active_operation.cancel_requested or not self._active_operation.persistent)
        ):
            self._active_operation = None

    def _clear_stale_operation_locked(self) -> None:
        if self._active_operation is None:
            return
        if self._active_operation.active_requests > 0 or self._operation_clients:
            return
        age_seconds = (self._now() - self._active_operation.updated_at).total_seconds()
        if age_seconds >= PROTOCOL_OPERATION_STALE_SECONDS:
            self._active_operation = None

    def _track_protocol_client(self, client: object) -> None:
        with self._operation_lock:
            if self._active_operation is None:
                return
            self._operation_clients.add(client)
            self._active_operation.updated_at = self._now()

    def _untrack_protocol_client(self, client: object) -> None:
        with self._operation_lock:
            self._operation_clients.discard(client)
            if self._active_operation is not None:
                self._active_operation.updated_at = self._now()
                self._release_operation_if_idle_locked()

    def _protocol_operation_cancel_requested(self) -> bool:
        with self._operation_lock:
            return self._active_operation.cancel_requested if self._active_operation is not None else False

    def _raise_if_protocol_operation_cancelled(self) -> None:
        if self._protocol_operation_cancel_requested():
            raise ProtocolOperationCancelledError("Operazione protocollo annullata dall'operatore.")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _protocol_test_label(payload: ProtocolTestRequest) -> str:
        settings = payload.connection_settings
        if payload.transport == "serial":
            endpoint = str(settings.get("port") or "seriale")
        else:
            host = settings.get("host") or settings.get("ip") or "host"
            port = settings.get("port") or "porta"
            endpoint = f"{host}:{port}"
        return f"Test connessione {payload.protocol} {endpoint}"

    def test_connection(self, payload: ProtocolTestRequest) -> ProtocolTestResponse:
        with self._protocol_operation_scope(
            operation_id=payload.operation_id,
            kind="test_connection",
            label=payload.operation_label or self._protocol_test_label(payload),
        ):
            return self._test_connection(payload)

    def _test_connection(self, payload: ProtocolTestRequest) -> ProtocolTestResponse:
        rule = PROTOCOL_RULES.get(payload.protocol)
        if rule is None:
            return ProtocolTestResponse(
                success=False,
                protocol=payload.protocol,
                transport=payload.transport,
                message="Unsupported protocol for connection test.",
                diagnostics={"stub_mode": False, "stage": "protocol"},
            )

        catalog_model = self._find_catalog_model(payload)
        connection_settings = self._merge_connection_settings(catalog_model, payload)
        required_settings = rule.required_settings_by_transport.get(payload.transport, ())
        missing_settings = self._missing_required_settings(connection_settings, required_settings)

        diagnostics: dict[str, str | int | float | bool] = {
            "stub_mode": False,
            "allowed_transports": ", ".join(rule.allowed_transports),
            "provided_settings_count": len(payload.connection_settings),
            "required_settings_count": len(required_settings),
        }
        if missing_settings:
            diagnostics["missing_settings"] = ", ".join(missing_settings)

        if payload.transport not in rule.allowed_transports:
            return ProtocolTestResponse(
                success=False,
                protocol=payload.protocol,
                transport=payload.transport,
                message="Transport does not match the selected protocol.",
                diagnostics={**diagnostics, "stage": "transport"},
            )

        if missing_settings:
            return ProtocolTestResponse(
                success=False,
                protocol=payload.protocol,
                transport=payload.transport,
                message="Missing connection settings for the selected protocol.",
                diagnostics={**diagnostics, "stage": "settings"},
            )

        if payload.protocol == "delta_rs485":
            return self._test_delta_connection(payload, connection_settings, diagnostics)
        if payload.protocol == "aurora" and catalog_model is None:
            return self._test_aurora_connection(payload, connection_settings, diagnostics)

        if catalog_model is not None:
            return self._test_profile_connection(
                payload=payload,
                catalog_model=catalog_model,
                connection_settings=connection_settings,
                diagnostics=diagnostics,
            )

        return self._test_generic_connection(
            payload=payload,
            connection_settings=connection_settings,
            diagnostics=diagnostics,
        )

    def read_rtu(self, payload: RtuReadRequest) -> RtuReadResponse:
        return self._read_rtu_common(payload)

    def read_rtu_raw(self, payload: RtuReadRequest) -> RtuReadResponse:
        return self._read_rtu_common(payload)

    def scan_rtu(self, payload: RtuScanRequest) -> RtuScanResponse:
        with self._protocol_operation_scope(
            operation_id=payload.operation_id,
            kind="scan_rtu",
            label=payload.operation_label or f"Scan RTU {payload.port}",
        ):
            return self._scan_rtu(payload)

    def _scan_rtu(self, payload: RtuScanRequest) -> RtuScanResponse:
        matches: list[RtuScanMatch] = []
        self._request_rtu_priority_window(
            port=payload.port,
            timeout_seconds=payload.timeout_seconds,
            retries=payload.retries,
            request_count=len(payload.slave_ids) * len(payload.registers),
        )

        def operation(client: object) -> None:
            for slave_id in payload.slave_ids:
                if self._protocol_operation_cancel_requested():
                    break
                for register_address in payload.registers:
                    if self._protocol_operation_cancel_requested():
                        break
                    try:
                        response, _ = self._read_modbus_registers(
                            client=client,
                            function=payload.function,
                            register_address=register_address,
                            count=MODBUS_RTU_SCAN_COUNT,
                            unit_value=slave_id,
                        )
                    except Exception:
                        continue
                    raw_values = self._response_registers(response)
                    if raw_values is None:
                        continue
                    matches.append(
                        RtuScanMatch(
                            slave_id=slave_id,
                            register=register_address,
                            function=payload.function,
                            raw_values=raw_values,
                        )
                    )

        try:
            connection_manager.execute_modbus_rtu(
                port=payload.port,
                baudrate=payload.baud_rate,
                bytesize=payload.byte_size,
                parity=payload.parity,
                stopbits=payload.stop_bits,
                timeout=payload.timeout_seconds,
                retries=payload.retries,
                advanced_options=self._rtu_advanced_options(payload),
                operation=operation,
            )
        except Exception:
            return RtuScanResponse(matches=[])

        matches.sort(key=lambda item: (item.slave_id, item.register, item.function))
        return RtuScanResponse(matches=matches)

    def scan_tcp(self, payload: TcpScanRequest) -> TcpScanResponse:
        with self._protocol_operation_scope(
            operation_id=payload.operation_id,
            kind="scan_tcp",
            label=payload.operation_label or f"Scan TCP {payload.host_start}-{payload.host_end}:{payload.port}",
        ):
            return self._scan_tcp(payload)

    def _scan_tcp(self, payload: TcpScanRequest) -> TcpScanResponse:
        matches: list[TcpScanMatch] = []
        endpoints = [(host, payload.port) for host in self._expand_ipv4_range(payload.host_start, payload.host_end)]

        with ThreadPoolExecutor(max_workers=min(MODBUS_TCP_DISCOVERY_MAX_WORKERS, len(endpoints) or 1)) as executor:
            futures = {
                executor.submit(
                    self._scan_tcp_endpoint,
                    host=host,
                    port=port,
                    unit_ids=payload.unit_ids,
                    registers=payload.registers,
                    function=payload.function,
                    timeout_seconds=payload.timeout_seconds,
                    retries=payload.retries,
                ): (host, port)
                for host, port in endpoints
            }
            for future in as_completed(futures):
                if self._protocol_operation_cancel_requested():
                    break
                try:
                    matches.extend(future.result())
                except Exception:
                    continue

        matches.sort(key=lambda item: (int(ip_address(item.host)), item.port, item.unit_id, item.register))
        return TcpScanResponse(matches=matches)

    def discover_rtu(self, payload: DeviceDiscoveryRtuRequest) -> DeviceDiscoveryRtuResponse:
        with self._protocol_operation_scope(
            operation_id=payload.operation_id,
            kind="discover_rtu",
            label=payload.operation_label or f"Browsing RTU {payload.port}",
        ):
            return self._discover_rtu(payload)

    def _discover_rtu(self, payload: DeviceDiscoveryRtuRequest) -> DeviceDiscoveryRtuResponse:
        started_at = perf_counter()
        request_count = 0
        results: list[DeviceDiscoveryRtuResult] = []
        found_slave_ids: set[int] = set()
        scan_protocol = payload.scan_protocol

        if scan_protocol in {"auto", "modbus_rtu"}:
            self._raise_if_protocol_operation_cancelled()
            modbus_results, modbus_attempts = self._discover_modbus_rtu(payload=payload)
            request_count += modbus_attempts
            results.extend(modbus_results)
            found_slave_ids.update(result.unit_id for result in modbus_results)

        if scan_protocol == "auto":
            self._raise_if_protocol_operation_cancelled()
            delta_results, delta_attempts = self._discover_delta_rtu(
                payload=payload,
                excluded_slave_ids=found_slave_ids,
            )
            request_count += delta_attempts
            results.extend(delta_results)
            found_slave_ids.update(result.unit_id for result in delta_results)

        if scan_protocol in {"auto", "aurora"}:
            self._raise_if_protocol_operation_cancelled()
            aurora_results, aurora_attempts = self._discover_aurora_rtu(
                payload=payload,
                excluded_slave_ids=found_slave_ids,
            )
            request_count += aurora_attempts
            results.extend(aurora_results)

        results.sort(key=lambda item: item.unit_id)
        return DeviceDiscoveryRtuResponse(
            duration_ms=int(round((perf_counter() - started_at) * 1000)),
            request_count=request_count,
            results=results,
        )

    def discover_tcp(self, payload: DeviceDiscoveryTcpRequest) -> DeviceDiscoveryTcpResponse:
        with self._protocol_operation_scope(
            operation_id=payload.operation_id,
            kind="discover_tcp",
            label=payload.operation_label
            or f"Browsing TCP {payload.host_start}-{payload.host_end}:{payload.port_start}-{payload.port_end}",
        ):
            return self._discover_tcp(payload)

    def _discover_tcp(self, payload: DeviceDiscoveryTcpRequest) -> DeviceDiscoveryTcpResponse:
        gateway_protocol_mode = payload.gateway_protocol_mode
        descriptors = self._preferred_discovery_descriptors(
            self._get_discovery_descriptors(
                "serial" if gateway_protocol_mode == "rtu_over_tcp" else "tcp",
                ("modbus_rtu",) if gateway_protocol_mode == "rtu_over_tcp" else ("modbus_tcp", "sunspec"),
            ),
            preferred_brand=payload.preferred_brand,
            preferred_model=payload.preferred_model,
        )
        started_at = perf_counter()
        request_count = 0
        results: list[DeviceDiscoveryTcpResult] = []
        endpoints = [
            (host, port)
            for host in self._expand_ipv4_range(payload.host_start, payload.host_end)
            for port in range(payload.port_start, payload.port_end + 1)
        ]

        with ThreadPoolExecutor(max_workers=min(MODBUS_TCP_DISCOVERY_MAX_WORKERS, len(endpoints) or 1)) as executor:
            futures = {
                executor.submit(
                    self._discover_tcp_endpoint,
                    host=host,
                    port=port,
                    unit_ids=payload.unit_ids,
                    descriptors=descriptors,
                    timeout_seconds=payload.timeout_seconds,
                    retries=payload.retries,
                    framer=FramerType.RTU if gateway_protocol_mode == "rtu_over_tcp" else FramerType.SOCKET,
                ): (host, port)
                for host, port in endpoints
            }
            for future in as_completed(futures):
                if self._protocol_operation_cancel_requested():
                    break
                try:
                    endpoint_results, endpoint_attempts = future.result()
                except Exception:
                    continue
                results.extend(endpoint_results)
                request_count += endpoint_attempts

        results.sort(key=lambda item: (int(ip_address(item.host)), item.port, item.unit_id))
        return DeviceDiscoveryTcpResponse(
            duration_ms=int(round((perf_counter() - started_at) * 1000)),
            request_count=request_count,
            results=results,
        )

    def _read_rtu_common(self, payload: RtuReadRequest) -> RtuReadResponse:
        tx_trace: list[str] = []
        rx_trace: list[str] = []
        connect_ok = False
        unit_argument_style = "not_attempted"
        raw_values: list[int] | None = None
        error: str | None = None
        success = False
        started_at = perf_counter()

        def trace_packet(is_outbound: bool, packet: bytes) -> bytes:
            rendered = packet.hex(" ").upper()
            if is_outbound:
                tx_trace.append(rendered)
            else:
                rx_trace.append(rendered)
            return packet

        def connect_observer(status: bool) -> None:
            nonlocal connect_ok
            connect_ok = status

        def operation(client: object) -> tuple[object, str]:
            return self._read_modbus_registers(
                client=client,
                function=payload.function,
                register_address=payload.register_address,
                count=payload.count,
                unit_value=payload.slave_id,
            )

        self._request_rtu_priority_window(
            port=payload.port,
            timeout_seconds=payload.timeout_seconds,
            retries=payload.retries,
            request_count=1,
        )
        try:
            response, unit_argument_style = connection_manager.execute_modbus_rtu(
                port=payload.port,
                baudrate=payload.baud_rate,
                bytesize=payload.byte_size,
                parity=payload.parity,
                stopbits=payload.stop_bits,
                timeout=payload.timeout_seconds,
                retries=payload.retries,
                advanced_options=self._rtu_advanced_options(payload),
                trace_packet=trace_packet,
                connect_observer=connect_observer,
                operation=operation,
            )
            raw_values = self._response_registers(response)
            success = raw_values is not None
            if not success:
                error = str(response)
        except Exception as exc:
            error = str(exc)

        return RtuReadResponse(
            success=success,
            connect_ok=connect_ok,
            function_used=payload.function,
            register=payload.register_address,
            count=payload.count,
            unit_argument_style=unit_argument_style,
            elapsed_ms=int(round((perf_counter() - started_at) * 1000)),
            tx_trace=tx_trace,
            rx_trace=rx_trace,
            raw_values=raw_values,
            error=error,
        )

    def _test_profile_connection(
        self,
        *,
        payload: ProtocolTestRequest,
        catalog_model: InverterModel,
        connection_settings: dict[str, object],
        diagnostics: dict[str, str | int | float | bool],
    ) -> ProtocolTestResponse:
        test_device = self._build_profile_test_device(
            payload=payload,
            catalog_model=catalog_model,
            connection_settings=connection_settings,
        )
        resolved_model = inverter_profile_resolver.resolve_for_device(test_device)
        if resolved_model is None:
            return ProtocolTestResponse(
                success=False,
                protocol=payload.protocol,
                transport=payload.transport,
                message="Selected model is not available in the inverter catalog.",
                diagnostics={**diagnostics, "stage": "profile"},
            )

        started_at = perf_counter()
        if payload.transport == "serial":
            self._request_rtu_priority_window(
                port=str(connection_settings.get("port", "")),
                timeout_seconds=float(connection_settings.get("timeout_seconds", 3.0)),
                retries=int(connection_settings.get("retries", 0)),
            )
        try:
            telemetry_result = inverter_io_service.read_telemetry(test_device, resolved_model)
        except Exception as exc:
            return ProtocolTestResponse(
                success=False,
                protocol=payload.protocol,
                transport=payload.transport,
                message="Connection test failed for the selected inverter profile.",
                diagnostics={
                    **diagnostics,
                    "stage": self._classify_profile_test_stage(exc),
                    "elapsed_ms": int(round((perf_counter() - started_at) * 1000)),
                },
            )

        return ProtocolTestResponse(
            success=True,
            protocol=payload.protocol,
            transport=payload.transport,
            message="Profile-aware connection test passed.",
            diagnostics={
                **diagnostics,
                "stage": "profile",
                "elapsed_ms": int(round((perf_counter() - started_at) * 1000)),
                "telemetry_values_read": len(telemetry_result.values),
                "unit_argument_style": telemetry_result.unit_argument_style,
            },
        )

    def _test_generic_connection(
        self,
        *,
        payload: ProtocolTestRequest,
        connection_settings: dict[str, object],
        diagnostics: dict[str, str | int | float | bool],
    ) -> ProtocolTestResponse:
        register_address, function = self._generic_probe_defaults(payload.protocol)
        started_at = perf_counter()
        try:
            if payload.protocol in {"modbus_tcp", "sunspec"}:
                raw_values, unit_argument_style = self._generic_tcp_probe(
                    host=str(connection_settings["host"]),
                    port=int(connection_settings["port"]),
                    unit_id=int(connection_settings["unit_id"]),
                    timeout_seconds=float(connection_settings["timeout_seconds"]),
                    retries=int(connection_settings["retries"]),
                    register_address=register_address,
                    function=function,
                )
            elif payload.protocol == "modbus_rtu" and payload.transport == "tcp":
                raw_values, unit_argument_style = self._generic_rtu_over_tcp_probe(
                    host=str(connection_settings["host"]),
                    port=int(connection_settings["port"]),
                    unit_id=int(connection_settings["unit_id"]),
                    timeout_seconds=float(connection_settings["timeout_seconds"]),
                    retries=int(connection_settings["retries"]),
                    register_address=register_address,
                    function=function,
                )
            elif payload.protocol == "modbus_rtu":
                raw_values, unit_argument_style = self._generic_rtu_probe(
                    port=str(connection_settings["port"]),
                    baud_rate=int(connection_settings["baud_rate"]),
                    byte_size=int(connection_settings["byte_size"]),
                    parity=str(connection_settings["parity"]),
                    stop_bits=int(connection_settings["stop_bits"]),
                    timeout_seconds=float(connection_settings["timeout_seconds"]),
                    retries=int(connection_settings["retries"]),
                    slave_id=int(connection_settings["slave_id"]),
                    register_address=register_address,
                    function=function,
                    advanced_options=connection_settings,
                )
            else:
                return ProtocolTestResponse(
                    success=False,
                    protocol=payload.protocol,
                    transport=payload.transport,
                    message="Unsupported protocol for connection test.",
                    diagnostics={**diagnostics, "stage": "protocol"},
                )
        except Exception:
            return ProtocolTestResponse(
                success=False,
                protocol=payload.protocol,
                transport=payload.transport,
                message="Generic connection test failed.",
                diagnostics={
                    **diagnostics,
                    "stage": "generic",
                    "elapsed_ms": int(round((perf_counter() - started_at) * 1000)),
                },
            )

        return ProtocolTestResponse(
            success=True,
            protocol=payload.protocol,
            transport=payload.transport,
            message="Generic connection test passed.",
            diagnostics={
                **diagnostics,
                "stage": "generic",
                "elapsed_ms": int(round((perf_counter() - started_at) * 1000)),
                "probe_register": register_address,
                "probe_function": function,
                "raw_values": ", ".join(str(value) for value in raw_values),
                "unit_argument_style": unit_argument_style,
            },
        )

    def _test_aurora_connection(
        self,
        payload: ProtocolTestRequest,
        connection_settings: dict[str, object],
        diagnostics: dict[str, str | int | float | bool],
    ) -> ProtocolTestResponse:
        started_at = perf_counter()
        self._request_rtu_priority_window(
            port=str(connection_settings.get("port", "")),
            timeout_seconds=float(connection_settings.get("timeout_seconds", 0.5)),
            retries=int(connection_settings.get("retries", 0)),
        )
        try:
            probe_diagnostics = aurora_service.probe_connection(connection_settings)
        except Exception as exc:
            return ProtocolTestResponse(
                success=False,
                protocol=payload.protocol,
                transport=payload.transport,
                message="Aurora connection test failed.",
                diagnostics={
                    **diagnostics,
                    "stage": "aurora_probe",
                    "elapsed_ms": int(round((perf_counter() - started_at) * 1000)),
                    **extract_aurora_exception_diagnostics(exc),
                },
            )

        flattened_diagnostics = {
            key: value
            for key, value in probe_diagnostics.items()
            if isinstance(value, (str, int, float, bool))
        }
        part_number = flattened_diagnostics.get("part_number")
        version_signature = flattened_diagnostics.get("version_signature")
        resolved_profiles = resolve_aurora_candidate_profiles(
            part_number=part_number if isinstance(part_number, str) else None,
            version_signature=version_signature if isinstance(version_signature, str) else None,
        )
        if resolved_profiles:
            flattened_diagnostics["resolved_candidate_count"] = len(resolved_profiles)
        if len(resolved_profiles) == 1:
            resolved_brand, resolved_model, _, _ = resolved_profiles[0]
            flattened_diagnostics["resolved_brand"] = resolved_brand
            flattened_diagnostics["resolved_model"] = resolved_model
        return ProtocolTestResponse(
            success=True,
            protocol=payload.protocol,
            transport=payload.transport,
            message="Aurora connection test passed.",
            diagnostics={
                **diagnostics,
                **flattened_diagnostics,
                "stage": "aurora_probe",
                "elapsed_ms": int(round((perf_counter() - started_at) * 1000)),
            },
        )

    def _test_delta_connection(
        self,
        payload: ProtocolTestRequest,
        connection_settings: dict[str, object],
        diagnostics: dict[str, str | int | float | bool],
    ) -> ProtocolTestResponse:
        expected_variant = None
        catalog_model = self._find_catalog_model(payload)
        if catalog_model is not None:
            raw_variant = catalog_model.defaults.get("delta_variant")
            if isinstance(raw_variant, int):
                expected_variant = raw_variant

        started_at = perf_counter()
        self._request_rtu_priority_window(
            port=str(connection_settings.get("port", "")),
            timeout_seconds=float(connection_settings.get("timeout_seconds", 1.0)),
            retries=int(connection_settings.get("retries", 0)),
        )
        try:
            probe_diagnostics = delta_rs485_service.probe_connection(
                connection_settings,
                expected_variant=expected_variant,
            )
        except Exception:
            return ProtocolTestResponse(
                success=False,
                protocol=payload.protocol,
                transport=payload.transport,
                message="Delta RS485 connection test failed.",
                diagnostics={
                    **diagnostics,
                    "stage": "delta_probe",
                    "elapsed_ms": int(round((perf_counter() - started_at) * 1000)),
                },
            )

        flattened_diagnostics = {
            key: value
            for key, value in probe_diagnostics.items()
            if isinstance(value, (str, int, float, bool))
        }
        return ProtocolTestResponse(
            success=True,
            protocol=payload.protocol,
            transport=payload.transport,
            message="Delta RS485 connection test passed.",
            diagnostics={
                **diagnostics,
                **flattened_diagnostics,
                "stage": "delta_probe",
                "elapsed_ms": int(round((perf_counter() - started_at) * 1000)),
            },
        )

    def _generic_rtu_probe(
        self,
        *,
        port: str,
        baud_rate: int,
        byte_size: int,
        parity: str,
        stop_bits: int,
        timeout_seconds: float,
        retries: int,
        slave_id: int,
        register_address: int,
        function: ModbusScanFunction,
        advanced_options: dict[str, object],
    ) -> tuple[list[int], str]:
        self._request_rtu_priority_window(
            port=port,
            timeout_seconds=timeout_seconds,
            retries=retries,
            request_count=1,
        )

        def operation(client: object) -> tuple[object, str]:
            return self._read_modbus_registers(
                client=client,
                function=function,
                register_address=register_address,
                count=MODBUS_RTU_TEST_COUNT,
                unit_value=slave_id,
            )

        response, unit_argument_style = connection_manager.execute_modbus_rtu(
            port=port,
            baudrate=baud_rate,
            bytesize=byte_size,
            parity=parity,
            stopbits=stop_bits,
            timeout=timeout_seconds,
            retries=retries,
            advanced_options=advanced_options,
            operation=operation,
        )
        raw_values = self._response_registers(response)
        if raw_values is None:
            raise RuntimeError(str(response))
        return raw_values, unit_argument_style

    def _generic_rtu_over_tcp_probe(
        self,
        *,
        host: str,
        port: int,
        unit_id: int,
        timeout_seconds: float,
        retries: int,
        register_address: int,
        function: ModbusScanFunction,
    ) -> tuple[list[int], str]:
        def operation(client: object) -> tuple[object, str]:
            return self._read_modbus_registers(
                client=client,
                function=function,
                register_address=register_address,
                count=MODBUS_RTU_TEST_COUNT,
                unit_value=unit_id,
            )

        response, unit_argument_style = connection_manager.execute_modbus_tcp(
            host=host,
            port=port,
            framer=FramerType.RTU,
            timeout=timeout_seconds,
            retries=retries,
            reset_after_operation=True,
            operation=operation,
        )
        raw_values = self._response_registers(response)
        if raw_values is None:
            raise RuntimeError(str(response))
        return raw_values, unit_argument_style

    def _generic_tcp_probe(
        self,
        *,
        host: str,
        port: int,
        unit_id: int,
        timeout_seconds: float,
        retries: int,
        register_address: int,
        function: ModbusScanFunction,
    ) -> tuple[list[int], str]:
        def operation(client: object) -> tuple[object, str]:
            return self._read_modbus_registers(
                client=client,
                function=function,
                register_address=register_address,
                count=MODBUS_TCP_TEST_COUNT,
                unit_value=unit_id,
            )

        response, unit_argument_style = connection_manager.execute_modbus_tcp(
            host=host,
            port=port,
            timeout=timeout_seconds,
            retries=retries,
            operation=operation,
        )
        raw_values = self._response_registers(response)
        if raw_values is None:
            raise RuntimeError(str(response))
        return raw_values, unit_argument_style

    def _scan_tcp_endpoint(
        self,
        *,
        host: str,
        port: int,
        unit_ids: list[int],
        registers: list[int],
        function: ModbusScanFunction,
        timeout_seconds: float,
        retries: int,
    ) -> list[TcpScanMatch]:
        matches: list[TcpScanMatch] = []
        client = ModbusTcpClient(host=host, port=port, timeout=timeout_seconds, retries=retries)
        self._track_protocol_client(client)
        try:
            if self._protocol_operation_cancel_requested():
                return matches
            if not client.connect():
                return matches
            for unit_id in unit_ids:
                if self._protocol_operation_cancel_requested():
                    break
                for register_address in registers:
                    if self._protocol_operation_cancel_requested():
                        break
                    try:
                        response, _ = self._read_modbus_registers(
                            client=client,
                            function=function,
                            register_address=register_address,
                            count=MODBUS_TCP_SCAN_COUNT,
                            unit_value=unit_id,
                        )
                    except Exception:
                        continue
                    raw_values = self._response_registers(response)
                    if raw_values is None:
                        continue
                    matches.append(
                        TcpScanMatch(
                            host=host,
                            unit_id=unit_id,
                            register=register_address,
                            function=function,
                            raw_values=raw_values,
                        )
                    )
        finally:
            try:
                client.close()
            finally:
                self._untrack_protocol_client(client)
        return matches

    def _discover_tcp_endpoint(
        self,
        *,
        host: str,
        port: int,
        unit_ids: list[int],
        descriptors: tuple[_DiscoveryDescriptor, ...],
        timeout_seconds: float,
        retries: int,
        framer: FramerType,
    ) -> tuple[list[DeviceDiscoveryTcpResult], int]:
        results: list[DeviceDiscoveryTcpResult] = []
        request_count = 0
        client = ModbusTcpClient(
            host=host,
            port=port,
            framer=framer,
            timeout=timeout_seconds,
            retries=retries,
        )
        self._track_protocol_client(client)
        try:
            if self._protocol_operation_cancel_requested():
                return results, request_count
            if not client.connect():
                return results, request_count
            for unit_id in unit_ids:
                if self._protocol_operation_cancel_requested():
                    break
                result, attempts = self._probe_modbus_discovery_unit(
                    client=client,
                    unit_id=unit_id,
                    descriptors=descriptors,
                    builder=lambda descriptor, raw_values, candidate_profiles: DeviceDiscoveryTcpResult(
                        host=host,
                        port=port,
                        unit_id=unit_id,
                        register=descriptor.register,
                        function=descriptor.function,
                        raw_values=raw_values,
                        candidate_brands=self._candidate_brands(candidate_profiles),
                        candidate_profile_count=len(candidate_profiles),
                        candidate_profiles=self._preview_candidate_profiles(candidate_profiles),
                    ),
                )
                request_count += attempts
                if result is not None:
                    results.append(result)
        finally:
            try:
                client.close()
            finally:
                self._untrack_protocol_client(client)
        return results, request_count

    def _probe_modbus_discovery_unit(
        self,
        *,
        client: object,
        unit_id: int,
        descriptors: tuple[_DiscoveryDescriptor, ...],
        builder,
    ) -> tuple[DeviceDiscoveryRtuResult | DeviceDiscoveryTcpResult | None, int]:
        attempts = 0
        successful_hits = 0
        first_hit_descriptor: _DiscoveryDescriptor | None = None
        first_hit_values: list[int] | None = None
        best_hit_descriptor: _DiscoveryDescriptor | None = None
        best_hit_values: list[int] | None = None
        best_candidate_profiles: set[tuple[str, str, str, str]] | None = None
        intersected_profiles: set[tuple[str, str, str, str]] | None = None
        intersection_hit_count = 0
        ambiguity_detected = False
        consecutive_no_response = 0

        for descriptor in descriptors:
            if self._protocol_operation_cancel_requested():
                break
            attempts += 1
            try:
                response, _ = self._read_modbus_registers(
                    client=client,
                    function=descriptor.function,
                    register_address=descriptor.register,
                    count=1,
                    unit_value=unit_id,
                )
            except Exception as exc:
                if self._is_no_response_exception(exc):
                    consecutive_no_response += 1
                    if consecutive_no_response >= DISCOVERY_MAX_NO_RESPONSE_PROBES_PER_NODE:
                        break
                continue

            consecutive_no_response = 0
            raw_values = self._response_registers(response)
            if raw_values is None:
                continue

            descriptor_profiles = set(descriptor.candidate_profiles)
            if first_hit_descriptor is None:
                first_hit_descriptor = descriptor
                first_hit_values = raw_values
            if best_hit_descriptor is None or self._is_more_specific_candidate_set(
                descriptor_profiles,
                best_candidate_profiles,
            ):
                best_hit_descriptor = descriptor
                best_hit_values = raw_values
                best_candidate_profiles = set(descriptor_profiles)

            if intersected_profiles is None:
                intersected_profiles = set(descriptor_profiles)
                intersection_hit_count = 1
            else:
                intersection = intersected_profiles & descriptor_profiles
                if intersection:
                    intersected_profiles = intersection
                    intersection_hit_count += 1
                else:
                    ambiguity_detected = True
                    if intersection_hit_count <= 1:
                        intersected_profiles = None
                        intersection_hit_count = 0

            successful_hits += 1
            resolved_count = len(
                self._resolve_discovery_profiles(
                    intersected_profiles=intersected_profiles,
                    intersection_hit_count=intersection_hit_count,
                    best_candidate_profiles=best_candidate_profiles,
                    fallback_profiles=first_hit_descriptor.candidate_profiles
                    if first_hit_descriptor is not None
                    else (),
                )
            )
            if resolved_count == 1:
                break
            if (
                successful_hits >= DISCOVERY_MAX_SUCCESSFUL_PROBES_PER_NODE
                and not ambiguity_detected
            ):
                break
            if (
                successful_hits >= DISCOVERY_MAX_SUCCESSFUL_PROBES_PER_NODE
                and best_candidate_profiles is not None
                and len(best_candidate_profiles) <= 4
            ):
                break

        if first_hit_descriptor is None or first_hit_values is None:
            return None, attempts

        selected_descriptor = best_hit_descriptor or first_hit_descriptor
        selected_values = best_hit_values or first_hit_values
        resolved_profiles = self._resolve_discovery_profiles(
            intersected_profiles=intersected_profiles,
            intersection_hit_count=intersection_hit_count,
            best_candidate_profiles=best_candidate_profiles,
            fallback_profiles=first_hit_descriptor.candidate_profiles,
        )
        return builder(selected_descriptor, selected_values, resolved_profiles), attempts

    def _is_no_response_exception(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "no response" in message or "timeout" in message or "timed out" in message

    def _discover_modbus_rtu(
        self,
        *,
        payload: DeviceDiscoveryRtuRequest,
    ) -> tuple[list[DeviceDiscoveryRtuResult], int]:
        descriptors = self._preferred_discovery_descriptors(
            self._get_discovery_descriptors("serial"),
            preferred_brand=payload.preferred_brand,
            preferred_model=payload.preferred_model,
        )
        timeout_seconds = self._effective_rtu_discovery_timeout_seconds(payload)
        inter_unit_delay_seconds = self._rtu_discovery_inter_unit_delay_seconds(payload)
        request_count = 0
        results: list[DeviceDiscoveryRtuResult] = []
        if not descriptors:
            return results, request_count

        self._request_rtu_priority_window(
            port=payload.port,
            timeout_seconds=timeout_seconds,
            retries=payload.retries,
            request_count=len(payload.slave_ids) * len(descriptors),
        )

        def operation(client: object) -> None:
            nonlocal request_count
            for index, slave_id in enumerate(payload.slave_ids):
                if self._protocol_operation_cancel_requested():
                    break
                result, attempts = self._probe_modbus_discovery_unit(
                    client=client,
                    unit_id=slave_id,
                    descriptors=descriptors,
                    builder=lambda descriptor, raw_values, candidate_profiles: DeviceDiscoveryRtuResult(
                        port=payload.port,
                        unit_id=slave_id,
                        register=descriptor.register,
                        function=descriptor.function,
                        raw_values=raw_values,
                        candidate_brands=self._candidate_brands(candidate_profiles),
                        candidate_profile_count=len(candidate_profiles),
                        candidate_profiles=self._preview_candidate_profiles(candidate_profiles),
                    ),
                )
                request_count += attempts
                if result is not None:
                    results.append(result)
                if inter_unit_delay_seconds > 0 and index < len(payload.slave_ids) - 1:
                    sleep(inter_unit_delay_seconds)

        try:
            connection_manager.execute_modbus_rtu(
                port=payload.port,
                baudrate=payload.baud_rate,
                bytesize=payload.byte_size,
                parity=payload.parity,
                stopbits=payload.stop_bits,
                timeout=timeout_seconds,
                retries=payload.retries,
                advanced_options=self._rtu_advanced_options(payload),
                operation=operation,
            )
        except Exception:
            return [], request_count

        return results, request_count

    def _discover_delta_rtu(
        self,
        *,
        payload: DeviceDiscoveryRtuRequest,
        excluded_slave_ids: set[int],
    ) -> tuple[list[DeviceDiscoveryRtuResult], int]:
        results: list[DeviceDiscoveryRtuResult] = []
        request_count = 0
        self._request_rtu_priority_window(
            port=payload.port,
            timeout_seconds=payload.timeout_seconds,
            retries=payload.retries,
            request_count=len(payload.slave_ids),
        )
        for slave_id in payload.slave_ids:
            if self._protocol_operation_cancel_requested():
                break
            if slave_id in excluded_slave_ids:
                continue
            request_count += 1
            settings = {
                "port": payload.port,
                "address": slave_id,
                "baud_rate": payload.baud_rate,
                "parity": payload.parity,
                "stop_bits": payload.stop_bits,
                "byte_size": payload.byte_size,
                "timeout_seconds": payload.timeout_seconds,
                "retries": payload.retries,
                **self._rtu_advanced_options(payload),
            }
            try:
                diagnostics = delta_rs485_service.probe_connection(settings)
            except Exception:
                continue
            variant = diagnostics.get("resolved_variant")
            raw_variant = int(variant) if isinstance(variant, (int, float)) else 0
            candidate_profiles = self._delta_candidate_profiles(raw_variant)
            results.append(
                DeviceDiscoveryRtuResult(
                    port=payload.port,
                    unit_id=slave_id,
                    register=DELTA_DISCOVERY_REGISTER,
                    function="holding",
                    raw_values=[raw_variant],
                    candidate_brands=self._candidate_brands(candidate_profiles),
                    candidate_profile_count=len(candidate_profiles),
                    candidate_profiles=self._preview_candidate_profiles(candidate_profiles),
                )
            )
        return results, request_count

    def _discover_aurora_rtu(
        self,
        *,
        payload: DeviceDiscoveryRtuRequest,
        excluded_slave_ids: set[int],
    ) -> tuple[list[DeviceDiscoveryRtuResult], int]:
        results: list[DeviceDiscoveryRtuResult] = []
        request_count = 0
        candidate_profiles = self._aurora_candidate_profiles()
        if not candidate_profiles:
            return results, request_count

        self._request_rtu_priority_window(
            port=payload.port,
            timeout_seconds=payload.timeout_seconds,
            retries=payload.retries,
            request_count=len(payload.slave_ids),
        )

        for slave_id in payload.slave_ids:
            if self._protocol_operation_cancel_requested():
                break
            if slave_id in excluded_slave_ids:
                continue
            request_count += 1
            settings = {
                "port": payload.port,
                "address": slave_id,
                "baud_rate": payload.baud_rate,
                "parity": payload.parity,
                "stop_bits": payload.stop_bits,
                "byte_size": payload.byte_size,
                "timeout_seconds": payload.timeout_seconds,
                "retries": payload.retries,
                **self._rtu_advanced_options(payload),
            }
            try:
                diagnostics = aurora_service.probe_connection(settings)
            except Exception:
                continue
            part_number = diagnostics.get("part_number")
            version_signature = diagnostics.get("version_signature")
            resolved_profiles = resolve_aurora_candidate_profiles(
                part_number=part_number if isinstance(part_number, str) else None,
                version_signature=version_signature if isinstance(version_signature, str) else None,
            )
            candidate_profiles = resolved_profiles or self._aurora_candidate_profiles()
            signature_label = None
            register_address = AURORA_DISCOVERY_OPCODE
            if isinstance(part_number, str) and part_number.strip() != "":
                signature_label = f"Part number Aurora {part_number.strip().upper()}"
                register_address = 52
            elif isinstance(version_signature, str) and version_signature.strip() != "":
                signature_label = f"Firma Aurora {version_signature.strip().upper()}"
                register_address = 58

            raw_values: list[int] = []
            for key in (
                "global_state",
                "inverter_state",
                "dcdc1_state",
                "dcdc2_state",
                "alarm_code",
            ):
                value = diagnostics.get(key)
                if isinstance(value, (int, float)):
                    raw_values.append(int(value))
            if not raw_values:
                raw_values = [0]

            results.append(
                DeviceDiscoveryRtuResult(
                    port=payload.port,
                    unit_id=slave_id,
                    register=register_address,
                    function="holding",
                    raw_values=raw_values,
                    signature_label=signature_label,
                    candidate_brands=self._candidate_brands(candidate_profiles),
                    candidate_profile_count=len(candidate_profiles),
                    candidate_profiles=self._preview_candidate_profiles(candidate_profiles),
                )
            )
        return results, request_count

    def _read_modbus_registers(
        self,
        *,
        client: object,
        function: ModbusScanFunction,
        register_address: int,
        count: int,
        unit_value: int,
    ) -> tuple[object, str]:
        method_name = "read_holding_registers" if function == "holding" else "read_input_registers"
        method = getattr(client, method_name)
        try:
            return method(register_address, count=count, device_id=unit_value), "device_id"
        except TypeError:
            try:
                return method(register_address, count=count, slave=unit_value), "slave"
            except TypeError:
                return method(register_address, count=count), "none"

    def _response_registers(self, response: object) -> list[int] | None:
        is_error = getattr(response, "isError", None)
        if callable(is_error) and is_error():
            return None
        registers = getattr(response, "registers", None)
        if registers is None:
            return None
        return [int(value) for value in registers]

    def _find_catalog_model(self, payload: ProtocolTestRequest) -> InverterModel | None:
        if not payload.brand or not payload.model:
            return None
        return inverter_profile_resolver.find_catalog_model(
            brand=payload.brand,
            model=payload.model,
            protocol=payload.protocol,
            transport=payload.transport,
        )

    def _merge_connection_settings(
        self,
        catalog_model: InverterModel | None,
        payload: ProtocolTestRequest,
    ) -> dict[str, object]:
        merged: dict[str, object] = {}
        if catalog_model is not None:
            merged.update(catalog_model.defaults)
        merged.update(payload.connection_settings)
        return merged

    def _missing_required_settings(
        self,
        settings: dict[str, object],
        required_settings: tuple[str, ...],
    ) -> list[str]:
        missing: list[str] = []
        for key in required_settings:
            value = settings.get(key)
            if value is None:
                missing.append(key)
                continue
            if isinstance(value, str) and value.strip() == "":
                missing.append(key)
        return missing

    def _build_profile_test_device(
        self,
        *,
        payload: ProtocolTestRequest,
        catalog_model: InverterModel,
        connection_settings: dict[str, object],
    ) -> DeviceResponse:
        return DeviceResponse(
            device_id="protocol-test",
            name=f"{catalog_model.brand} {catalog_model.model}",
            brand=catalog_model.brand,
            model=catalog_model.model,
            protocol=payload.protocol,
            transport=payload.transport,
            connection_settings={
                key: value
                for key, value in connection_settings.items()
                if isinstance(value, (str, int, float, bool))
            },
            profile_overrides=payload.profile_overrides,
            status="pending",
            created_at="",
        )

    def _classify_profile_test_stage(self, exc: Exception) -> str:
        message = str(exc).lower()
        if "missing" in message and "settings" in message:
            return "settings"
        if "telemetry profile" in message or "profile" in message:
            return "profile"
        if (
            "connect" in message
            or "timeout" in message
            or "crc" in message
            or "txstate" in message
            or "aurora" in message
        ):
            return "connect"
        return "profile"

    def _generic_probe_defaults(self, protocol: str) -> tuple[int, ModbusScanFunction]:
        if protocol == "modbus_rtu":
            return MODBUS_RTU_TEST_REGISTER, MODBUS_RTU_TEST_FUNCTION
        return MODBUS_TCP_TEST_REGISTER, MODBUS_TCP_TEST_FUNCTION

    def _rtu_advanced_options(
        self,
        payload: RtuReadRequest | RtuScanRequest | DeviceDiscoveryRtuRequest,
    ) -> dict[str, object]:
        return {
            "handle_local_echo": getattr(payload, "handle_local_echo", False),
            "use_rs485_mode": getattr(payload, "use_rs485_mode", False),
            "rs485_rts_level_for_tx": getattr(payload, "rs485_rts_level_for_tx", True),
            "rs485_rts_level_for_rx": getattr(payload, "rs485_rts_level_for_rx", False),
            "rs485_loopback": getattr(payload, "rs485_loopback", False),
            "rs485_delay_before_tx_ms": getattr(payload, "rs485_delay_before_tx_ms", None),
            "rs485_delay_before_rx_ms": getattr(payload, "rs485_delay_before_rx_ms", None),
        }

    def _preferred_discovery_descriptors(
        self,
        descriptors: tuple[_DiscoveryDescriptor, ...],
        *,
        preferred_brand: str | None,
        preferred_model: str | None,
    ) -> tuple[_DiscoveryDescriptor, ...]:
        normalized_brand = self._normalize_discovery_preference(preferred_brand)
        normalized_model = self._normalize_discovery_preference(preferred_model)
        if not normalized_brand and not normalized_model:
            return descriptors

        if normalized_model:
            model_matches = self._filter_discovery_descriptors(
                descriptors,
                preferred_brand=normalized_brand,
                preferred_model=normalized_model,
            )
            if model_matches:
                return model_matches

        if normalized_brand:
            brand_matches = self._filter_discovery_descriptors(
                descriptors,
                preferred_brand=normalized_brand,
                preferred_model=None,
            )
            if brand_matches:
                return brand_matches

        return descriptors

    def _filter_discovery_descriptors(
        self,
        descriptors: tuple[_DiscoveryDescriptor, ...],
        *,
        preferred_brand: str,
        preferred_model: str | None,
    ) -> tuple[_DiscoveryDescriptor, ...]:
        filtered_descriptors: list[_DiscoveryDescriptor] = []
        for descriptor in descriptors:
            profiles = tuple(
                sorted(
                    profile
                    for profile in descriptor.candidate_profiles
                    if self._discovery_profile_matches(
                        profile,
                        preferred_brand=preferred_brand,
                        preferred_model=preferred_model,
                    )
                )
            )
            if not profiles:
                continue
            filtered_descriptors.append(
                _DiscoveryDescriptor(
                    register=descriptor.register,
                    function=descriptor.function,
                    candidate_brands=tuple(sorted({profile[0] for profile in profiles})),
                    candidate_profiles=profiles,
                )
            )
        return tuple(filtered_descriptors)

    def _discovery_profile_matches(
        self,
        profile: tuple[str, str, str, str],
        *,
        preferred_brand: str,
        preferred_model: str | None,
    ) -> bool:
        profile_brand = self._normalize_discovery_preference(profile[0])
        profile_model = self._normalize_discovery_preference(profile[1])
        brand_matches = (
            not preferred_brand
            or preferred_brand == profile_brand
            or preferred_brand in profile_brand
            or profile_brand in preferred_brand
        )
        model_matches = (
            not preferred_model
            or preferred_model == profile_model
            or preferred_model in profile_model
            or profile_model in preferred_model
        )
        return brand_matches and model_matches

    def _effective_rtu_discovery_timeout_seconds(self, payload: DeviceDiscoveryRtuRequest) -> float:
        if not self._is_ingeteam_discovery(payload):
            return payload.timeout_seconds
        return max(payload.timeout_seconds, RTU_DISCOVERY_INGETEAM_TIMEOUT_FLOOR_SECONDS)

    def _rtu_discovery_inter_unit_delay_seconds(self, payload: DeviceDiscoveryRtuRequest) -> float:
        if self._is_ingeteam_discovery(payload):
            return RTU_DISCOVERY_INGETEAM_INTER_UNIT_DELAY_SECONDS
        return 0.0

    def _is_ingeteam_discovery(self, payload: DeviceDiscoveryRtuRequest) -> bool:
        brand = self._normalize_discovery_preference(payload.preferred_brand)
        model = self._normalize_discovery_preference(payload.preferred_model)
        return "ingeteam" in brand or "ingeteam" in model or "ingecon" in model

    def _normalize_discovery_preference(self, value: str | None) -> str:
        return str(value or "").strip().casefold()

    def _request_rtu_priority_window(
        self,
        *,
        port: str,
        timeout_seconds: float,
        retries: int,
        request_count: int = 1,
    ) -> None:
        normalized_port = str(port).strip()
        if not normalized_port:
            return
        estimated_seconds = (
            float(timeout_seconds)
            * max(1, int(retries) + 1)
            * max(1, int(request_count))
            + 3.0
        )
        hold_seconds = max(
            8.0,
            min(
                RTU_DISCOVERY_PRIORITY_MAX_SECONDS,
                estimated_seconds,
            ),
        )
        connection_manager.request_modbus_rtu_priority(
            normalized_port,
            hold_seconds=hold_seconds,
        )

    def _expand_ipv4_range(self, host_start: str, host_end: str) -> list[str]:
        start_ip = self._parse_ipv4(host_start)
        end_ip = self._parse_ipv4(host_end)
        return [str(IPv4Address(value)) for value in range(int(start_ip), int(end_ip) + 1)]

    def _parse_ipv4(self, raw_value: str) -> IPv4Address:
        parsed = ip_address(raw_value)
        if not isinstance(parsed, IPv4Address):
            raise ValueError("Only IPv4 addresses are supported.")
        return parsed

    @lru_cache(maxsize=6)
    def _get_discovery_descriptors(
        self,
        transport: str,
        allowed_protocols: tuple[str, ...] = ("modbus_rtu", "modbus_tcp", "sunspec"),
    ) -> tuple[_DiscoveryDescriptor, ...]:
        grouped: dict[tuple[int, ModbusScanFunction], list[tuple[str, str, str, str]]] = {}
        for inverter_model in get_inverter_catalog():
            if inverter_model.transport != transport:
                continue
            if inverter_model.protocol not in allowed_protocols:
                continue
            test_register = inverter_model.defaults.get("test_register")
            if not isinstance(test_register, int):
                continue
            raw_function = inverter_model.defaults.get("test_function", "holding")
            function: ModbusScanFunction = "input" if raw_function == "input" else "holding"
            grouped.setdefault((test_register, function), []).append(
                (
                    inverter_model.brand,
                    inverter_model.model,
                    inverter_model.protocol,
                    inverter_model.transport,
                )
            )

        descriptors: list[_DiscoveryDescriptor] = []
        for (register, function), profiles in grouped.items():
            ordered_profiles = tuple(sorted(set(profiles)))
            descriptors.append(
                _DiscoveryDescriptor(
                    register=register,
                    function=function,
                    candidate_brands=tuple(sorted({profile[0] for profile in ordered_profiles})),
                    candidate_profiles=ordered_profiles,
                )
            )

        descriptors.sort(
            key=lambda item: (
                len(item.candidate_profiles),
                len(item.candidate_brands),
                0 if item.function == "holding" else 1,
                item.register,
            )
        )
        return tuple(descriptors)

    def _is_more_specific_candidate_set(
        self,
        candidate_profiles: set[tuple[str, str, str, str]],
        current_profiles: set[tuple[str, str, str, str]] | None,
    ) -> bool:
        if current_profiles is None:
            return True

        candidate_key = (
            len(candidate_profiles),
            len({brand for brand, _, _, _ in candidate_profiles}),
            tuple(sorted(candidate_profiles)),
        )
        current_key = (
            len(current_profiles),
            len({brand for brand, _, _, _ in current_profiles}),
            tuple(sorted(current_profiles)),
        )
        return candidate_key < current_key

    def _resolve_discovery_profiles(
        self,
        *,
        intersected_profiles: set[tuple[str, str, str, str]] | None,
        intersection_hit_count: int,
        best_candidate_profiles: set[tuple[str, str, str, str]] | None,
        fallback_profiles: tuple[tuple[str, str, str, str], ...],
    ) -> tuple[tuple[str, str, str, str], ...]:
        if intersected_profiles and intersection_hit_count > 1:
            return tuple(sorted(intersected_profiles))
        if best_candidate_profiles:
            return tuple(sorted(best_candidate_profiles))
        if intersected_profiles:
            return tuple(sorted(intersected_profiles))
        return tuple(sorted(fallback_profiles))

    @lru_cache(maxsize=4)
    def _delta_candidate_profiles(self, variant: int) -> tuple[tuple[str, str, str, str], ...]:
        profiles: list[tuple[str, str, str, str]] = []
        for inverter_model in get_inverter_catalog():
            if inverter_model.protocol != "delta_rs485":
                continue
            raw_variant = inverter_model.defaults.get("delta_variant")
            if isinstance(raw_variant, int) and raw_variant == variant:
                profiles.append(
                    (
                        inverter_model.brand,
                        inverter_model.model,
                        inverter_model.protocol,
                        inverter_model.transport,
                    )
                )
        return tuple(sorted(set(profiles)))

    @lru_cache(maxsize=1)
    def _aurora_candidate_profiles(self) -> tuple[tuple[str, str, str, str], ...]:
        profiles: list[tuple[str, str, str, str]] = []
        for inverter_model in get_inverter_catalog():
            if inverter_model.protocol != "aurora":
                continue
            if inverter_model.brand == "Generic":
                continue
            profiles.append(
                (
                    inverter_model.brand,
                    inverter_model.model,
                    inverter_model.protocol,
                    inverter_model.transport,
                )
            )
        return tuple(sorted(set(profiles)))

    def _preview_candidate_profiles(
        self,
        profiles: tuple[tuple[str, str, str, str], ...],
    ) -> list[DiscoveryCandidateProfile]:
        return [
            DiscoveryCandidateProfile(
                brand=brand,
                model=model,
                protocol=protocol,
                transport=transport,
            )
            for brand, model, protocol, transport in profiles[:12]
        ]

    def _candidate_brands(self, profiles: tuple[tuple[str, str, str, str], ...]) -> list[str]:
        return sorted({brand for brand, _, _, _ in profiles})


protocol_test_service = ProtocolTestService()
