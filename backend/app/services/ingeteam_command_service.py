from app.models.inverter_model import InverterPoint
from app.core.connection_settings import (
    get_write_retry_count,
    get_write_timeout_seconds,
)
from app.schemas.device_schemas import DeviceResponse
from app.services.connection_manager import connection_manager


INGETEAM_UNIT_COMMAND_DRIVER = "ingeteam_unit_commands"
INGETEAM_COMMAND_START_ADDRESS = 1000


class IngeteamCommandService:
    def build_broadcast_signature(
        self,
        point: InverterPoint,
        value: float,
    ) -> tuple[object, ...] | None:
        if point.protocol_meta.get("driver") != INGETEAM_UNIT_COMMAND_DRIVER:
            return None

        registers = self._build_register_payload(point, value)
        start_address = int(
            point.protocol_meta.get("command_start_address", INGETEAM_COMMAND_START_ADDRESS),
        )
        return (
            INGETEAM_UNIT_COMMAND_DRIVER,
            start_address,
            tuple(registers),
        )

    def write_point_broadcast(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> dict[str, str | int | float | bool]:
        if point.protocol_meta.get("driver") != INGETEAM_UNIT_COMMAND_DRIVER:
            raise ValueError("Point is not handled by the Ingeteam command driver.")
        registers = self._build_register_payload(point, value)
        start_address = int(
            point.protocol_meta.get("command_start_address", INGETEAM_COMMAND_START_ADDRESS),
        )
        if device.protocol == "modbus_rtu":
            diagnostics = self._write_rtu_registers(
                device=device,
                start_address=start_address,
                registers=registers,
                broadcast=True,
            )
        elif device.protocol == "modbus_tcp":
            diagnostics = self._write_tcp_registers(
                device=device,
                start_address=start_address,
                registers=registers,
                broadcast=True,
            )
        else:
            raise NotImplementedError(
                f"Ingeteam broadcast is not supported for protocol {device.protocol}.",
            )

        return {
            **diagnostics,
            "driver": INGETEAM_UNIT_COMMAND_DRIVER,
            "profile_family": "unit_commands_1000_1002",
            "register_start": start_address,
            "register_count": len(registers),
            "command_code": registers[0],
            "encoded_values": ",".join(str(register) for register in registers),
            "encoded_values_hex": ",".join(f"0x{register:04X}" for register in registers),
            "requested_value": value,
            "write_function": "0x10" if len(registers) > 1 else "0x06",
        }

    def write_point(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> dict[str, str | int | float | bool]:
        if point.protocol_meta.get("driver") != INGETEAM_UNIT_COMMAND_DRIVER:
            raise ValueError("Point is not handled by the Ingeteam command driver.")

        registers = self._build_register_payload(point, value)
        start_address = int(
            point.protocol_meta.get("command_start_address", INGETEAM_COMMAND_START_ADDRESS),
        )

        if device.protocol == "modbus_rtu":
            diagnostics = self._write_rtu_registers(
                device=device,
                start_address=start_address,
                registers=registers,
            )
        elif device.protocol in {"modbus_tcp", "sunspec"}:
            diagnostics = self._write_tcp_registers(
                device=device,
                start_address=start_address,
                registers=registers,
            )
        else:
            raise NotImplementedError(
                f"Protocol {device.protocol} is not supported by the Ingeteam driver.",
            )

        return {
            **diagnostics,
            "driver": INGETEAM_UNIT_COMMAND_DRIVER,
            "profile_family": "unit_commands_1000_1002",
            "register_start": start_address,
            "register_count": len(registers),
            "command_code": registers[0],
            "encoded_values": ",".join(str(register) for register in registers),
            "encoded_values_hex": ",".join(f"0x{register:04X}" for register in registers),
            "requested_value": value,
            "write_function": "0x10" if len(registers) > 1 else "0x06",
        }

    def _build_register_payload(self, point: InverterPoint, value: float) -> list[int]:
        command_code = int(point.protocol_meta["command_code"])
        payload = [command_code]
        for word_spec in point.protocol_meta.get("command_words", []):
            if not isinstance(word_spec, dict):
                continue
            payload.append(self._encode_command_word(point, value, word_spec))
        return payload

    def _encode_command_word(
        self,
        point: InverterPoint,
        value: float,
        word_spec: dict[str, object],
    ) -> int:
        source = str(word_spec.get("source", "value"))
        encoding = str(word_spec.get("encoding", "scaled_int16"))

        if source == "fixed":
            raw_value = float(word_spec.get("value", 0))
        else:
            raw_value = float(value)

        if encoding == "percent_to_int16_32767":
            encoded = int(round((raw_value / 100.0) * 32767.0))
            return encoded & 0xFFFF
        if encoding == "fraction_to_int16_32767":
            encoded = int(round(raw_value * 32767.0))
            return encoded & 0xFFFF
        if encoding == "scaled_uint16":
            scaled = self._apply_inverse_point_scale(point, raw_value)
            return int(round(scaled)) & 0xFFFF
        if encoding == "scaled_int16":
            scaled = self._apply_inverse_point_scale(point, raw_value)
            return int(round(scaled)) & 0xFFFF
        if encoding == "raw_uint16":
            return int(round(raw_value)) & 0xFFFF
        if encoding == "raw_int16":
            return int(round(raw_value)) & 0xFFFF

        raise ValueError(f"Unsupported Ingeteam command encoding: {encoding}")

    def _apply_inverse_point_scale(self, point: InverterPoint, value: float) -> float:
        if point.scale in {0.0, 1.0}:
            return value
        return value / point.scale

    def _write_rtu_registers(
        self,
        *,
        device: DeviceResponse,
        start_address: int,
        registers: list[int],
        broadcast: bool = False,
    ) -> dict[str, str | int | float | bool]:
        port = str(device.connection_settings.get("port", ""))
        slave_id = 0 if broadcast else int(device.connection_settings.get("slave_id", 1))
        baud_rate = int(device.connection_settings.get("baud_rate", 9600))
        byte_size = int(device.connection_settings.get("byte_size", 8))
        parity = str(device.connection_settings.get("parity", "N"))
        stop_bits = int(device.connection_settings.get("stop_bits", 1))
        timeout_seconds = get_write_timeout_seconds(device.connection_settings)
        retries = get_write_retry_count(device.connection_settings)
        if not port:
            raise ValueError("Missing Modbus RTU port for Ingeteam command write.")

        def operation(client: object) -> tuple[object, str]:
            return self._write_registers(
                client=client,
                address=start_address,
                registers=registers,
                unit_value=slave_id,
                no_response_expected=broadcast,
            )

        response, unit_argument_style = connection_manager.execute_modbus_rtu(
            port=port,
            baudrate=baud_rate,
            bytesize=byte_size,
            parity=parity,
            stopbits=stop_bits,
            timeout=timeout_seconds,
            retries=retries,
            advanced_options=device.connection_settings,
            operation_kind="command",
            operation=operation,
        )
        if response is not None and response.isError():
            raise RuntimeError(f"Ingeteam Modbus RTU command failed: {response}")

        return {
            "port": port,
            "slave_id": slave_id,
            "broadcast": broadcast,
            "unit_argument_style": unit_argument_style,
        }

    def _write_tcp_registers(
        self,
        *,
        device: DeviceResponse,
        start_address: int,
        registers: list[int],
        broadcast: bool = False,
    ) -> dict[str, str | int | float | bool]:
        host = str(device.connection_settings.get("host", ""))
        port = int(device.connection_settings.get("port", 502))
        unit_id = 0 if broadcast else int(device.connection_settings.get("unit_id", 1))
        timeout_seconds = get_write_timeout_seconds(device.connection_settings)
        retries = get_write_retry_count(device.connection_settings)
        if not host:
            raise ValueError("Missing Modbus TCP host for Ingeteam command write.")

        def operation(client: object) -> tuple[object, str]:
            return self._write_registers(
                client=client,
                address=start_address,
                registers=registers,
                unit_value=unit_id,
                no_response_expected=broadcast,
            )

        response, unit_argument_style = connection_manager.execute_modbus_tcp(
            host=host,
            port=port,
            timeout=timeout_seconds,
            retries=retries,
            reset_after_operation=broadcast,
            operation_kind="command",
            operation=operation,
        )
        if response is not None and response.isError():
            raise RuntimeError(f"Ingeteam Modbus TCP command failed: {response}")

        return {
            "host": host,
            "port": port,
            "unit_id": unit_id,
            "broadcast": broadcast,
            "gateway_mode": "modbus_tcp" if broadcast else "unit_tcp",
            "unit_argument_style": unit_argument_style,
        }

    def _write_registers(
        self,
        *,
        client: object,
        address: int,
        registers: list[int],
        unit_value: int,
        no_response_expected: bool = False,
    ) -> tuple[object, str]:
        if len(registers) == 1:
            write_method = getattr(client, "write_register")
            write_args: tuple[object, ...] = (address, registers[0])
        else:
            write_method = getattr(client, "write_registers")
            write_args = (address, registers)

        try:
            response = write_method(
                *write_args,
                device_id=unit_value,
                no_response_expected=no_response_expected,
            )
            return response, "device_id"
        except TypeError:
            try:
                response = write_method(
                    *write_args,
                    slave=unit_value,
                    no_response_expected=no_response_expected,
                )
                return response, "slave"
            except TypeError:
                response = write_method(*write_args)
                return response, "none"


ingeteam_command_service = IngeteamCommandService()
