from collections.abc import Callable
from dataclasses import dataclass, field
import time
from threading import Lock, current_thread
from time import monotonic, perf_counter
from typing import TypeVar

import serial
from pymodbus import FramerType
from pymodbus.client import ModbusSerialClient, ModbusTcpClient
from pymodbus.exceptions import ConnectionException as ModbusConnectionException
from pymodbus.exceptions import ModbusIOException
from serial.rs485 import RS485Settings

T = TypeVar("T")


@dataclass(slots=True)
class TcpConnectionEntry:
    client: ModbusTcpClient
    timeout: float
    retries: int
    framer: FramerType
    trace_packet: Callable[[bool, bytes], bytes] | None = None
    lock: Lock = field(default_factory=Lock)
    last_lock_wait_ms: float | None = None
    average_lock_wait_ms: float | None = None
    last_operation_duration_ms: float | None = None
    average_operation_duration_ms: float | None = None
    last_round_trip_duration_ms: float | None = None
    average_round_trip_duration_ms: float | None = None
    sample_count: int = 0
    lock_owner_thread_name: str | None = None
    lock_acquired_at_monotonic: float = 0.0
    priority_until_monotonic: float = 0.0
    last_command_at_monotonic: float = 0.0


@dataclass(slots=True)
class RtuConnectionEntry:
    lock: Lock = field(default_factory=Lock)
    priority_until_monotonic: float = 0.0
    last_command_at_monotonic: float = 0.0
    client: ModbusSerialClient | None = None
    settings_signature: tuple[object, ...] | None = None
    reconnect_required: bool = False
    last_used_at_monotonic: float = 0.0


@dataclass(slots=True, frozen=True)
class RtuSerialOptions:
    handle_local_echo: bool = False
    use_rs485_mode: bool = False
    rs485_rts_level_for_tx: bool = True
    rs485_rts_level_for_rx: bool = False
    rs485_loopback: bool = False
    rs485_delay_before_tx_ms: float | None = None
    rs485_delay_before_rx_ms: float | None = None


class ConnectionManager:
    def __init__(self) -> None:
        self._registry_lock = Lock()
        self._tcp_clients: dict[tuple[str, int, FramerType], TcpConnectionEntry] = {}
        self._rtu_clients: dict[str, RtuConnectionEntry] = {}

    def execute_modbus_tcp(
        self,
        host: str,
        port: int,
        *,
        framer: FramerType = FramerType.SOCKET,
        timeout: float,
        retries: int,
        trace_packet: Callable[[bool, bytes], bytes] | None = None,
        reset_after_operation: bool = False,
        operation_kind: str = "poll",
        operation: Callable[[ModbusTcpClient], T],
    ) -> T:
        if operation_kind == "command":
            self.request_modbus_tcp_priority(
                host,
                port,
                framer=framer,
                hold_seconds=max(1.0, timeout * max(1, retries + 1) + 0.75),
            )
        entry = self._get_modbus_tcp_entry(
            host=host,
            port=port,
            framer=framer,
            timeout=timeout,
            retries=retries,
        )
        lock_requested_at = perf_counter()
        entry.lock.acquire()
        lock_wait_ms = (perf_counter() - lock_requested_at) * 1000.0
        operation_started_at = perf_counter()
        entry.lock_owner_thread_name = current_thread().name
        entry.lock_acquired_at_monotonic = monotonic()
        try:
            last_error: Exception | None = None
            for _ in range(2):
                client = self._prepare_modbus_tcp_client(
                    entry=entry,
                    host=host,
                    port=port,
                    framer=framer,
                    timeout=timeout,
                    retries=retries,
                    trace_packet=trace_packet,
                )
                try:
                    if not client.is_socket_open() and not client.connect():
                        raise ConnectionError("Unable to connect to Modbus TCP device.")
                    return operation(client)
                except (
                    ConnectionError,
                    OSError,
                    ModbusConnectionException,
                    ModbusIOException,
                ) as exc:
                    last_error = exc
                    self._replace_modbus_tcp_client(
                        entry=entry,
                        host=host,
                        port=port,
                        framer=framer,
                        timeout=timeout,
                        retries=retries,
                        trace_packet=trace_packet,
                    )

            raise ConnectionError("Unable to connect to Modbus TCP device.") from last_error
        finally:
            if reset_after_operation:
                self._replace_modbus_tcp_client(
                    entry=entry,
                    host=host,
                    port=port,
                    framer=framer,
                    timeout=timeout,
                    retries=retries,
                    trace_packet=None,
                )
            operation_duration_ms = (perf_counter() - operation_started_at) * 1000.0
            self._record_modbus_tcp_runtime(
                entry,
                lock_wait_ms=lock_wait_ms,
                operation_duration_ms=operation_duration_ms,
            )
            if operation_kind == "command":
                self.register_modbus_tcp_write(
                    host,
                    port,
                    framer=framer,
                    quiet_seconds=max(0.25, timeout),
                )
            entry.lock_owner_thread_name = None
            entry.lock_acquired_at_monotonic = 0.0
            entry.lock.release()

    def execute_modbus_rtu(
        self,
        port: str,
        baudrate: int,
        bytesize: int,
        parity: str,
        stopbits: int,
        *,
        timeout: float,
        retries: int,
        advanced_options: dict[str, object] | None = None,
        trace_packet: Callable[[bool, bytes], bytes] | None = None,
        connect_observer: Callable[[bool], None] | None = None,
        operation_kind: str = "poll",
        operation: Callable[[ModbusSerialClient], T],
    ) -> T:
        serial_options = self._build_rtu_serial_options(advanced_options)
        settings_signature = self._build_modbus_rtu_settings_signature(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=timeout,
            retries=retries,
            serial_options=serial_options,
            trace_packet=trace_packet,
        )
        if operation_kind == "command":
            self.request_modbus_rtu_priority(
                port,
                hold_seconds=max(1.0, timeout * max(1, retries + 1) + 0.75),
            )
        entry = self._get_modbus_rtu_entry(port=port)
        with entry.lock:
            last_error: Exception | None = None
            try:
                for _ in range(2):
                    client = self._prepare_modbus_rtu_client(
                        entry=entry,
                        port=port,
                        baudrate=baudrate,
                        bytesize=bytesize,
                        parity=parity,
                        stopbits=stopbits,
                        timeout=timeout,
                        retries=retries,
                        serial_options=serial_options,
                        trace_packet=trace_packet,
                        settings_signature=settings_signature,
                    )
                    try:
                        self._ensure_modbus_rtu_client_connected(
                            entry=entry,
                            client=client,
                            serial_options=serial_options,
                            connect_observer=connect_observer,
                        )
                        result = operation(client)
                        entry.last_used_at_monotonic = monotonic()
                        return result
                    except (
                        ConnectionError,
                        OSError,
                        serial.SerialException,
                        ModbusConnectionException,
                        ModbusIOException,
                    ) as exc:
                        last_error = exc
                        self._reset_modbus_rtu_client(entry)
                raise ConnectionError("Unable to connect to Modbus RTU device.") from last_error
            finally:
                if operation_kind == "command":
                    self.register_modbus_rtu_write(port, quiet_seconds=0.9)

    def execute_modbus_rtu_raw(
        self,
        port: str,
        baudrate: int,
        bytesize: int,
        parity: str,
        stopbits: int,
        *,
        timeout: float,
        retries: int,
        raw_request: bytes,
        response_timeout: float,
        expect_response: bool = True,
        advanced_options: dict[str, object] | None = None,
        trace_packet: Callable[[bool, bytes], bytes] | None = None,
        connect_observer: Callable[[bool], None] | None = None,
        operation_kind: str = "command",
        inter_frame_gap_seconds: float = 0.03,
    ) -> bytes:
        serial_options = self._build_rtu_serial_options(advanced_options)
        settings_signature = self._build_modbus_rtu_settings_signature(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            serial_options=serial_options,
            trace_packet=trace_packet,
        )
        if operation_kind == "command":
            self.request_modbus_rtu_priority(
                port,
                hold_seconds=max(
                    1.0,
                    float(response_timeout) + max(float(inter_frame_gap_seconds), 0.01) + 0.75,
                ),
            )

        entry = self._get_modbus_rtu_entry(port=port)
        with entry.lock:
            last_error: Exception | None = None
            try:
                for _ in range(2):
                    client = self._prepare_modbus_rtu_client(
                        entry=entry,
                        port=port,
                        baudrate=baudrate,
                        bytesize=bytesize,
                        parity=parity,
                        stopbits=stopbits,
                        timeout=timeout,
                        retries=retries,
                        serial_options=serial_options,
                        trace_packet=trace_packet,
                        settings_signature=settings_signature,
                    )
                    try:
                        self._ensure_modbus_rtu_client_connected(
                            entry=entry,
                            client=client,
                            serial_options=serial_options,
                            connect_observer=connect_observer,
                        )
                        result = self._exchange_modbus_rtu_raw(
                            client=client,
                            raw_request=raw_request,
                            response_timeout=float(response_timeout),
                            expect_response=expect_response,
                            inter_frame_gap_seconds=inter_frame_gap_seconds,
                        )
                        entry.last_used_at_monotonic = monotonic()
                        return result
                    except (
                        ConnectionError,
                        OSError,
                        serial.SerialException,
                        ModbusConnectionException,
                        ModbusIOException,
                    ) as exc:
                        last_error = exc
                        self._reset_modbus_rtu_client(entry)
                raise ConnectionError("Unable to exchange raw Modbus RTU payload.") from last_error
            finally:
                if operation_kind == "command":
                    self.register_modbus_rtu_write(
                        port,
                        quiet_seconds=max(
                            0.25,
                            float(response_timeout) + max(float(inter_frame_gap_seconds), 0.01),
                        ),
                    )

    def request_modbus_rtu_priority(self, port: str, *, hold_seconds: float = 2.0) -> None:
        if not port:
            return
        deadline = monotonic() + max(0.25, float(hold_seconds))
        with self._registry_lock:
            entry = self._get_or_create_modbus_rtu_entry_locked(port)
            entry.priority_until_monotonic = max(entry.priority_until_monotonic, deadline)

    def register_modbus_rtu_write(self, port: str, *, quiet_seconds: float = 0.9) -> None:
        if not port:
            return
        now = monotonic()
        deadline = now + max(0.25, float(quiet_seconds))
        with self._registry_lock:
            entry = self._get_or_create_modbus_rtu_entry_locked(port)
            entry.last_command_at_monotonic = now
            entry.priority_until_monotonic = max(entry.priority_until_monotonic, deadline)

    def is_modbus_rtu_priority_pending(self, port: str) -> bool:
        if not port:
            return False
        with self._registry_lock:
            entry = self._rtu_clients.get(port)
            if entry is None:
                return False
            remaining = entry.priority_until_monotonic - monotonic()
            if remaining <= 0:
                entry.priority_until_monotonic = 0.0
                return False
            return True

    def request_modbus_tcp_priority(
        self,
        host: str,
        port: int,
        *,
        framer: FramerType = FramerType.SOCKET,
        hold_seconds: float = 2.0,
    ) -> None:
        normalized_host = str(host).strip()
        if not normalized_host:
            return
        deadline = monotonic() + max(0.25, float(hold_seconds))
        with self._registry_lock:
            entry = self._get_or_create_modbus_tcp_entry_locked(
                host=normalized_host,
                port=int(port),
                framer=framer,
                timeout=1.0,
                retries=0,
            )
            entry.priority_until_monotonic = max(entry.priority_until_monotonic, deadline)

    def register_modbus_tcp_write(
        self,
        host: str,
        port: int,
        *,
        framer: FramerType = FramerType.SOCKET,
        quiet_seconds: float = 0.5,
    ) -> None:
        normalized_host = str(host).strip()
        if not normalized_host:
            return
        now = monotonic()
        deadline = now + max(0.25, float(quiet_seconds))
        with self._registry_lock:
            entry = self._get_or_create_modbus_tcp_entry_locked(
                host=normalized_host,
                port=int(port),
                framer=framer,
                timeout=1.0,
                retries=0,
            )
            entry.last_command_at_monotonic = now
            entry.priority_until_monotonic = max(entry.priority_until_monotonic, deadline)

    def is_modbus_tcp_priority_pending(
        self,
        host: str,
        port: int,
        *,
        framer: FramerType = FramerType.SOCKET,
    ) -> bool:
        normalized_host = str(host).strip()
        if not normalized_host:
            return False
        with self._registry_lock:
            entry = self._tcp_clients.get((normalized_host, int(port), framer))
            if entry is None:
                return False
            remaining = entry.priority_until_monotonic - monotonic()
            if remaining <= 0:
                entry.priority_until_monotonic = 0.0
                return False
            return True

    def close_all_rtu_connections(self) -> None:
        with self._registry_lock:
            entries = list(self._rtu_clients.values())
            self._rtu_clients = {}

        for entry in entries:
            self._close_modbus_rtu_client(entry)

    def close_all_tcp_connections(self) -> None:
        with self._registry_lock:
            entries = list(self._tcp_clients.values())
            self._tcp_clients = {}

        for entry in entries:
            try:
                entry.client.close()
            except Exception:
                pass

    def get_modbus_tcp_runtime_snapshots(self) -> list[dict[str, object]]:
        with self._registry_lock:
            entries = list(self._tcp_clients.items())

        snapshots: list[dict[str, object]] = []
        for (host, port, _framer), entry in entries:
            now = monotonic()
            endpoint_label = f"{host}:{port}"
            if entry.framer != FramerType.SOCKET:
                endpoint_label = f"{endpoint_label} [{entry.framer.value}]"
            lock_held_ms = None
            if entry.lock.locked() and entry.lock_acquired_at_monotonic > 0.0:
                lock_held_ms = max(
                    0.0,
                    (monotonic() - entry.lock_acquired_at_monotonic) * 1000.0,
                )
            snapshots.append(
                {
                    "endpoint_type": "tcp",
                    "endpoint_label": endpoint_label,
                    "modbus_framer": entry.framer.value,
                    "last_lock_wait_ms": self._round_metric(entry.last_lock_wait_ms),
                    "average_lock_wait_ms": self._round_metric(entry.average_lock_wait_ms),
                    "last_operation_duration_ms": self._round_metric(
                        entry.last_operation_duration_ms
                    ),
                    "average_operation_duration_ms": self._round_metric(
                        entry.average_operation_duration_ms
                    ),
                    "last_round_trip_duration_ms": self._round_metric(
                        entry.last_round_trip_duration_ms
                    ),
                    "average_round_trip_duration_ms": self._round_metric(
                        entry.average_round_trip_duration_ms
                    ),
                    "tcp_sample_count": int(entry.sample_count),
                    "current_lock_owner_thread_name": entry.lock_owner_thread_name,
                    "current_lock_held_ms": self._round_metric(lock_held_ms),
                    "priority_pending": entry.priority_until_monotonic > now,
                    "priority_remaining_ms": self._round_metric(
                        max(0.0, entry.priority_until_monotonic - now) * 1000.0
                    ),
                    "last_command_age_ms": self._round_metric(
                        (now - entry.last_command_at_monotonic) * 1000.0
                        if entry.last_command_at_monotonic > 0.0
                        else None
                    ),
                }
            )
        return snapshots

    def _get_modbus_tcp_entry(
        self,
        host: str,
        port: int,
        *,
        framer: FramerType,
        timeout: float,
        retries: int,
    ) -> TcpConnectionEntry:
        key = (host, port, framer)
        with self._registry_lock:
            return self._get_or_create_modbus_tcp_entry_locked(
                host=host,
                port=port,
                framer=framer,
                timeout=timeout,
                retries=retries,
            )

    def _get_or_create_modbus_tcp_entry_locked(
        self,
        *,
        host: str,
        port: int,
        framer: FramerType,
        timeout: float,
        retries: int,
    ) -> TcpConnectionEntry:
        key = (host, port, framer)
        entry = self._tcp_clients.get(key)
        if entry is None:
            entry = TcpConnectionEntry(
                client=self._build_modbus_tcp_client(
                    host=host,
                    port=port,
                    framer=framer,
                    timeout=timeout,
                    retries=retries,
                    trace_packet=None,
                ),
                timeout=timeout,
                retries=retries,
                framer=framer,
            )
            self._tcp_clients[key] = entry
        return entry

    def _prepare_modbus_tcp_client(
        self,
        *,
        entry: TcpConnectionEntry,
        host: str,
        port: int,
        framer: FramerType,
        timeout: float,
        retries: int,
        trace_packet: Callable[[bool, bytes], bytes] | None,
    ) -> ModbusTcpClient:
        if (
            entry.timeout != timeout
            or entry.retries != retries
            or entry.framer != framer
            or entry.trace_packet is not trace_packet
        ):
            self._replace_modbus_tcp_client(
                entry=entry,
                host=host,
                port=port,
                framer=framer,
                timeout=timeout,
                retries=retries,
                trace_packet=trace_packet,
            )
        return entry.client

    def _replace_modbus_tcp_client(
        self,
        *,
        entry: TcpConnectionEntry,
        host: str,
        port: int,
        framer: FramerType,
        timeout: float,
        retries: int,
        trace_packet: Callable[[bool, bytes], bytes] | None,
    ) -> None:
        try:
            entry.client.close()
        except Exception:
            pass

        entry.client = self._build_modbus_tcp_client(
            host=host,
            port=port,
            framer=framer,
            timeout=timeout,
            retries=retries,
            trace_packet=trace_packet,
        )
        entry.timeout = timeout
        entry.retries = retries
        entry.framer = framer
        entry.trace_packet = trace_packet

    def _build_modbus_tcp_client(
        self,
        *,
        host: str,
        port: int,
        framer: FramerType,
        timeout: float,
        retries: int,
        trace_packet: Callable[[bool, bytes], bytes] | None = None,
    ) -> ModbusTcpClient:
        kwargs: dict[str, object] = {
            "host": host,
            "port": port,
            "framer": framer,
            "timeout": timeout,
            "retries": retries,
        }
        if trace_packet is not None:
            kwargs["trace_packet"] = trace_packet
        return ModbusTcpClient(**kwargs)

    def _record_modbus_tcp_runtime(
        self,
        entry: TcpConnectionEntry,
        *,
        lock_wait_ms: float,
        operation_duration_ms: float,
    ) -> None:
        round_trip_duration_ms = max(0.0, float(lock_wait_ms)) + max(
            0.0,
            float(operation_duration_ms),
        )
        entry.last_lock_wait_ms = lock_wait_ms
        entry.last_operation_duration_ms = operation_duration_ms
        entry.last_round_trip_duration_ms = round_trip_duration_ms
        entry.sample_count += 1
        entry.average_lock_wait_ms = self._blend_average(
            entry.average_lock_wait_ms,
            lock_wait_ms,
            entry.sample_count,
        )
        entry.average_operation_duration_ms = self._blend_average(
            entry.average_operation_duration_ms,
            operation_duration_ms,
            entry.sample_count,
        )
        entry.average_round_trip_duration_ms = self._blend_average(
            entry.average_round_trip_duration_ms,
            round_trip_duration_ms,
            entry.sample_count,
        )

    def _blend_average(
        self,
        current_average: float | None,
        new_value: float,
        sample_count: int,
    ) -> float:
        if current_average is None or sample_count <= 1:
            return float(new_value)
        return ((current_average * (sample_count - 1)) + float(new_value)) / sample_count

    def _round_metric(self, value: float | None) -> float | None:
        if value is None:
            return None
        return round(float(value), 2)

    def _get_modbus_rtu_entry(self, port: str) -> RtuConnectionEntry:
        with self._registry_lock:
            return self._get_or_create_modbus_rtu_entry_locked(port)

    def _get_or_create_modbus_rtu_entry_locked(self, port: str) -> RtuConnectionEntry:
        entry = self._rtu_clients.get(port)
        if entry is None:
            entry = RtuConnectionEntry()
            self._rtu_clients[port] = entry
        return entry

    def _build_modbus_rtu_settings_signature(
        self,
        *,
        port: str,
        baudrate: int,
        bytesize: int,
        parity: str,
        stopbits: int,
        timeout: float | None = None,
        retries: int | None = None,
        serial_options: RtuSerialOptions,
        trace_packet: Callable[[bool, bytes], bytes] | None,
    ) -> tuple[object, ...]:
        _ = timeout, retries
        return (
            port,
            baudrate,
            bytesize,
            parity.upper(),
            stopbits,
            serial_options.handle_local_echo,
            serial_options.use_rs485_mode,
            serial_options.rs485_rts_level_for_tx,
            serial_options.rs485_rts_level_for_rx,
            serial_options.rs485_loopback,
            serial_options.rs485_delay_before_tx_ms,
            serial_options.rs485_delay_before_rx_ms,
            trace_packet,
        )

    def _prepare_modbus_rtu_client(
        self,
        *,
        entry: RtuConnectionEntry,
        port: str,
        baudrate: int,
        bytesize: int,
        parity: str,
        stopbits: int,
        timeout: float,
        retries: int,
        serial_options: RtuSerialOptions,
        trace_packet: Callable[[bool, bytes], bytes] | None,
        settings_signature: tuple[object, ...],
    ) -> ModbusSerialClient:
        if (
            entry.client is None
            or entry.settings_signature != settings_signature
            or entry.reconnect_required
        ):
            self._close_modbus_rtu_client(entry)
            entry.client = ModbusSerialClient(
                port=port,
                baudrate=baudrate,
                bytesize=bytesize,
                parity=parity.upper(),
                stopbits=stopbits,
                handle_local_echo=serial_options.handle_local_echo,
                timeout=timeout,
                retries=retries,
                trace_packet=trace_packet,
            )
            entry.settings_signature = settings_signature
            entry.reconnect_required = False
        self._apply_modbus_rtu_runtime_params(entry.client, timeout=timeout, retries=retries)
        return entry.client

    def _ensure_modbus_rtu_client_connected(
        self,
        *,
        entry: RtuConnectionEntry,
        client: ModbusSerialClient,
        serial_options: RtuSerialOptions,
        connect_observer: Callable[[bool], None] | None = None,
    ) -> None:
        if self._is_modbus_rtu_client_open(client):
            if connect_observer is not None:
                connect_observer(True)
            return

        connect_ok = client.connect()
        if connect_observer is not None:
            connect_observer(connect_ok)
        if not connect_ok:
            entry.reconnect_required = True
            raise ConnectionError("Unable to connect to Modbus RTU device.")
        self._apply_rtu_serial_options(client, serial_options)

    def _is_modbus_rtu_client_open(self, client: ModbusSerialClient) -> bool:
        socket = getattr(client, "socket", None)
        return bool(socket is not None and getattr(socket, "is_open", False))

    def _reset_modbus_rtu_client(self, entry: RtuConnectionEntry) -> None:
        entry.reconnect_required = True
        self._close_modbus_rtu_client(entry)

    def _close_modbus_rtu_client(self, entry: RtuConnectionEntry) -> None:
        client = entry.client
        entry.client = None
        entry.settings_signature = None
        if client is None:
            return
        try:
            client.close()
        except Exception:
            pass

    def _build_rtu_serial_options(
        self,
        raw_options: dict[str, object] | None,
    ) -> RtuSerialOptions:
        options = raw_options or {}
        return RtuSerialOptions(
            handle_local_echo=self._to_bool(options.get("handle_local_echo", False)),
            use_rs485_mode=self._to_bool(options.get("use_rs485_mode", False)),
            rs485_rts_level_for_tx=self._to_bool(
                options.get("rs485_rts_level_for_tx", True),
                default=True,
            ),
            rs485_rts_level_for_rx=self._to_bool(
                options.get("rs485_rts_level_for_rx", False),
            ),
            rs485_loopback=self._to_bool(options.get("rs485_loopback", False)),
            rs485_delay_before_tx_ms=self._to_optional_float(
                options.get("rs485_delay_before_tx_ms"),
            ),
            rs485_delay_before_rx_ms=self._to_optional_float(
                options.get("rs485_delay_before_rx_ms"),
            ),
        )

    def _apply_rtu_serial_options(
        self,
        client: ModbusSerialClient,
        serial_options: RtuSerialOptions,
    ) -> None:
        if not serial_options.use_rs485_mode:
            return

        socket = getattr(client, "socket", None)
        if socket is None:
            raise RuntimeError("Modbus RTU serial socket is not available for RS485 mode.")

        try:
            socket.rs485_mode = RS485Settings(
                rts_level_for_tx=serial_options.rs485_rts_level_for_tx,
                rts_level_for_rx=serial_options.rs485_rts_level_for_rx,
                loopback=serial_options.rs485_loopback,
                delay_before_tx=self._milliseconds_to_seconds(
                    serial_options.rs485_delay_before_tx_ms,
                ),
                delay_before_rx=self._milliseconds_to_seconds(
                    serial_options.rs485_delay_before_rx_ms,
                ),
            )
        except Exception as exc:
            raise RuntimeError(f"Unable to configure RS485 mode: {exc}") from exc

    def _apply_modbus_rtu_runtime_params(
        self,
        client: ModbusSerialClient,
        *,
        timeout: float,
        retries: int,
    ) -> None:
        normalized_timeout = max(0.01, float(timeout))
        normalized_retries = max(0, int(retries))
        setattr(client, "timeout", normalized_timeout)
        setattr(client, "retries", normalized_retries)

        comm_params = getattr(client, "comm_params", None)
        if comm_params is not None:
            try:
                comm_params.timeout_connect = normalized_timeout
            except Exception:
                pass

        transaction = getattr(client, "transaction", None)
        if transaction is not None:
            try:
                transaction.retries = normalized_retries
            except Exception:
                pass
            transaction_comm_params = getattr(transaction, "comm_params", None)
            if transaction_comm_params is not None:
                try:
                    transaction_comm_params.timeout_connect = normalized_timeout
                except Exception:
                    pass

        socket = getattr(client, "socket", None)
        if socket is not None:
            try:
                socket.timeout = normalized_timeout
            except Exception:
                pass
            try:
                socket.write_timeout = normalized_timeout
            except Exception:
                pass

    def _exchange_modbus_rtu_raw(
        self,
        *,
        client: ModbusSerialClient,
        raw_request: bytes,
        response_timeout: float,
        expect_response: bool,
        inter_frame_gap_seconds: float,
    ) -> bytes:
        socket = getattr(client, "socket", None)
        if socket is None:
            raise ConnectionError("Modbus RTU serial socket is not available.")

        if hasattr(socket, "reset_input_buffer"):
            socket.reset_input_buffer()
        if hasattr(socket, "reset_output_buffer"):
            socket.reset_output_buffer()

        client.send(raw_request)
        if not expect_response:
            return b""

        deadline = monotonic() + max(0.01, float(response_timeout))
        silence_gap = max(0.01, float(inter_frame_gap_seconds))
        last_data_at: float | None = None
        response = bytearray()

        while monotonic() < deadline:
            waiting_bytes = self._safe_serial_in_waiting(socket)
            if waiting_bytes > 0:
                chunk = socket.read(waiting_bytes)
                if chunk:
                    response.extend(chunk)
                    last_data_at = monotonic()
                    continue
            if response and last_data_at is not None and monotonic() - last_data_at >= silence_gap:
                break
            time.sleep(0.005)

        return bytes(response)

    def _safe_serial_in_waiting(self, socket: object) -> int:
        try:
            return int(getattr(socket, "in_waiting", 0) or 0)
        except Exception:
            return 0

    def _to_bool(self, value: object, *, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return bool(value)

    def _to_optional_float(self, value: object) -> float | None:
        if value in {None, ""}:
            return None
        numeric_value = float(value)
        return numeric_value if numeric_value > 0 else None

    def _milliseconds_to_seconds(self, value_ms: float | None) -> float | None:
        if value_ms is None:
            return None
        return value_ms / 1000.0


connection_manager = ConnectionManager()
