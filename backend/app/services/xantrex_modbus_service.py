from __future__ import annotations

from threading import Lock
from time import sleep

from app.core.connection_settings import (
    get_poll_retry_count,
    get_poll_timeout_seconds,
    get_write_retry_count,
    get_write_timeout_seconds,
)
from app.models.inverter_model import InverterPoint
from app.schemas.device_schemas import DeviceResponse
from app.services.connection_manager import connection_manager

XANTREX_GT_DRIVER = "xantrex_gt_modbus"


class XantrexModbusService:
    def __init__(self) -> None:
        self._registry_lock = Lock()
        self._rtu_locks: dict[str, Lock] = {}
        self._tcp_locks: dict[tuple[str, int], Lock] = {}

    def read_points(
        self,
        device: DeviceResponse,
        points: list[InverterPoint],
    ) -> dict[str, str | int | float | bool | None]:
        lock = self._get_lock(device)
        with lock:
            return self._execute_with_client(
                device,
                operation_kind="poll",
                operation=lambda client, unit_value: self._read_points_with_client(
                    client=client,
                    device=device,
                    unit_value=unit_value,
                    points=points,
                ),
            )

    def write_point(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> dict[str, str | int | float | bool]:
        lock = self._get_lock(device)
        with lock:
            return self._execute_with_client(
                device,
                operation_kind="command",
                operation=lambda client, unit_value: self._write_point_with_client(
                    client=client,
                    device=device,
                    unit_value=unit_value,
                    point=point,
                    value=value,
                ),
            )

    def _get_lock(self, device: DeviceResponse) -> Lock:
        with self._registry_lock:
            if device.protocol == "modbus_rtu":
                key = str(device.connection_settings.get("port", ""))
                return self._rtu_locks.setdefault(key, Lock())

            key = (
                str(device.connection_settings.get("host", "")),
                int(device.connection_settings.get("port", 502)),
            )
            return self._tcp_locks.setdefault(key, Lock())

    def _execute_with_client(
        self,
        device: DeviceResponse,
        *,
        operation_kind: str,
        operation: callable,
    ) -> object:
        if device.protocol == "modbus_tcp":
            host = str(device.connection_settings.get("host", ""))
            port = int(device.connection_settings.get("port", 502))
            unit_id = int(device.connection_settings.get("unit_id", 101))
            timeout_seconds = (
                get_write_timeout_seconds(device.connection_settings)
                if operation_kind == "command"
                else get_poll_timeout_seconds(
                    device.connection_settings,
                    transport=device.transport,
                )
            )
            retries = (
                get_write_retry_count(device.connection_settings)
                if operation_kind == "command"
                else get_poll_retry_count(
                    device.connection_settings,
                    transport=device.transport,
                )
            )
            if not host:
                raise ValueError("Missing Modbus TCP host for Xantrex driver.")
            return connection_manager.execute_modbus_tcp(
                host=host,
                port=port,
                timeout=timeout_seconds,
                retries=retries,
                operation_kind=operation_kind,
                operation=lambda client: operation(client, unit_id),
            )

        if device.protocol == "modbus_rtu":
            port = str(device.connection_settings.get("port", ""))
            slave_id = int(device.connection_settings.get("slave_id", 101))
            baud_rate = int(device.connection_settings.get("baud_rate", 9600))
            byte_size = int(device.connection_settings.get("byte_size", 8))
            parity = str(device.connection_settings.get("parity", "N"))
            stop_bits = int(device.connection_settings.get("stop_bits", 1))
            timeout_seconds = (
                get_write_timeout_seconds(device.connection_settings)
                if operation_kind == "command"
                else get_poll_timeout_seconds(
                    device.connection_settings,
                    transport=device.transport,
                    default=1.0,
                )
            )
            retries = (
                get_write_retry_count(device.connection_settings)
                if operation_kind == "command"
                else get_poll_retry_count(
                    device.connection_settings,
                    transport=device.transport,
                )
            )
            if not port:
                raise ValueError("Missing Modbus RTU port for Xantrex driver.")
            return connection_manager.execute_modbus_rtu(
                port=port,
                baudrate=baud_rate,
                bytesize=byte_size,
                parity=parity,
                stopbits=stop_bits,
                timeout=timeout_seconds,
                retries=retries,
                advanced_options=device.connection_settings,
                operation_kind=operation_kind,
                operation=lambda client: operation(client, slave_id),
            )

        raise NotImplementedError(f"Protocol {device.protocol} is not supported by Xantrex.")

    def _read_points_with_client(
        self,
        *,
        client: object,
        device: DeviceResponse,
        unit_value: int,
        points: list[InverterPoint],
    ) -> dict[str, str | int | float | bool | None]:
        raw_values: dict[str, str | int | float | bool | None] = {}

        fixed_points = [
            point
            for point in points
            if point.protocol_meta.get("queue_kind") is None
        ]
        for block in self._group_fixed_points(fixed_points):
            start_address = min(point.address for point in block)
            end_address = max(point.address + point.length - 1 for point in block)
            registers = self._read_holding_registers(
                client=client,
                unit_value=unit_value,
                address=start_address,
                count=end_address - start_address + 1,
                settings=device.connection_settings,
            )
            for point in block:
                raw_values[point.key] = self._decode_point(
                    registers=registers,
                    start_address=start_address,
                    point=point,
                )

        queue_groups = self._group_queue_points(points)
        for queue_kind, queue_points in queue_groups.items():
            if queue_kind == "energy_history":
                queue_cache: dict[int, dict[str, int | str | None]] = {}
                for point in queue_points:
                    log_type = int(point.protocol_meta.get("queue_log_type", 0))
                    if log_type not in queue_cache:
                        queue_cache[log_type] = self._read_energy_history_log(
                            client=client,
                            unit_value=unit_value,
                            settings=device.connection_settings,
                            log_type=log_type,
                        )
                    field_name = str(point.protocol_meta.get("queue_field", ""))
                    raw_values[point.key] = queue_cache[log_type].get(field_name)
            elif queue_kind == "active_fault":
                queue_record = self._read_fault_queue_record(
                    client=client,
                    unit_value=unit_value,
                    settings=device.connection_settings,
                    total_address=0x0080,
                    record_start=0x0081,
                    record_count=25,
                )
                for point in queue_points:
                    field_name = str(point.protocol_meta.get("queue_field", ""))
                    raw_values[point.key] = queue_record.get(field_name)
            elif queue_kind == "fault_log":
                queue_record = self._read_fault_queue_record(
                    client=client,
                    unit_value=unit_value,
                    settings=device.connection_settings,
                    total_address=0x1000,
                    record_start=0x1001,
                    record_count=25,
                )
                for point in queue_points:
                    field_name = str(point.protocol_meta.get("queue_field", ""))
                    raw_values[point.key] = queue_record.get(field_name)

        return raw_values

    def _write_point_with_client(
        self,
        *,
        client: object,
        device: DeviceResponse,
        unit_value: int,
        point: InverterPoint,
        value: float,
    ) -> dict[str, str | int | float | bool]:
        encoded_values = self._encode_command_value(point, value)
        self._write_holding_registers(
            client=client,
            unit_value=unit_value,
            address=point.address,
            values=encoded_values,
            settings=device.connection_settings,
        )
        return {
            "stub_mode": False,
            "driver": XANTREX_GT_DRIVER,
            "protocol": device.protocol,
            "register": point.address,
            "requested_value": value,
        }

    def _group_fixed_points(self, points: list[InverterPoint]) -> list[list[InverterPoint]]:
        if not points:
            return []

        sorted_points = sorted(points, key=lambda point: point.address)
        blocks: list[list[InverterPoint]] = []
        current_block = [sorted_points[0]]
        current_end = sorted_points[0].address + sorted_points[0].length - 1

        for point in sorted_points[1:]:
            point_end = point.address + point.length - 1
            if point.address <= current_end + 1:
                current_block.append(point)
                current_end = max(current_end, point_end)
                continue
            blocks.append(current_block)
            current_block = [point]
            current_end = point_end

        if current_block:
            blocks.append(current_block)
        return blocks

    def _group_queue_points(self, points: list[InverterPoint]) -> dict[str, list[InverterPoint]]:
        grouped: dict[str, list[InverterPoint]] = {}
        for point in points:
            queue_kind = point.protocol_meta.get("queue_kind")
            if isinstance(queue_kind, str):
                grouped.setdefault(queue_kind, []).append(point)
        return grouped

    def _read_energy_history_log(
        self,
        *,
        client: object,
        unit_value: int,
        settings: dict[str, object],
        log_type: int,
    ) -> dict[str, int | str | None]:
        self._write_holding_registers(
            client=client,
            unit_value=unit_value,
            address=0x0800,
            values=[log_type, 0, 0],
            settings=settings,
        )
        self._write_holding_registers(
            client=client,
            unit_value=unit_value,
            address=0x0803,
            values=[0],
            settings=settings,
        )
        record = self._read_holding_registers(
            client=client,
            unit_value=unit_value,
            address=0x0803,
            count=7,
            settings=settings,
        )
        return {
            "queue_index": record[0],
            "energy": self._decode_int32(record[1], record[2]),
            "peak_power": self._decode_int32(record[3], record[4]),
            "harvest_time": self._decode_uint32(record[5], record[6]),
        }

    def _read_fault_queue_record(
        self,
        *,
        client: object,
        unit_value: int,
        settings: dict[str, object],
        total_address: int,
        record_start: int,
        record_count: int,
    ) -> dict[str, int | str | None]:
        total_register = self._read_holding_registers(
            client=client,
            unit_value=unit_value,
            address=total_address,
            count=1,
            settings=settings,
        )[0]
        if total_register in {0, 0xFFFF, 0xFFFE, 0xFFFD}:
            return {"count": None, "type": None, "identifier": None, "time": None, "text": None}

        self._write_holding_registers(
            client=client,
            unit_value=unit_value,
            address=record_start,
            values=[0],
            settings=settings,
        )
        record = self._read_holding_registers(
            client=client,
            unit_value=unit_value,
            address=record_start,
            count=record_count,
            settings=settings,
        )
        return {
            "count": total_register,
            "type": self._sanitize_uint16(record[1]),
            "identifier": self._sanitize_uint16(record[2]),
            "time": self._sanitize_uint32(self._decode_uint32(record[3], record[4])),
            "text": self._decode_ascii(record[5:]),
        }

    def _read_holding_registers(
        self,
        *,
        client: object,
        unit_value: int,
        address: int,
        count: int,
        settings: dict[str, object],
    ) -> list[int]:
        response = self._execute_with_busy_retry(
            settings,
            lambda: self._read_holding_registers_once(
                client=client,
                unit_value=unit_value,
                address=address,
                count=count,
            ),
        )
        if response.isError():
            raise RuntimeError(str(response))
        return list(getattr(response, "registers", []))

    def _write_holding_registers(
        self,
        *,
        client: object,
        unit_value: int,
        address: int,
        values: list[int],
        settings: dict[str, object],
    ) -> None:
        response = self._execute_with_busy_retry(
            settings,
            lambda: self._write_holding_registers_once(
                client=client,
                unit_value=unit_value,
                address=address,
                values=values,
            ),
        )
        if response.isError():
            raise RuntimeError(str(response))

    def _read_holding_registers_once(
        self,
        *,
        client: object,
        unit_value: int,
        address: int,
        count: int,
    ) -> object:
        read_method = getattr(client, "read_holding_registers")
        try:
            return read_method(address, count=count, device_id=unit_value)
        except TypeError:
            try:
                return read_method(address, count=count, slave=unit_value)
            except TypeError:
                return read_method(address, count=count)

    def _write_holding_registers_once(
        self,
        *,
        client: object,
        unit_value: int,
        address: int,
        values: list[int],
    ) -> object:
        write_method = getattr(client, "write_registers")
        try:
            return write_method(address, values, device_id=unit_value)
        except TypeError:
            try:
                return write_method(address, values, slave=unit_value)
            except TypeError:
                return write_method(address, values)

    def _execute_with_busy_retry(self, settings: dict[str, object], action: callable) -> object:
        if not self._retry_on_device_busy(settings):
            return action()

        attempts = self._device_busy_retry_count(settings)
        for attempt in range(attempts + 1):
            response = action()
            if getattr(response, "exception_code", None) != 6:
                return response
            if attempt < attempts:
                self._wait_for_device_busy_retry(settings)
        return response

    def _decode_point(
        self,
        *,
        registers: list[int],
        start_address: int,
        point: InverterPoint,
    ) -> str | int | float | None:
        index = point.address - start_address
        raw_slice = registers[index : index + point.length]
        if not raw_slice:
            return None

        if point.datatype == "uint16":
            return self._sanitize_uint16(raw_slice[0])
        if point.datatype == "int16":
            return self._sanitize_int16(raw_slice[0])
        if point.datatype == "uint32":
            return self._sanitize_uint32(self._decode_uint32(raw_slice[0], raw_slice[1]))
        if point.datatype == "int32":
            return self._sanitize_int32(self._decode_int32(raw_slice[0], raw_slice[1]))
        if point.datatype == "ascii_string":
            return self._decode_ascii(raw_slice)

        return raw_slice[0]

    def _encode_command_value(self, point: InverterPoint, value: float) -> list[int]:
        scaled_value = value / point.scale if point.scale not in {0.0, 1.0} else value
        integer_value = int(round(scaled_value))
        if point.datatype == "uint16":
            return [integer_value & 0xFFFF]
        if point.datatype == "int16":
            return [integer_value & 0xFFFF]
        if point.datatype == "uint32":
            normalized_value = integer_value & 0xFFFFFFFF
            return [(normalized_value >> 16) & 0xFFFF, normalized_value & 0xFFFF]
        if point.datatype == "int32":
            normalized_value = integer_value & 0xFFFFFFFF
            return [(normalized_value >> 16) & 0xFFFF, normalized_value & 0xFFFF]
        raise ValueError(f"Unsupported Xantrex command datatype {point.datatype}.")

    def _decode_ascii(self, registers: list[int]) -> str:
        raw_bytes = bytearray()
        for register in registers:
            raw_bytes.append((register >> 8) & 0xFF)
            raw_bytes.append(register & 0xFF)
        return bytes(raw_bytes).split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()

    def _decode_uint32(self, high_word: int, low_word: int) -> int:
        return ((high_word & 0xFFFF) << 16) | (low_word & 0xFFFF)

    def _decode_int32(self, high_word: int, low_word: int) -> int:
        value = self._decode_uint32(high_word, low_word)
        return value - 0x100000000 if value >= 0x80000000 else value

    def _sanitize_uint16(self, value: int) -> int | None:
        return None if value in {0xFFFF, 0xFFFE, 0xFFFD} else value

    def _sanitize_int16(self, value: int) -> int | None:
        if value in {0x7FFF, 0x7FFE, 0x7FFD}:
            return None
        return value - 0x10000 if value >= 0x8000 else value

    def _sanitize_uint32(self, value: int) -> int | None:
        return None if value in {0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD} else value

    def _sanitize_int32(self, value: int) -> int | None:
        if value in {0x7FFFFFFF, 0x7FFFFFFE, 0x7FFFFFFD}:
            return None
        return value

    def _retry_on_device_busy(self, settings: dict[str, object]) -> bool:
        raw_value = settings.get("retry_on_device_busy")
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, (int, float)):
            return bool(raw_value)
        if isinstance(raw_value, str):
            return raw_value.strip().lower() in {"1", "true", "yes", "on"}
        return False

    def _device_busy_retry_count(self, settings: dict[str, object]) -> int:
        raw_value = settings.get("device_busy_retry_count", 0)
        if raw_value in {None, ""}:
            return 0
        return max(0, int(raw_value))

    def _wait_for_device_busy_retry(self, settings: dict[str, object]) -> None:
        raw_value = settings.get("device_busy_retry_delay_ms", 0)
        if raw_value in {None, ""}:
            return
        delay_seconds = float(raw_value) / 1000.0
        if delay_seconds > 0:
            sleep(delay_seconds)


xantrex_modbus_service = XantrexModbusService()
