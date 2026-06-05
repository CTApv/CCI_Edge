from __future__ import annotations

from dataclasses import dataclass
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

DELTA_RS485_DRIVER = "delta_si_rs485"

_STX = 0x02
_ENQ = 0x05
_ACK = 0x06
_NAK = 0x15
_ETX = 0x03

_IDENTIFY_COMMAND = 0
_IDENTIFY_SUBCOMMAND = 0
_MEASUREMENT_COMMAND = 96
_MEASUREMENT_SUBCOMMAND = 1
_ACTIVE_POWER_LIMIT_COMMAND = 13
_ACTIVE_POWER_LIMIT_SUBCOMMAND = 136

_SUPPORTED_VARIANTS = {1, 3, 4}
_VARIANT_FAMILY_MAP = {
    1: "SI 2500",
    3: "SI 3300",
    4: "SI 5000",
}


@dataclass(slots=True, frozen=True)
class DeltaIdentification:
    variant: int | None = None
    model_name: str = ""


class DeltaRs485Service:
    def __init__(self) -> None:
        self._registry_lock = Lock()
        self._serial_locks: dict[str, Lock] = {}

    def read_points(
        self,
        device: DeviceResponse,
        inverter_model: InverterModel,
        points: list[InverterPoint],
    ) -> dict[str, str | int | float | bool | None]:
        port = self._require_port(device.connection_settings)
        lock = self._get_lock(port)
        with lock:
            serial_port = self._open_serial_port(
                device.connection_settings,
                operation_kind="poll",
            )
            try:
                address = self._resolve_address(device.connection_settings)
                identification = self._identify_device(
                    serial_port=serial_port,
                    address=address,
                    settings=device.connection_settings,
                )
                self._wait_between_requests(device.connection_settings)
                variant = self._resolve_variant(
                    settings=device.connection_settings,
                    inverter_model=inverter_model,
                    identification=identification,
                )
                payload = self._execute_standard_command(
                    serial_port=serial_port,
                    address=address,
                    command=_MEASUREMENT_COMMAND,
                    subcommand=_MEASUREMENT_SUBCOMMAND,
                    data=b"",
                    settings=device.connection_settings,
                    operation_kind="poll",
                )
            finally:
                serial_port.close()

        raw_values = self._decode_measurement_payload(variant, payload)
        raw_values["delta_variant"] = identification.variant or variant
        raw_values["identified_model_name"] = (
            identification.model_name or _VARIANT_FAMILY_MAP.get(variant, "Delta SI")
        )
        raw_values["family_model"] = _VARIANT_FAMILY_MAP.get(variant, "Delta SI")
        raw_values["variant_mismatch"] = (
            1
            if identification.variant is not None
            and identification.variant in _SUPPORTED_VARIANTS
            and identification.variant != variant
            else 0
        )
        return {
            point.key: raw_values.get(point.key)
            for point in points
            if point.key in raw_values
        }

    def write_point(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> dict[str, str | int | float | bool]:
        if point.key != "active_power_limit":
            raise ValueError(f"Unsupported Delta RS485 command {point.key}.")

        requested_value = int(round(value))
        if requested_value < 0 or requested_value > 100:
            raise ValueError("Delta active power limit must be between 0 and 100%.")

        port = self._require_port(device.connection_settings)
        lock = self._get_lock(port)
        with lock:
            serial_port = self._open_serial_port(
                device.connection_settings,
                operation_kind="command",
            )
            try:
                address = self._resolve_address(device.connection_settings)
                response_data = self._execute_standard_command(
                    serial_port=serial_port,
                    address=address,
                    command=int(point.protocol_meta.get("command_code", _ACTIVE_POWER_LIMIT_COMMAND)),
                    subcommand=int(
                        point.protocol_meta.get("subcommand", _ACTIVE_POWER_LIMIT_SUBCOMMAND)
                    ),
                    data=bytes((requested_value & 0xFF,)),
                    settings=device.connection_settings,
                    operation_kind="command",
                )
            finally:
                serial_port.close()

        applied_value = response_data[0] if response_data else requested_value
        return {
            "stub_mode": False,
            "driver": DELTA_RS485_DRIVER,
            "protocol": device.protocol,
            "port": port,
            "address": self._resolve_address(device.connection_settings),
            "requested_value": requested_value,
            "applied_value": applied_value,
        }

    def probe_connection(
        self,
        settings: dict[str, object],
        *,
        expected_variant: int | None = None,
    ) -> dict[str, str | int | float | bool]:
        port = self._require_port(settings)
        lock = self._get_lock(port)
        with lock:
            serial_port = self._open_serial_port(settings, operation_kind="poll")
            try:
                address = self._resolve_address(settings)
                identification = self._identify_device(
                    serial_port=serial_port,
                    address=address,
                    settings=settings,
                )
                self._wait_between_requests(settings)
                variant = identification.variant or expected_variant
                if variant is None:
                    raise ValueError(
                        "Delta probe could not determine the inverter variant. "
                        "Select a catalog model or set delta_variant in connection settings."
                    )
                if variant not in _SUPPORTED_VARIANTS:
                    raise NotImplementedError(
                        f"Delta variant {variant} is not supported by the SI family driver."
                    )
                payload = self._execute_standard_command(
                    serial_port=serial_port,
                    address=address,
                    command=_MEASUREMENT_COMMAND,
                    subcommand=_MEASUREMENT_SUBCOMMAND,
                    data=b"",
                    settings=settings,
                    operation_kind="poll",
                )
            finally:
                serial_port.close()

        decoded = self._decode_measurement_payload(variant, payload)
        return {
            "resolved_variant": identification.variant or variant,
            "family_model": _VARIANT_FAMILY_MAP.get(variant, "Delta SI"),
            "identified_model_name": identification.model_name
            or _VARIANT_FAMILY_MAP.get(variant, "Delta SI"),
            "serial_number": str(decoded.get("sap_serial_number", "")),
            "part_number": str(decoded.get("sap_part_number", "")),
            "payload_bytes": len(payload),
        }

    def _get_lock(self, port: str) -> Lock:
        with self._registry_lock:
            return self._serial_locks.setdefault(port, Lock())

    def _identify_device(
        self,
        *,
        serial_port: serial.Serial,
        address: int,
        settings: dict[str, object],
    ) -> DeltaIdentification:
        request_frame = self._build_request_frame(
            address=address,
            command=_IDENTIFY_COMMAND,
            subcommand=_IDENTIFY_SUBCOMMAND,
            data=b"",
        )
        serial_port.reset_input_buffer()
        serial_port.reset_output_buffer()
        serial_port.write(request_frame)
        serial_port.flush()
        response = self._read_identification_response(
            serial_port=serial_port,
            request_frame=request_frame,
            timeout_seconds=get_poll_timeout_seconds(settings, transport="serial", default=1.0),
            handle_local_echo=self._to_bool(settings.get("handle_local_echo", False)),
        )
        if not response:
            return DeltaIdentification()
        first_byte = response[0]
        if first_byte == _NAK:
            raise ValueError("Delta identification command rejected by the inverter.")
        if first_byte == _ACK:
            variant = response[1] if len(response) > 1 else None
            model_name = self._decode_ascii_bytes(response[2:]).strip(" ,")
            return DeltaIdentification(variant=variant, model_name=model_name)
        if first_byte == _STX:
            payload = self._parse_standard_frame(
                frame=response,
                address=address,
                expected_command=_IDENTIFY_COMMAND,
                expected_subcommand=_IDENTIFY_SUBCOMMAND,
            )
            variant = payload[0] if payload else None
            model_name = self._decode_ascii_bytes(payload[1:]).strip(" ,")
            return DeltaIdentification(variant=variant, model_name=model_name)
        return DeltaIdentification()

    def _execute_standard_command(
        self,
        *,
        serial_port: serial.Serial,
        address: int,
        command: int,
        subcommand: int,
        data: bytes,
        settings: dict[str, object],
        operation_kind: str = "poll",
    ) -> bytes:
        retries = (
            get_poll_retry_count(settings, transport="serial")
            if operation_kind == "poll"
            else get_write_retry_count(settings)
        )
        timeout_seconds = (
            get_poll_timeout_seconds(settings, transport="serial", default=1.0)
            if operation_kind == "poll"
            else get_write_timeout_seconds(settings, default=1.0)
        )
        handle_local_echo = self._to_bool(settings.get("handle_local_echo", False))
        request_frame = self._build_request_frame(
            address=address,
            command=command,
            subcommand=subcommand,
            data=data,
        )

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                serial_port.reset_input_buffer()
                serial_port.reset_output_buffer()
                serial_port.write(request_frame)
                serial_port.flush()
                response_frame = self._read_standard_response(
                    serial_port=serial_port,
                    request_frame=request_frame,
                    timeout_seconds=timeout_seconds,
                    handle_local_echo=handle_local_echo,
                    address=address,
                    command=command,
                    subcommand=subcommand,
                )
                return self._parse_standard_frame(
                    frame=response_frame,
                    address=address,
                    expected_command=command,
                    expected_subcommand=subcommand,
                )
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    self._wait_for_retry(settings)
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("Delta RS485 command failed without a specific error.")

    def _read_identification_response(
        self,
        *,
        serial_port: serial.Serial,
        request_frame: bytes,
        timeout_seconds: float,
        handle_local_echo: bool,
    ) -> bytes:
        deadline = monotonic() + timeout_seconds
        quiet_deadline: float | None = None
        buffer = bytearray()
        while monotonic() < deadline:
            chunk = serial_port.read(serial_port.in_waiting or 1)
            if chunk:
                buffer.extend(chunk)
                quiet_deadline = monotonic() + 0.05
                continue
            if buffer and quiet_deadline is not None and monotonic() >= quiet_deadline:
                break
        raw_response = bytes(buffer)
        if handle_local_echo and raw_response.startswith(request_frame):
            raw_response = raw_response[len(request_frame) :]
        return raw_response

    def _read_standard_response(
        self,
        *,
        serial_port: serial.Serial,
        request_frame: bytes,
        timeout_seconds: float,
        handle_local_echo: bool,
        address: int,
        command: int,
        subcommand: int,
    ) -> bytes:
        deadline = monotonic() + timeout_seconds
        while monotonic() < deadline:
            start_byte = self._read_next_nonempty_byte(serial_port, deadline)
            if start_byte is None:
                break
            if start_byte != _STX:
                continue

            header = self._read_exact(serial_port, 5, deadline)
            if header is None:
                break
            data_length = header[2]
            data = self._read_exact(serial_port, data_length, deadline)
            crc = self._read_exact(serial_port, 2, deadline)
            etx = self._read_exact(serial_port, 1, deadline)
            if data is None or crc is None or etx is None:
                break

            frame = bytes((start_byte,)) + header + data + crc + etx
            if etx[0] != _ETX:
                continue
            if handle_local_echo and frame == request_frame:
                continue

            payload_type = frame[1]
            if payload_type == _ENQ:
                continue
            if payload_type not in {_ACK, _NAK}:
                continue

            self._validate_frame_crc(frame)
            if frame[2] != (address & 0xFF):
                continue
            if frame[4] != (command & 0xFF) or frame[5] != (subcommand & 0xFF):
                continue
            return frame

        raise ConnectionError("Timeout waiting for Delta RS485 response frame.")

    def _parse_standard_frame(
        self,
        *,
        frame: bytes,
        address: int,
        expected_command: int,
        expected_subcommand: int,
    ) -> bytes:
        if len(frame) < 9:
            raise ValueError("Delta RS485 response frame is too short.")
        if frame[0] != _STX or frame[-1] != _ETX:
            raise ValueError("Delta RS485 frame boundaries are invalid.")

        self._validate_frame_crc(frame)
        frame_type = frame[1]
        response_address = frame[2]
        data_length = frame[3]
        command = frame[4]
        subcommand = frame[5]
        data = frame[6 : 6 + data_length]

        if response_address != (address & 0xFF):
            raise ValueError(
                f"Delta RS485 address mismatch (expected={address}, received={response_address})."
            )
        if command != (expected_command & 0xFF) or subcommand != (expected_subcommand & 0xFF):
            raise ValueError("Delta RS485 command echo does not match the request.")
        if frame_type == _NAK:
            raise ValueError(
                f"Delta RS485 command {expected_command}+{expected_subcommand} was rejected."
            )
        if frame_type != _ACK:
            raise ValueError("Delta RS485 response is not an acknowledge frame.")
        return data

    def _decode_measurement_payload(
        self,
        variant: int,
        payload: bytes,
    ) -> dict[str, str | int | float | bool | None]:
        if variant == 1:
            return self._decode_variant_1(payload)
        if variant == 3:
            return self._decode_variant_3(payload)
        if variant == 4:
            return self._decode_variant_4(payload)
        raise NotImplementedError(f"Delta variant {variant} is not supported.")

    def _decode_variant_1(
        self,
        payload: bytes,
    ) -> dict[str, str | int | float | bool | None]:
        if len(payload) < 141:
            raise ValueError("Delta SI 2500 payload is shorter than expected.")
        status_dc = payload[110]
        limits_dc = payload[111]
        status_ac = payload[112]
        limits_ac = payload[113]
        alarm = payload[109]
        return {
            "sap_part_number": self._decode_ascii_bytes(payload[0:11]),
            "sap_serial_number": self._decode_ascii_bytes(payload[11:29]),
            "software_revision_ac_control": self._version_pair(payload[35:37]),
            "software_revision_dc_control": self._version_pair(payload[37:39]),
            "software_revision_display": self._version_pair(payload[39:41]),
            "software_revision_ens_control": self._version_pair(payload[41:43]),
            "dc_input_1_current_a": self._u16(payload[43:45]),
            "dc_input_1_voltage_v": self._u16(payload[45:47]),
            "dc_input_1_isolation_kohm": self._u16(payload[47:49]),
            "ac_current_a": self._u16(payload[49:51]),
            "ac_voltage_v": self._u16(payload[51:53]),
            "active_power_w": self._u16(payload[53:55]),
            "ac_frequency_hz": self._u16(payload[55:57]),
            "daily_energy_wh": self._u16(payload[57:59]),
            "runtime_minutes": self._u16(payload[59:61]),
            "dc_side_temperature_c": self._i16(payload[61:63]),
            "solar_input_mov_resistance_kohm": self._u16(payload[63:65]),
            "ac_side_temperature_c": self._i16(payload[65:67]),
            "total_energy_decikwh": self._u32(payload[101:105]),
            "runtime_hours": self._u32(payload[105:109]),
            "alarm_status_raw": alarm,
            "status_dc_raw": status_dc,
            "limits_dc_raw": limits_dc,
            "status_ac_raw": status_ac,
            "limits_ac_raw": limits_ac,
            "warning_status_raw": payload[114],
            "dc_hardware_failure_raw": payload[115],
            "ac_hardware_failure_raw": payload[116],
            "ens_hardware_failure_raw": payload[117],
            "bulk_failure_raw": payload[118],
            "internal_communication_failure_raw": payload[119],
            "ac_hardware_disturbance_raw": payload[120],
            "operating_state": self._build_operating_state(
                alarm_status=alarm,
                status_dc=status_dc,
                limits_dc=limits_dc,
                status_ac=status_ac,
                limits_ac=limits_ac,
                hardware_bytes=payload[115:121],
            ),
        }

    def _decode_variant_3(
        self,
        payload: bytes,
    ) -> dict[str, str | int | float | bool | None]:
        if len(payload) < 147:
            raise ValueError("Delta SI 3300 payload is shorter than expected.")
        alarm = payload[115]
        status_dc = payload[116]
        limits_dc = payload[117]
        status_ac = payload[118]
        limits_ac = payload[119]
        return {
            "sap_part_number": self._decode_ascii_bytes(payload[0:11]),
            "sap_serial_number": self._decode_ascii_bytes(payload[11:29]),
            "software_revision_ac_control": self._version_pair(payload[35:37]),
            "software_revision_dc_control": self._version_pair(payload[37:39]),
            "software_revision_display": self._version_pair(payload[39:41]),
            "software_revision_ens_master": self._version_pair(payload[41:43]),
            "software_revision_ens_slave": self._version_pair(payload[43:45]),
            "dc_input_1_voltage_v": self._u16(payload[45:47]),
            "dc_input_1_current_a": self._u16(payload[47:49]),
            "dc_input_1_isolation_kohm": self._u16(payload[49:51]),
            "dc_side_temperature_c": self._i16(payload[51:53]),
            "solar_input_mov_resistance_kohm": self._u16(payload[53:55]),
            "ac_current_a": self._u16(payload[55:57]),
            "ac_voltage_v": self._u16(payload[57:59]),
            "active_power_w": self._u16(payload[59:61]),
            "ac_frequency_hz": self._u16(payload[61:63]),
            "ac_side_temperature_c": self._i16(payload[63:65]),
            "daily_energy_wh": self._u16(payload[81:83]),
            "runtime_minutes": self._u16(payload[83:85]),
            "total_energy_decikwh": self._u32(payload[97:101]),
            "runtime_hours": self._u32(payload[101:105]),
            "alarm_status_raw": alarm,
            "status_dc_raw": status_dc,
            "limits_dc_raw": limits_dc,
            "status_ac_raw": status_ac,
            "limits_ac_raw": limits_ac,
            "warning_status_raw": payload[120],
            "dc_hardware_failure_raw": payload[121],
            "ac_hardware_failure_raw": payload[122],
            "ens_hardware_failure_raw": payload[123],
            "bulk_failure_raw": payload[124],
            "internal_communication_failure_raw": payload[125],
            "ac_hardware_disturbance_raw": payload[126],
            "operating_state": self._build_operating_state(
                alarm_status=alarm,
                status_dc=status_dc,
                limits_dc=limits_dc,
                status_ac=status_ac,
                limits_ac=limits_ac,
                hardware_bytes=payload[121:127],
            ),
        }

    def _decode_variant_4(
        self,
        payload: bytes,
    ) -> dict[str, str | int | float | bool | None]:
        if len(payload) < 159:
            raise ValueError("Delta SI 5000 payload is shorter than expected.")
        alarm = payload[127]
        status_dc = payload[128]
        limits_dc = payload[129]
        status_ac = payload[130]
        limits_ac = payload[131]
        return {
            "sap_part_number": self._decode_ascii_bytes(payload[0:11]),
            "sap_serial_number": self._decode_ascii_bytes(payload[11:29]),
            "software_revision_ac_control": self._version_pair(payload[35:37]),
            "software_revision_dc_control": self._version_pair(payload[37:39]),
            "software_revision_display": self._version_pair(payload[39:41]),
            "software_revision_ens_control": self._version_pair(payload[41:43]),
            "dc_input_1_current_a": self._u16(payload[43:45]),
            "dc_input_1_voltage_v": self._u16(payload[45:47]),
            "dc_input_1_isolation_kohm": self._u16(payload[47:49]),
            "dc_input_2_current_a": self._u16(payload[49:51]),
            "dc_input_2_voltage_v": self._u16(payload[51:53]),
            "dc_input_2_isolation_kohm": self._u16(payload[53:55]),
            "ac_current_a": self._u16(payload[55:57]),
            "ac_voltage_v": self._u16(payload[57:59]),
            "active_power_w": self._u16(payload[59:61]),
            "ac_frequency_hz": self._u16(payload[61:63]),
            "daily_energy_wh": self._u16(payload[63:65]),
            "runtime_minutes": self._u16(payload[65:67]),
            "dc_side_temperature_c": self._i16(payload[67:69]),
            "solar_input_1_mov_resistance_kohm": self._u16(payload[69:71]),
            "solar_input_2_mov_resistance_kohm": self._u16(payload[71:73]),
            "ac_side_temperature_c": self._i16(payload[73:75]),
            "total_energy_decikwh": self._u32(payload[119:123]),
            "runtime_hours": self._u32(payload[123:127]),
            "alarm_status_raw": alarm,
            "status_dc_raw": status_dc,
            "limits_dc_raw": limits_dc,
            "status_ac_raw": status_ac,
            "limits_ac_raw": limits_ac,
            "warning_status_raw": payload[132],
            "dc_hardware_failure_raw": payload[133],
            "ac_hardware_failure_raw": payload[134],
            "ens_hardware_failure_raw": payload[135],
            "bulk_failure_raw": payload[136],
            "internal_communication_failure_raw": payload[137],
            "ac_hardware_disturbance_raw": payload[138],
            "operating_state": self._build_operating_state(
                alarm_status=alarm,
                status_dc=status_dc,
                limits_dc=limits_dc,
                status_ac=status_ac,
                limits_ac=limits_ac,
                hardware_bytes=payload[133:139],
            ),
        }

    def _build_operating_state(
        self,
        *,
        alarm_status: int,
        status_dc: int,
        limits_dc: int,
        status_ac: int,
        limits_ac: int,
        hardware_bytes: bytes,
    ) -> int:
        has_fault = alarm_status != 0 or any(value != 0 for value in hardware_bytes)
        is_limited = limits_dc != 0 or limits_ac != 0 or bool(status_dc & 0x1E) or bool(status_ac & 0x02)
        is_operating = bool(status_ac & 0x10)
        is_syncing = bool(status_ac & 0x08)
        if has_fault:
            return 4
        if is_limited:
            return 3
        if is_operating:
            return 2
        if is_syncing:
            return 1
        return 0

    def _resolve_variant(
        self,
        *,
        settings: dict[str, object],
        inverter_model: InverterModel,
        identification: DeltaIdentification,
    ) -> int:
        if identification.variant in _SUPPORTED_VARIANTS:
            return int(identification.variant)

        configured_variant = settings.get("delta_variant")
        if configured_variant not in {None, ""}:
            parsed_variant = int(configured_variant)
            if parsed_variant in _SUPPORTED_VARIANTS:
                return parsed_variant

        model_name = inverter_model.model.lower()
        if "2500" in model_name:
            return 1
        if "3300" in model_name:
            return 3
        if "5000" in model_name:
            return 4
        raise ValueError(
            "Delta SI driver could not resolve the inverter variant. "
            "Set delta_variant in connection settings."
        )

    def _build_request_frame(
        self,
        *,
        address: int,
        command: int,
        subcommand: int,
        data: bytes,
    ) -> bytes:
        body = bytes(
            (
                _ENQ,
                address & 0xFF,
                len(data) & 0xFF,
                command & 0xFF,
                subcommand & 0xFF,
            )
        ) + data
        crc = self._crc16_delta(body)
        return bytes((_STX,)) + body + bytes((crc & 0xFF, (crc >> 8) & 0xFF, _ETX))

    def _validate_frame_crc(self, frame: bytes) -> None:
        body = frame[1:-3]
        expected_crc = self._crc16_delta(body)
        received_crc = frame[-3] | (frame[-2] << 8)
        if expected_crc != received_crc:
            raise ValueError(
                "Delta RS485 CRC mismatch "
                f"(expected={expected_crc:04x}, received={received_crc:04x})."
            )

    def _read_next_nonempty_byte(
        self,
        serial_port: serial.Serial,
        deadline: float,
    ) -> int | None:
        while monotonic() < deadline:
            chunk = serial_port.read(1)
            if chunk:
                return chunk[0]
        return None

    def _read_exact(
        self,
        serial_port: serial.Serial,
        count: int,
        deadline: float,
    ) -> bytes | None:
        buffer = bytearray()
        while len(buffer) < count and monotonic() < deadline:
            chunk = serial_port.read(count - len(buffer))
            if chunk:
                buffer.extend(chunk)
        return bytes(buffer) if len(buffer) == count else None

    def _open_serial_port(
        self,
        settings: dict[str, object],
        *,
        operation_kind: str,
    ) -> serial.Serial:
        timeout_seconds = (
            get_poll_timeout_seconds(settings, transport="serial", default=1.0)
            if operation_kind == "poll"
            else get_write_timeout_seconds(settings, default=1.0)
        )
        serial_port = serial.Serial(
            port=self._require_port(settings),
            baudrate=int(settings.get("baud_rate", 19200)),
            bytesize=int(settings.get("byte_size", 8)),
            parity=str(settings.get("parity", "N")),
            stopbits=int(settings.get("stop_bits", 1)),
            timeout=min(timeout_seconds, 0.1),
            write_timeout=timeout_seconds,
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
        delay_ms = settings.get("inter_request_delay_ms", 10)
        if delay_ms in {None, ""}:
            return
        delay_seconds = float(delay_ms) / 1000.0
        if delay_seconds > 0:
            sleep(delay_seconds)

    def _wait_for_retry(self, settings: dict[str, object]) -> None:
        retry_delay_ms = settings.get("retry_delay_ms", 50)
        if retry_delay_ms in {None, ""}:
            return
        delay_seconds = float(retry_delay_ms) / 1000.0
        if delay_seconds > 0:
            sleep(delay_seconds)

    def _require_port(self, settings: dict[str, object]) -> str:
        port = str(settings.get("port", "")).strip()
        if not port:
            raise ValueError("Missing Delta RS485 port in connection settings.")
        return port

    def _resolve_address(self, settings: dict[str, object]) -> int:
        raw_value = settings.get("address", settings.get("slave_id", 1))
        address = int(raw_value)
        if address < 1 or address > 254:
            raise ValueError("Delta RS485 address must be between 1 and 254.")
        return address

    def _crc16_delta(self, data: bytes) -> int:
        crc = 0x0000
        for byte in data:
            crc ^= byte & 0x00FF
            for _ in range(8):
                if crc & 0x0001:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return crc & 0xFFFF

    def _u16(self, data: bytes) -> int:
        return int.from_bytes(data[:2], byteorder="big", signed=False)

    def _i16(self, data: bytes) -> int:
        return int.from_bytes(data[:2], byteorder="big", signed=True)

    def _u32(self, data: bytes) -> int:
        return int.from_bytes(data[:4], byteorder="big", signed=False)

    def _version_pair(self, data: bytes) -> str:
        if len(data) < 2:
            return ""
        return f"{data[0]}.{data[1]}"

    def _decode_ascii_bytes(self, data: bytes) -> str:
        return (
            bytes(byte for byte in data if byte != 0)
            .decode("ascii", errors="ignore")
            .strip()
            .strip(",")
        )

    def _milliseconds_to_seconds(self, value_ms: object | None) -> float | None:
        if value_ms in {None, ""}:
            return None
        return float(value_ms) / 1000.0

    def _to_bool(self, value: object, *, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return bool(value)


delta_rs485_service = DeltaRs485Service()
