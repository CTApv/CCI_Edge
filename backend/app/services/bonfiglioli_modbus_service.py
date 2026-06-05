from __future__ import annotations

import socket
from threading import Lock
from time import monotonic

import serial
from serial.rs485 import RS485Settings

from app.core.connection_settings import (
    get_poll_timeout_seconds,
    get_write_timeout_seconds,
)
from app.models.inverter_model import InverterPoint
from app.schemas.device_schemas import DeviceResponse
from app.services.connection_manager import connection_manager

BONFIGLIOLI_DRIVER = "bonfiglioli_parameter_modbus"


class BonfiglioliModbusService:
    def __init__(self) -> None:
        self._registry_lock = Lock()
        self._rtu_locks: dict[str, Lock] = {}
        self._tcp_locks: dict[tuple[str, int], Lock] = {}
        self._transaction_id = 0

    def build_broadcast_signature(
        self,
        point: InverterPoint,
        settings: dict[str, object],
        value: float,
    ) -> tuple[object, ...]:
        return (
            BONFIGLIOLI_DRIVER,
            self._write_function_code(point),
            self._parameter_address(point, settings),
            self._encode_command_value(point, value),
        )

    def read_points(
        self,
        device: DeviceResponse,
        points: list[InverterPoint],
    ) -> dict[str, int | float]:
        if device.protocol == "modbus_rtu":
            return self._read_points_rtu(device, points)
        if device.protocol == "modbus_tcp":
            return self._read_points_tcp(device, points)
        raise NotImplementedError(f"Bonfiglioli driver does not support protocol {device.protocol}.")

    def write_point(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> dict[str, str | int | float | bool]:
        if device.protocol == "modbus_rtu":
            return self._write_point_rtu(device, point, value)
        if device.protocol == "modbus_tcp":
            return self._write_point_tcp(device, point, value)
        raise NotImplementedError(f"Bonfiglioli driver does not support protocol {device.protocol}.")

    def write_point_broadcast(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> dict[str, str | int | float | bool]:
        if device.protocol != "modbus_rtu":
            raise NotImplementedError("Bonfiglioli broadcast is only supported for Modbus RTU.")
        return self._write_point_rtu(device, point, value, broadcast=True)

    def _read_points_rtu(
        self,
        device: DeviceResponse,
        points: list[InverterPoint],
    ) -> dict[str, int | float]:
        port = str(device.connection_settings.get("port", ""))
        slave_id = int(device.connection_settings.get("slave_id", 1))
        timeout = get_poll_timeout_seconds(
            device.connection_settings,
            transport=device.transport,
        )
        lock = self._get_rtu_lock(port)
        with lock:
            serial_port = self._open_serial_port(device.connection_settings)
            try:
                values: dict[str, int | float] = {}
                first_error: Exception | None = None
                for point in points:
                    try:
                        values[point.key] = self._read_parameter_rtu(
                            serial_port=serial_port,
                            slave_id=slave_id,
                            point=point,
                            settings=device.connection_settings,
                            timeout=timeout,
                        )
                    except Exception as exc:
                        if first_error is None:
                            first_error = exc
                if values:
                    return values
                if first_error is not None:
                    raise first_error
                return values
            finally:
                serial_port.close()

    def _read_points_tcp(
        self,
        device: DeviceResponse,
        points: list[InverterPoint],
    ) -> dict[str, int | float]:
        host = str(device.connection_settings.get("host", ""))
        port = int(device.connection_settings.get("port", 502))
        unit_id = int(device.connection_settings.get("unit_id", 1))
        timeout = get_poll_timeout_seconds(
            device.connection_settings,
            transport=device.transport,
        )
        lock = self._get_tcp_lock(host, port)
        with lock:
            with socket.create_connection((host, port), timeout=timeout) as tcp_socket:
                tcp_socket.settimeout(timeout)
                values: dict[str, int | float] = {}
                first_error: Exception | None = None
                for point in points:
                    try:
                        values[point.key] = self._read_parameter_tcp(
                            tcp_socket=tcp_socket,
                            unit_id=unit_id,
                            point=point,
                            settings=device.connection_settings,
                            timeout=timeout,
                        )
                    except Exception as exc:
                        if first_error is None:
                            first_error = exc
                if values:
                    return values
                if first_error is not None:
                    raise first_error
                return values

    def _write_point_rtu(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
        *,
        broadcast: bool = False,
    ) -> dict[str, str | int | float | bool]:
        port = str(device.connection_settings.get("port", ""))
        slave_id = 0 if broadcast else int(device.connection_settings.get("slave_id", 1))
        timeout = get_write_timeout_seconds(device.connection_settings)
        encoded_value = self._encode_command_value(point, value)
        connection_manager.request_modbus_rtu_priority(
            port,
            hold_seconds=max(1.0, timeout + 0.75),
        )
        lock = self._get_rtu_lock(port)
        with lock:
            serial_port = self._open_serial_port(device.connection_settings)
            try:
                function_code = self._write_function_code(point)
                request_frame = self._build_rtu_request(
                    slave_id=slave_id,
                    function_code=function_code,
                    parameter_address=self._parameter_address(point, device.connection_settings),
                    encoded_value=encoded_value,
                )
                serial_port.reset_input_buffer()
                serial_port.write(request_frame)
                serial_port.flush()
                if not broadcast:
                    self._read_rtu_response(
                        serial_port=serial_port,
                        slave_id=slave_id,
                        function_code=function_code,
                        timeout=timeout,
                    )
            finally:
                serial_port.close()
                connection_manager.register_modbus_rtu_write(port, quiet_seconds=0.9)

        return {
            "driver": BONFIGLIOLI_DRIVER,
            "function_code": function_code,
            "parameter": point.address,
            "parameter_actual": point.address + self._address_offset(point, device.connection_settings),
            "parameter_offset": self._address_offset(point, device.connection_settings),
            "encoded_value": encoded_value,
            "dataset": self._dataset(point),
            "transport": device.transport,
            "broadcast": broadcast,
        }

    def _write_point_tcp(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> dict[str, str | int | float | bool]:
        host = str(device.connection_settings.get("host", ""))
        port = int(device.connection_settings.get("port", 502))
        unit_id = int(device.connection_settings.get("unit_id", 1))
        timeout = get_write_timeout_seconds(device.connection_settings)
        encoded_value = self._encode_command_value(point, value)
        connection_manager.request_modbus_tcp_priority(
            host,
            port,
            hold_seconds=max(1.0, timeout + 0.75),
        )
        lock = self._get_tcp_lock(host, port)
        try:
            with lock:
                with socket.create_connection((host, port), timeout=timeout) as tcp_socket:
                    tcp_socket.settimeout(timeout)
                    function_code = self._write_function_code(point)
                    transaction_id = self._next_transaction_id()
                    request_frame = self._build_tcp_request(
                        transaction_id=transaction_id,
                        unit_id=unit_id,
                        function_code=function_code,
                        parameter_address=self._parameter_address(point, device.connection_settings),
                        encoded_value=encoded_value,
                    )
                    tcp_socket.sendall(request_frame)
                    self._read_tcp_response(
                        tcp_socket=tcp_socket,
                        transaction_id=transaction_id,
                        function_code=function_code,
                        timeout=timeout,
                    )
        finally:
            connection_manager.register_modbus_tcp_write(
                host,
                port,
                quiet_seconds=max(0.25, timeout),
            )

        return {
            "driver": BONFIGLIOLI_DRIVER,
            "function_code": function_code,
            "parameter": point.address,
            "parameter_actual": point.address + self._address_offset(point, device.connection_settings),
            "parameter_offset": self._address_offset(point, device.connection_settings),
            "encoded_value": encoded_value,
            "dataset": self._dataset(point),
            "transport": device.transport,
        }

    def _read_parameter_rtu(
        self,
        *,
        serial_port: serial.Serial,
        slave_id: int,
        point: InverterPoint,
        settings: dict[str, object],
        timeout: float,
    ) -> int | float:
        function_code = self._read_function_code(point)
        request_frame = self._build_rtu_request(
            slave_id=slave_id,
            function_code=function_code,
            parameter_address=self._parameter_address(point, settings),
        )
        serial_port.reset_input_buffer()
        serial_port.write(request_frame)
        serial_port.flush()
        response_frame = self._read_rtu_response(
            serial_port=serial_port,
            slave_id=slave_id,
            function_code=function_code,
            timeout=timeout,
        )
        raw_value = self._parse_rtu_read_response(response_frame, function_code=function_code)
        return self._decode_raw_value(point, raw_value)

    def _read_parameter_tcp(
        self,
        *,
        tcp_socket: socket.socket,
        unit_id: int,
        point: InverterPoint,
        settings: dict[str, object],
        timeout: float,
    ) -> int | float:
        function_code = self._read_function_code(point)
        transaction_id = self._next_transaction_id()
        request_frame = self._build_tcp_request(
            transaction_id=transaction_id,
            unit_id=unit_id,
            function_code=function_code,
            parameter_address=self._parameter_address(point, settings),
        )
        tcp_socket.sendall(request_frame)
        response_payload = self._read_tcp_response(
            tcp_socket=tcp_socket,
            transaction_id=transaction_id,
            function_code=function_code,
            timeout=timeout,
        )
        raw_value = self._parse_tcp_read_response(response_payload, function_code=function_code)
        return self._decode_raw_value(point, raw_value)

    def _open_serial_port(self, settings: dict[str, object]) -> serial.Serial:
        serial_port = serial.Serial(
            port=str(settings.get("port", "")),
            baudrate=int(settings.get("baud_rate", 9600)),
            bytesize=int(settings.get("byte_size", 8)),
            parity=str(settings.get("parity", "N")),
            stopbits=int(settings.get("stop_bits", 1)),
            timeout=0.05,
            write_timeout=get_write_timeout_seconds(settings),
        )

        if self._to_bool(settings.get("use_rs485_mode", False)):
            serial_port.rs485_mode = RS485Settings(
                rts_level_for_tx=self._to_bool(settings.get("rs485_rts_level_for_tx", True), default=True),
                rts_level_for_rx=self._to_bool(settings.get("rs485_rts_level_for_rx", False)),
                loopback=self._to_bool(settings.get("rs485_loopback", False)),
                delay_before_tx=self._milliseconds_to_seconds(settings.get("rs485_delay_before_tx_ms")),
                delay_before_rx=self._milliseconds_to_seconds(settings.get("rs485_delay_before_rx_ms")),
            )

        return serial_port

    def _get_rtu_lock(self, port: str) -> Lock:
        with self._registry_lock:
            lock = self._rtu_locks.get(port)
            if lock is None:
                lock = Lock()
                self._rtu_locks[port] = lock
            return lock

    def _get_tcp_lock(self, host: str, port: int) -> Lock:
        key = (host, port)
        with self._registry_lock:
            lock = self._tcp_locks.get(key)
            if lock is None:
                lock = Lock()
                self._tcp_locks[key] = lock
            return lock

    def _next_transaction_id(self) -> int:
        with self._registry_lock:
            self._transaction_id = (self._transaction_id + 1) % 0x10000
            return self._transaction_id

    def _parameter_address(self, point: InverterPoint, settings: dict[str, object]) -> int:
        parameter = point.address + self._address_offset(point, settings)
        return (self._dataset(point) << 12) | (parameter & 0x0FFF)

    def _dataset(self, point: InverterPoint) -> int:
        dataset = int(point.protocol_meta.get("dataset", 0))
        if dataset < 0 or dataset > 9:
            raise ValueError(f"Unsupported Bonfiglioli dataset for point {point.key}.")
        return dataset

    def _address_offset(self, point: InverterPoint, settings: dict[str, object]) -> int:
        raw_offset = settings.get("parameter_offset", point.protocol_meta.get("address_offset", 0))
        return int(raw_offset)

    def _read_function_code(self, point: InverterPoint) -> int:
        if "read_function_code" in point.protocol_meta:
            return int(point.protocol_meta["read_function_code"])
        if point.datatype in {"int32", "uint32"}:
            return 100
        return 3

    def _write_function_code(self, point: InverterPoint) -> int:
        if "write_function_code" in point.protocol_meta:
            return int(point.protocol_meta["write_function_code"])
        if point.datatype in {"int32", "uint32"}:
            return 101
        return 6

    def _build_rtu_request(
        self,
        *,
        slave_id: int,
        function_code: int,
        parameter_address: int,
        encoded_value: int | None = None,
    ) -> bytes:
        payload = bytes((slave_id, function_code)) + parameter_address.to_bytes(2, byteorder="big")
        if function_code == 3:
            payload += (1).to_bytes(2, byteorder="big")
        elif function_code == 6:
            if encoded_value is None:
                raise ValueError("Bonfiglioli write request is missing a 16-bit value.")
            payload += encoded_value.to_bytes(2, byteorder="big")
        elif function_code == 101:
            if encoded_value is None:
                raise ValueError("Bonfiglioli write request is missing a 32-bit value.")
            payload += encoded_value.to_bytes(4, byteorder="big")
        elif function_code != 100:
            raise ValueError(f"Unsupported Bonfiglioli function code {function_code}.")
        return self._append_crc(payload)

    def _build_tcp_request(
        self,
        *,
        transaction_id: int,
        unit_id: int,
        function_code: int,
        parameter_address: int,
        encoded_value: int | None = None,
    ) -> bytes:
        pdu = bytes((function_code,)) + parameter_address.to_bytes(2, byteorder="big")
        if function_code == 3:
            pdu += (1).to_bytes(2, byteorder="big")
        elif function_code == 6:
            if encoded_value is None:
                raise ValueError("Bonfiglioli write request is missing a 16-bit value.")
            pdu += encoded_value.to_bytes(2, byteorder="big")
        elif function_code == 101:
            if encoded_value is None:
                raise ValueError("Bonfiglioli write request is missing a 32-bit value.")
            pdu += encoded_value.to_bytes(4, byteorder="big")
        elif function_code != 100:
            raise ValueError(f"Unsupported Bonfiglioli function code {function_code}.")

        mbap = (
            transaction_id.to_bytes(2, byteorder="big")
            + b"\x00\x00"
            + (len(pdu) + 1).to_bytes(2, byteorder="big")
            + bytes((unit_id,))
        )
        return mbap + pdu

    def _read_rtu_response(
        self,
        *,
        serial_port: serial.Serial,
        slave_id: int,
        function_code: int,
        timeout: float,
    ) -> bytes:
        deadline = monotonic() + timeout
        buffer = bytearray()
        while monotonic() < deadline:
            chunk = serial_port.read(serial_port.in_waiting or 1)
            if chunk:
                buffer.extend(chunk)
                frame = self._extract_rtu_frame(buffer, slave_id=slave_id, function_code=function_code)
                if frame is not None:
                    return frame
        raise TimeoutError("Bonfiglioli RTU read timed out before a complete response frame was received.")

    def _read_tcp_response(
        self,
        *,
        tcp_socket: socket.socket,
        transaction_id: int,
        function_code: int,
        timeout: float,
    ) -> bytes:
        deadline = monotonic() + timeout
        header = self._read_socket_exact(tcp_socket, size=7, deadline=deadline)
        response_transaction_id = int.from_bytes(header[0:2], byteorder="big")
        protocol_id = int.from_bytes(header[2:4], byteorder="big")
        payload_length = int.from_bytes(header[4:6], byteorder="big")
        if response_transaction_id != transaction_id:
            raise RuntimeError("Bonfiglioli TCP response transaction id does not match the request.")
        if protocol_id != 0:
            raise RuntimeError("Bonfiglioli TCP response uses an invalid Modbus protocol id.")
        if payload_length < 2:
            raise RuntimeError("Bonfiglioli TCP response is too short.")
        payload = self._read_socket_exact(tcp_socket, size=payload_length - 1, deadline=deadline)
        if not payload:
            raise RuntimeError("Bonfiglioli TCP response payload is empty.")
        response_function = payload[0]
        if response_function == (function_code | 0x80):
            if len(payload) < 2:
                raise RuntimeError("Bonfiglioli TCP exception response is too short.")
            raise RuntimeError(
                f"Bonfiglioli TCP exception response {payload[1]} for function {function_code}.",
            )
        return payload

    def _read_socket_exact(
        self,
        tcp_socket: socket.socket,
        *,
        size: int,
        deadline: float,
    ) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("Bonfiglioli TCP read timed out before the response was complete.")
            tcp_socket.settimeout(remaining)
            chunk = tcp_socket.recv(size - len(chunks))
            if not chunk:
                raise RuntimeError("Bonfiglioli TCP socket closed before the response was complete.")
            chunks.extend(chunk)
        return bytes(chunks)

    def _extract_rtu_frame(
        self,
        buffer: bytearray,
        *,
        slave_id: int,
        function_code: int,
    ) -> bytes | None:
        index = 0
        while index < len(buffer):
            if buffer[index] != slave_id:
                index += 1
                continue
            if index + 2 > len(buffer):
                break

            response_function = buffer[index + 1]
            frame_length = self._expected_rtu_response_length(function_code, response_function)
            if frame_length is None:
                index += 1
                continue
            if index + frame_length > len(buffer):
                break

            frame = bytes(buffer[index : index + frame_length])
            payload = frame[:-2]
            received_crc = int.from_bytes(frame[-2:], byteorder="little")
            expected_crc = self._crc16_modbus(payload)
            if received_crc == expected_crc:
                del buffer[: index + frame_length]
                if response_function == (function_code | 0x80):
                    raise RuntimeError(
                        f"Bonfiglioli RTU exception response {frame[2]} for function {function_code}.",
                    )
                return frame
            index += 1

        if len(buffer) > 32:
            del buffer[:-8]
        return None

    def _expected_rtu_response_length(self, function_code: int, response_function: int) -> int | None:
        if response_function == (function_code | 0x80):
            return 5
        if response_function != function_code:
            return None
        if function_code == 3:
            return 7
        if function_code == 6:
            return 8
        if function_code == 100:
            return 8
        if function_code == 101:
            return 10
        return None

    def _parse_rtu_read_response(self, frame: bytes, *, function_code: int) -> int:
        if function_code == 3:
            if len(frame) != 7 or frame[2] != 2:
                raise RuntimeError("Unexpected Bonfiglioli RTU 16-bit response length.")
            return int.from_bytes(frame[3:5], byteorder="big")
        if function_code == 100:
            if len(frame) != 8:
                raise RuntimeError("Unexpected Bonfiglioli RTU 32-bit response length.")
            return int.from_bytes(frame[2:6], byteorder="big")
        raise RuntimeError(f"Unsupported Bonfiglioli RTU read function code {function_code}.")

    def _parse_tcp_read_response(self, payload: bytes, *, function_code: int) -> int:
        if function_code == 3:
            if len(payload) != 4 or payload[1] != 2:
                raise RuntimeError("Unexpected Bonfiglioli TCP 16-bit response payload.")
            return int.from_bytes(payload[2:4], byteorder="big")
        if function_code == 100:
            if len(payload) != 5:
                raise RuntimeError("Unexpected Bonfiglioli TCP 32-bit response payload.")
            return int.from_bytes(payload[1:5], byteorder="big")
        raise RuntimeError(f"Unsupported Bonfiglioli TCP read function code {function_code}.")

    def _decode_raw_value(self, point: InverterPoint, raw_value: int) -> int | float:
        if point.datatype == "int16":
            return raw_value - 0x10000 if raw_value >= 0x8000 else raw_value
        if point.datatype == "uint16":
            return raw_value
        if point.datatype == "int32":
            return raw_value - 0x100000000 if raw_value >= 0x80000000 else raw_value
        if point.datatype == "uint32":
            return raw_value
        raise RuntimeError(f"Unsupported Bonfiglioli datatype {point.datatype}.")

    def _encode_command_value(self, point: InverterPoint, value: float) -> int:
        scaled_value = value / point.scale if point.scale not in {0.0, 1.0} else value
        integer_value = int(round(scaled_value))
        if point.datatype in {"uint16", "int16"}:
            return integer_value & 0xFFFF
        if point.datatype in {"uint32", "int32"}:
            return integer_value & 0xFFFFFFFF
        raise RuntimeError(f"Unsupported Bonfiglioli command datatype {point.datatype}.")

    def _append_crc(self, payload: bytes) -> bytes:
        crc = self._crc16_modbus(payload)
        return payload + bytes((crc & 0xFF, (crc >> 8) & 0xFF))

    def _crc16_modbus(self, data: bytes) -> int:
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc & 0xFFFF

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

    def _milliseconds_to_seconds(self, value_ms: object) -> float | None:
        if value_ms in {None, ""}:
            return None
        numeric_value = float(value_ms)
        return numeric_value / 1000.0 if numeric_value > 0 else None


bonfiglioli_modbus_service = BonfiglioliModbusService()
