from __future__ import annotations

from dataclasses import dataclass
from struct import pack, unpack
from threading import Lock
from time import monotonic, sleep

import serial
from serial.rs485 import RS485Settings

from app.core.connection_settings import (
    get_poll_retry_count,
    get_poll_timeout_seconds,
    get_write_retry_count,
    get_write_timeout_seconds,
)
from app.models.inverter_model import InverterModel, InverterPoint
from app.schemas.device_schemas import DeviceResponse

AURORA_DRIVER = "aurora_protocol"
AuroraDiagnosticValue = str | int | float | bool

TX_OK = 0
OP_GET_STATE = 50
OP_GET_PART_NUMBER = 52
OP_GET_VER = 58
OP_GET_DSP = 59
OP_GET_SYSTEM_PART_NUMBER = 105
OP_SET_PWR_LIMIT = 151

_MAX_REPLY_WINDOW_BYTES = 32
_AURORA_REPLY_STATEFUL = "stateful"
_AURORA_REPLY_ASCII6 = "ascii6"
_AURORA_TX_STATE_LABELS: dict[int, str] = {
    0: "Everything is OK",
    51: "Command is not implemented",
    52: "Variable does not exist",
    53: "Variable value is out of range",
    54: "EEprom not accessible",
    55: "Not toggled service mode",
    56: "Can not send the command to internal micro",
    57: "Command not executed",
    58: "The variable is not available, retry",
}


@dataclass(slots=True, frozen=True)
class _AuroraRequest:
    op: int
    params6: bytes
    reply_format: str = _AURORA_REPLY_STATEFUL


class AuroraProtocolError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        diagnostics: dict[str, AuroraDiagnosticValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def extract_aurora_exception_diagnostics(
    exc: Exception,
) -> dict[str, AuroraDiagnosticValue]:
    diagnostics = getattr(exc, "diagnostics", None)
    if not isinstance(diagnostics, dict):
        return {}
    return {
        str(key): value
        for key, value in diagnostics.items()
        if isinstance(value, (str, int, float, bool))
    }


def describe_aurora_tx_state(code: int) -> str | None:
    return _AURORA_TX_STATE_LABELS.get(int(code))


class AuroraService:
    def __init__(self) -> None:
        self._registry_lock = Lock()
        self._serial_locks: dict[str, Lock] = {}

    def read_points(
        self,
        device: DeviceResponse,
        inverter_model: InverterModel,
        points: list[InverterPoint],
    ) -> dict[str, str | int | float | bool | None]:
        del inverter_model
        port = self._require_port(device.connection_settings)
        lock = self._get_lock(port)
        with lock:
            serial_port = self._open_serial_port(
                device.connection_settings,
                operation_kind="poll",
            )
            try:
                address = self._resolve_address(device.connection_settings)
                raw_values: dict[str, str | int | float | bool | None] = {}
                last_error: Exception | None = None
                issued_request_count = 0

                state_points = [
                    point
                    for point in points
                    if str(point.protocol_meta.get("aurora_method", "")) == "state"
                ]
                if state_points:
                    try:
                        state = self._get_state(
                            serial_port=serial_port,
                            address=address,
                            settings=device.connection_settings,
                        )
                        issued_request_count += 1
                        for point in state_points:
                            field_name = str(point.protocol_meta.get("field", point.key))
                            raw_values[point.key] = state.get(field_name)
                    except Exception as exc:
                        last_error = exc

                dsp_cache: dict[int, float] = {}
                for point in points:
                    if str(point.protocol_meta.get("aurora_method", "")) != "dsp":
                        continue
                    tom = self._resolve_tom(point)
                    if tom is None:
                        continue
                    if tom not in dsp_cache:
                        try:
                            if issued_request_count > 0:
                                self._wait_between_requests(device.connection_settings)
                            dsp_cache[tom] = self._get_dsp(
                                serial_port=serial_port,
                                address=address,
                                tom=tom,
                                settings=device.connection_settings,
                                float_endian=self._resolve_float_endian(device.connection_settings),
                            )
                            issued_request_count += 1
                        except Exception as exc:
                            last_error = exc
                            continue
                    raw_values[point.key] = dsp_cache[tom]

                if raw_values:
                    return {
                        point.key: raw_values.get(point.key)
                        for point in points
                        if point.key in raw_values
                    }
                if last_error is not None:
                    raise last_error
                raise RuntimeError("Aurora telemetry read returned no values.")
            finally:
                serial_port.close()

    def write_point(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> dict[str, str | int | float | bool]:
        if point.key != "active_power_limit":
            raise ValueError(f"Unsupported Aurora command {point.key}.")

        requested_percent = int(round(value))
        if requested_percent < 0 or requested_percent > 100:
            raise ValueError("Aurora active power limit must be between 0 and 100%.")

        port = self._require_port(device.connection_settings)
        lock = self._get_lock(port)
        with lock:
            serial_port = self._open_serial_port(
                device.connection_settings,
                operation_kind="command",
            )
            try:
                address = self._resolve_address(device.connection_settings)
                command_trace = self._set_power_limit(
                    serial_port=serial_port,
                    address=address,
                    percent=requested_percent,
                    settings=device.connection_settings,
                )
            finally:
                serial_port.close()

        return {
            "stub_mode": False,
            "driver": AURORA_DRIVER,
            "protocol": device.protocol,
            "port": port,
            "address": self._resolve_address(device.connection_settings),
            "requested_value": float(value),
            "applied_value": requested_percent,
            **command_trace,
        }

    def probe_connection(
        self,
        settings: dict[str, object],
    ) -> dict[str, str | int | float | bool]:
        port = self._require_port(settings)
        lock = self._get_lock(port)
        with lock:
            serial_port = self._open_serial_port(settings, operation_kind="poll")
            try:
                address = self._resolve_address(settings)
                state = self._get_state(
                    serial_port=serial_port,
                    address=address,
                    settings=settings,
                )
                version: dict[str, str] = {}
                try:
                    self._wait_between_requests(settings)
                    part_number = self._probe_part_number(
                        serial_port=serial_port,
                        address=address,
                        settings=settings,
                    )
                except Exception:
                    part_number = {}
                try:
                    self._wait_between_requests(settings)
                    version = self._probe_version(
                        serial_port=serial_port,
                        address=address,
                        settings=settings,
                    )
                except Exception:
                    version = {}
            finally:
                serial_port.close()

        diagnostics: dict[str, str | int | float | bool] = {
            "driver": AURORA_DRIVER,
            "port": port,
            "address": address,
            "global_state": int(state.get("Global", 0)),
            "inverter_state": int(state.get("InvState", 0)),
            "dcdc1_state": int(state.get("DcDc1", 0)),
            "dcdc2_state": int(state.get("DcDc2", 0)),
            "alarm_code": int(state.get("Alarm", 0)),
        }
        if part_number:
            diagnostics.update(part_number)
        if version:
            diagnostics.update(
                {
                    "model_code": version.get("Model", ""),
                    "grid_code": version.get("Grid", ""),
                    "transformer_code": version.get("Trafo", ""),
                    "application_code": version.get("App", ""),
                    "version_signature": "".join(
                        [
                            version.get("Model", ""),
                            version.get("Grid", ""),
                            version.get("Trafo", ""),
                            version.get("App", ""),
                        ]
                    ),
                }
            )
        return diagnostics

    def _get_lock(self, port: str) -> Lock:
        with self._registry_lock:
            return self._serial_locks.setdefault(port, Lock())

    def _get_state(
        self,
        *,
        serial_port: serial.Serial,
        address: int,
        settings: dict[str, object],
    ) -> dict[str, int]:
        reply, _ = self._execute_request(
            serial_port=serial_port,
            address=address,
            request=_AuroraRequest(op=OP_GET_STATE, params6=b"\x00" * 6),
            settings=settings,
        )
        return {
            "Global": reply[1],
            "InvState": reply[2],
            "DcDc1": reply[3],
            "DcDc2": reply[4],
            "Alarm": reply[5],
        }

    def _get_dsp(
        self,
        *,
        serial_port: serial.Serial,
        address: int,
        tom: int,
        settings: dict[str, object],
        float_endian: str,
    ) -> float:
        reply, _ = self._execute_request(
            serial_port=serial_port,
            address=address,
            request=_AuroraRequest(op=OP_GET_DSP, params6=bytes((tom & 0xFF, 0, 0, 0, 0, 0))),
            settings=settings,
        )
        return float(unpack(f"{float_endian}f", reply[2:6])[0])

    def _probe_version(
        self,
        *,
        serial_port: serial.Serial,
        address: int,
        settings: dict[str, object],
    ) -> dict[str, str]:
        reply, _ = self._execute_request(
            serial_port=serial_port,
            address=address,
            request=_AuroraRequest(op=OP_GET_VER, params6=b"4OWER1"),
            settings=settings,
        )
        return {
            "Model": chr(reply[2]),
            "Grid": chr(reply[3]),
            "Trafo": chr(reply[4]),
            "App": chr(reply[5]),
        }

    def _probe_part_number(
        self,
        *,
        serial_port: serial.Serial,
        address: int,
        settings: dict[str, object],
    ) -> dict[str, str | int]:
        attempts = (
            (OP_GET_PART_NUMBER, "op_52"),
            (OP_GET_SYSTEM_PART_NUMBER, "op_105"),
        )
        last_error: Exception | None = None
        for index, (op, source_label) in enumerate(attempts):
            if index > 0:
                self._wait_between_requests(settings)
            try:
                reply, _ = self._execute_request(
                    serial_port=serial_port,
                    address=address,
                    request=_AuroraRequest(
                        op=op,
                        params6=b"\x00" * 6,
                        reply_format=_AURORA_REPLY_ASCII6,
                    ),
                    settings=settings,
                )
                raw_part_number = self._decode_ascii_reply(reply[:6])
                normalized_part_number = self._normalize_identifier(raw_part_number)
                if normalized_part_number:
                    return {
                        "part_number": normalized_part_number,
                        "part_number_raw": raw_part_number,
                        "part_number_source": source_label,
                    }
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        return {}

    def _set_power_limit(
        self,
        *,
        serial_port: serial.Serial,
        address: int,
        percent: int,
        settings: dict[str, object],
    ) -> dict[str, AuroraDiagnosticValue]:
        scaled = int(round((percent / 100.0) * 32767.0))
        _, diagnostics = self._execute_request(
            serial_port=serial_port,
            address=address,
            request=_AuroraRequest(
                op=OP_SET_PWR_LIMIT,
                params6=bytes((1, 1, (scaled >> 8) & 0xFF, scaled & 0xFF, 0, 3)),
            ),
            settings=settings,
            operation_kind="command",
        )
        return diagnostics

    def _execute_request(
        self,
        *,
        serial_port: serial.Serial,
        address: int,
        request: _AuroraRequest,
        settings: dict[str, object],
        operation_kind: str = "poll",
    ) -> tuple[bytes, dict[str, AuroraDiagnosticValue]]:
        frame = self._build_request_frame(address=address, op=request.op, params6=request.params6)
        retries = (
            get_poll_retry_count(settings, transport="serial")
            if operation_kind == "poll"
            else get_write_retry_count(settings)
        )
        last_error: AuroraProtocolError | None = None
        for attempt in range(retries + 1):
            if attempt > 0:
                self._wait_for_retry(settings)
            try:
                reply, exchange_diagnostics = self._transact_and_parse(
                    serial_port=serial_port,
                    frame=frame,
                    reply_format=request.reply_format,
                    settings=settings,
                    operation_kind=operation_kind,
                )
                return (
                    reply,
                    {
                        "aurora_address": address,
                        "aurora_op": request.op,
                        "aurora_operation": self._operation_name(request.op),
                        "aurora_attempt": attempt + 1,
                        "aurora_retry_budget": retries,
                        "aurora_tx_frame": self._render_trace_bytes(frame),
                        **exchange_diagnostics,
                    },
                )
            except Exception as exc:
                last_error = AuroraProtocolError(
                    str(exc),
                    diagnostics={
                        "aurora_address": address,
                        "aurora_op": request.op,
                        "aurora_operation": self._operation_name(request.op),
                        "aurora_attempt": attempt + 1,
                        "aurora_retry_budget": retries,
                        "aurora_tx_frame": self._render_trace_bytes(frame),
                        **extract_aurora_exception_diagnostics(exc),
                    },
                )
        if last_error is not None:
            raise last_error
        raise RuntimeError("Aurora request failed without an explicit error.")

    def _transact_and_parse(
        self,
        *,
        serial_port: serial.Serial,
        frame: bytes,
        reply_format: str,
        settings: dict[str, object],
        operation_kind: str,
    ) -> tuple[bytes, dict[str, AuroraDiagnosticValue]]:
        try:
            serial_port.reset_input_buffer()
            serial_port.reset_output_buffer()
        except Exception:
            pass

        serial_port.write(frame)
        serial_port.flush()
        sleep(self._resolve_inter_frame_delay_seconds(settings))

        timeout_seconds = (
            get_poll_timeout_seconds(settings, transport="serial", default=0.5)
            if operation_kind == "poll"
            else get_write_timeout_seconds(settings, default=0.5)
        )
        deadline = monotonic() + max(0.05, timeout_seconds)
        buffer = bytearray()
        last_parse_error: Exception | None = None
        while monotonic() < deadline and len(buffer) < _MAX_REPLY_WINDOW_BYTES:
            chunk = serial_port.read(self._next_read_size(serial_port, len(buffer)))
            if chunk:
                buffer.extend(chunk)
                if len(buffer) >= 8:
                    reply, parse_error = self._scan_for_valid_reply(
                        bytes(buffer),
                        reply_format=reply_format,
                    )
                    if reply is not None:
                        return (
                            reply,
                            {
                                "aurora_rx_buffer": self._render_trace_bytes(bytes(buffer)),
                                "aurora_reply_frame": self._render_trace_bytes(reply),
                            },
                        )
                    last_parse_error = parse_error
                    continue
            else:
                if len(buffer) >= 8:
                    break

        if len(buffer) < 8:
            raise AuroraProtocolError(
                f"Aurora timeout: {len(buffer)} bytes",
                diagnostics={
                    "aurora_rx_buffer": self._render_trace_bytes(bytes(buffer)),
                    "aurora_received_bytes": len(buffer),
                },
            )
        if last_parse_error is not None:
            raise AuroraProtocolError(
                str(last_parse_error),
                diagnostics={
                    "aurora_rx_buffer": self._render_trace_bytes(bytes(buffer)),
                    **extract_aurora_exception_diagnostics(last_parse_error),
                },
            )
        raise AuroraProtocolError(
            "Aurora reply parsing failed.",
            diagnostics={"aurora_rx_buffer": self._render_trace_bytes(bytes(buffer))},
        )

    def _scan_for_valid_reply(
        self,
        payload: bytes,
        *,
        reply_format: str,
    ) -> tuple[bytes | None, Exception | None]:
        last_error: Exception | None = None
        for index in range(0, len(payload) - 7):
            candidate = payload[index : index + 8]
            try:
                return self._parse_reply(candidate, reply_format=reply_format), None
            except Exception as exc:
                last_error = exc
        return None, last_error

    def _build_request_frame(self, *, address: int, op: int, params6: bytes) -> bytes:
        if len(params6) != 6:
            raise ValueError("Aurora requests require exactly 6 parameter bytes.")
        frame = bytearray(10)
        frame[0] = address & 0xFF
        frame[1] = op & 0xFF
        frame[2:8] = params6
        crc = self._crc16_ccitt_reflected(bytes(frame[:8]))
        frame[8] = crc & 0xFF
        frame[9] = (crc >> 8) & 0xFF
        return bytes(frame)

    def _parse_reply(self, payload: bytes, *, reply_format: str) -> bytes:
        if len(payload) != 8:
            raise AuroraProtocolError(
                f"Aurora timeout: {len(payload)} bytes",
                diagnostics={
                    "aurora_reply_frame": self._render_trace_bytes(payload),
                    "aurora_received_bytes": len(payload),
                },
            )
        crc_expected = self._crc16_ccitt_reflected(payload[:6])
        crc_received = payload[6] | (payload[7] << 8)
        if crc_expected != crc_received:
            raise AuroraProtocolError(
                "Aurora CRC mismatch",
                diagnostics={
                    "aurora_reply_frame": self._render_trace_bytes(payload),
                    "aurora_reply_tx_state": int(payload[0]),
                    "aurora_crc_expected": int(crc_expected),
                    "aurora_crc_received": int(crc_received),
                },
            )
        if reply_format == _AURORA_REPLY_ASCII6:
            return payload
        if payload[0] != TX_OK:
            tx_state_label = describe_aurora_tx_state(int(payload[0]))
            diagnostics: dict[str, AuroraDiagnosticValue] = {
                "aurora_reply_frame": self._render_trace_bytes(payload),
                "aurora_reply_tx_state": int(payload[0]),
                "aurora_crc_expected": int(crc_expected),
                "aurora_crc_received": int(crc_received),
            }
            if tx_state_label:
                diagnostics["aurora_reply_tx_state_label"] = tx_state_label
            raise AuroraProtocolError(
                f"Aurora TxState={payload[0]}",
                diagnostics=diagnostics,
            )
        return payload

    def _crc16_ccitt_reflected(self, data: bytes) -> int:
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0x8408
                else:
                    crc >>= 1
        return (~crc) & 0xFFFF

    def _next_read_size(self, serial_port: serial.Serial, current_size: int) -> int:
        remaining = max(1, _MAX_REPLY_WINDOW_BYTES - current_size)
        try:
            waiting = int(getattr(serial_port, "in_waiting", 0) or 0)
        except Exception:
            waiting = 0
        return max(1, min(remaining, waiting or 1))

    def _resolve_tom(self, point: InverterPoint) -> int | None:
        raw_value = point.protocol_meta.get("tom", point.address)
        if not isinstance(raw_value, int):
            return None
        if raw_value < 0 or raw_value > 255:
            raise ValueError(f"Aurora ToM {raw_value} is out of range.")
        return raw_value

    def _resolve_float_endian(self, settings: dict[str, object]) -> str:
        raw_value = str(settings.get("float_endian", ">")).strip()
        if raw_value not in {">", "<"}:
            raise ValueError("Aurora float_endian must be '>' or '<'.")
        return raw_value

    def _open_serial_port(
        self,
        settings: dict[str, object],
        *,
        operation_kind: str,
    ) -> serial.Serial:
        timeout_seconds = (
            get_poll_timeout_seconds(settings, transport="serial", default=0.5)
            if operation_kind == "poll"
            else get_write_timeout_seconds(settings, default=0.5)
        )
        serial_port = serial.Serial(
            port=self._require_port(settings),
            baudrate=int(settings.get("baud_rate", 19200)),
            bytesize=int(settings.get("byte_size", 8)),
            parity=str(settings.get("parity", "N")),
            stopbits=int(settings.get("stop_bits", 1)),
            timeout=min(max(timeout_seconds, 0.05), 0.1),
            write_timeout=max(timeout_seconds, 0.1),
        )
        if self._to_bool(settings.get("use_rs485_mode", False)):
            serial_port.rs485_mode = RS485Settings(
                rts_level_for_tx=self._to_bool(
                    settings.get("rs485_rts_level_for_tx", True),
                    default=True,
                ),
                rts_level_for_rx=self._to_bool(settings.get("rs485_rts_level_for_rx", False)),
                loopback=self._to_bool(settings.get("rs485_loopback", False)),
                delay_before_tx=self._milliseconds_to_seconds(
                    settings.get("rs485_delay_before_tx_ms")
                ),
                delay_before_rx=self._milliseconds_to_seconds(
                    settings.get("rs485_delay_before_rx_ms")
                ),
            )
        return serial_port

    def _wait_between_requests(self, settings: dict[str, object]) -> None:
        delay_ms = settings.get("inter_request_delay_ms", 20)
        if delay_ms in {None, ""}:
            return
        delay_seconds = float(delay_ms) / 1000.0
        if delay_seconds > 0:
            sleep(delay_seconds)

    def _wait_for_retry(self, settings: dict[str, object]) -> None:
        retry_delay_ms = settings.get("retry_delay_ms", 40)
        if retry_delay_ms in {None, ""}:
            return
        delay_seconds = float(retry_delay_ms) / 1000.0
        if delay_seconds > 0:
            sleep(delay_seconds)

    def _resolve_inter_frame_delay_seconds(self, settings: dict[str, object]) -> float:
        delay_ms = settings.get("inter_request_delay_ms", 20)
        if delay_ms in {None, ""}:
            return 0.02
        return max(0.0, float(delay_ms) / 1000.0)

    def _require_port(self, settings: dict[str, object]) -> str:
        port = str(settings.get("port", "")).strip()
        if not port:
            raise ValueError("Missing Aurora serial port in connection settings.")
        return port

    def _resolve_address(self, settings: dict[str, object]) -> int:
        raw_value = settings.get("address", settings.get("slave_id", 1))
        address = int(raw_value)
        if address < 0 or address > 247:
            raise ValueError("Aurora address must be between 0 and 247.")
        return address

    def _milliseconds_to_seconds(self, raw_value: object) -> float | None:
        if raw_value in {None, ""}:
            return None
        return max(0.0, float(raw_value) / 1000.0)

    def _to_bool(self, raw_value: object, *, default: bool = False) -> bool:
        if raw_value is None:
            return default
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, (int, float)):
            return bool(raw_value)
        if isinstance(raw_value, str):
            return raw_value.strip().lower() in {"1", "true", "yes", "on"}
        return default

    def _render_trace_bytes(self, payload: bytes) -> str:
        if not payload:
            return "(empty)"
        return payload.hex(" ").upper()

    def _decode_ascii_reply(self, payload: bytes) -> str:
        return "".join(chr(byte) if 32 <= byte <= 126 else " " for byte in payload).strip()

    def _normalize_identifier(self, value: str) -> str:
        return value.strip().strip("-").strip().upper()

    def _operation_name(self, op: int) -> str:
        if op == OP_GET_STATE:
            return "get_state"
        if op == OP_GET_PART_NUMBER:
            return "get_part_number"
        if op == OP_GET_VER:
            return "probe_version"
        if op == OP_GET_DSP:
            return "get_dsp"
        if op == OP_GET_SYSTEM_PART_NUMBER:
            return "get_system_part_number"
        if op == OP_SET_PWR_LIMIT:
            return "set_power_limit"
        return f"op_{op}"


aurora_service = AuroraService()
