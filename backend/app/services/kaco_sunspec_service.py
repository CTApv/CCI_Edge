from dataclasses import dataclass
from threading import Lock

from app.core.connection_settings import (
    get_poll_retry_count,
    get_poll_timeout_seconds,
    get_write_retry_count,
    get_write_timeout_seconds,
)
from app.models.inverter_model import InverterPoint
from app.schemas.device_schemas import DeviceResponse
from app.services.connection_manager import connection_manager

KACO_SUNSPEC_DRIVER = "kaco_sunspec"
SUNSPEC_MAGIC_WORDS = (0x5375, 0x6E53)
SUNSPEC_BASE_ADDRESS = 40000
SUNSPEC_FIRST_MODEL_ADDRESS = SUNSPEC_BASE_ADDRESS + 2
SUNSPEC_END_MODEL_DID = 0xFFFF
SUNSPEC_MAX_MODELS = 128


@dataclass(slots=True, frozen=True)
class DiscoveredSunSpecModel:
    did: int
    start_address: int
    length: int


@dataclass(slots=True, frozen=True)
class ResolvedSunSpecPoint:
    point: InverterPoint
    model: DiscoveredSunSpecModel
    absolute_address: int
    register_type: str
    length: int
    datatype: str
    scale_factor_offset: int | None = None


class KacoSunSpecService:
    def __init__(self) -> None:
        self._cache_lock = Lock()
        self._map_cache: dict[tuple[object, ...], dict[int, list[DiscoveredSunSpecModel]]] = {}

    def read_points(
        self,
        device: DeviceResponse,
        points: list[InverterPoint],
    ) -> dict[str, str | int | float | bool | None]:
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

    def _execute_with_client(
        self,
        device: DeviceResponse,
        *,
        operation_kind: str,
        operation: callable,
    ) -> object:
        if device.protocol in {"modbus_tcp", "sunspec"}:
            host = str(device.connection_settings.get("host", ""))
            port = int(device.connection_settings.get("port", 502))
            unit_id = int(device.connection_settings.get("unit_id", 1))
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
                raise ValueError("Missing Modbus TCP host for KACO SunSpec driver.")

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
            slave_id = int(device.connection_settings.get("slave_id", 1))
            baud_rate = int(device.connection_settings.get("baud_rate", 19200))
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
                raise ValueError("Missing Modbus RTU port for KACO SunSpec driver.")

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

        raise NotImplementedError(f"Protocol {device.protocol} is not supported by KACO SunSpec.")

    def _read_points_with_client(
        self,
        *,
        client: object,
        device: DeviceResponse,
        unit_value: int,
        points: list[InverterPoint],
    ) -> dict[str, str | int | float | bool | None]:
        model_map = self._get_or_discover_model_map(
            client=client,
            device=device,
            unit_value=unit_value,
        )
        resolved_points = [
            resolved
            for point in points
            for resolved in [self._resolve_point(point=point, model_map=model_map)]
            if resolved is not None
        ]

        if not resolved_points:
            raise ValueError("No matching KACO SunSpec models were found in the device register map.")

        raw_values: dict[str, str | int | float | bool | None] = {}
        for register_type, blocks in self._group_points(resolved_points).items():
            for block in blocks:
                start_address = min(item.absolute_address for item in block)
                end_address = max(item.absolute_address + item.length - 1 for item in block)
                count = end_address - start_address + 1
                response = self._read_registers(
                    client=client,
                    register_type=register_type,
                    unit_value=unit_value,
                    address=start_address,
                    count=count,
                )
                if response.isError():
                    raise RuntimeError(
                        f"KACO SunSpec {register_type} read returned an error response.",
                    )

                registers = list(getattr(response, "registers", []))
                for resolved in block:
                    raw_values[resolved.point.key] = self._decode_register_value(
                        registers=registers,
                        start_address=start_address,
                        resolved_point=resolved,
                    )

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
        model_map = self._get_or_discover_model_map(
            client=client,
            device=device,
            unit_value=unit_value,
        )
        resolved_point = self._resolve_point(point=point, model_map=model_map)
        if resolved_point is None:
            raise ValueError("Required KACO SunSpec control model was not found in the device map.")

        encoded_values = self._encode_command_value(
            client=client,
            unit_value=unit_value,
            resolved_point=resolved_point,
            value=value,
        )
        response = self._write_registers(
            client=client,
            register_type=resolved_point.register_type,
            unit_value=unit_value,
            address=resolved_point.absolute_address,
            values=encoded_values,
        )
        if response.isError():
            raise RuntimeError(str(response))

        post_writes = resolved_point.point.protocol_meta.get("post_writes")
        if isinstance(post_writes, list):
            for post_write in post_writes:
                if not isinstance(post_write, dict):
                    continue
                only_if_model_did = self._coerce_int(post_write.get("only_if_model_did"))
                if only_if_model_did is not None and only_if_model_did != resolved_point.model.did:
                    continue
                resolved_post_write = self._resolve_ad_hoc_write(
                    model_map=model_map,
                    resolved_point=resolved_point,
                    write_definition=post_write,
                )
                if resolved_post_write is None:
                    continue
                post_values = self._encode_ad_hoc_write(
                    write_definition=post_write,
                    resolved_point=resolved_post_write,
                )
                post_response = self._write_registers(
                    client=client,
                    register_type=resolved_post_write.register_type,
                    unit_value=unit_value,
                    address=resolved_post_write.absolute_address,
                    values=post_values,
                )
                if post_response.isError():
                    raise RuntimeError(str(post_response))

        return {
            "stub_mode": False,
            "driver": KACO_SUNSPEC_DRIVER,
            "protocol": device.protocol,
            "model_did": resolved_point.model.did,
            "absolute_register": resolved_point.absolute_address,
            "requested_value": value,
        }

    def _get_or_discover_model_map(
        self,
        *,
        client: object,
        device: DeviceResponse,
        unit_value: int,
    ) -> dict[int, list[DiscoveredSunSpecModel]]:
        cache_key = self._build_cache_key(device, unit_value)
        with self._cache_lock:
            cached = self._map_cache.get(cache_key)
        if cached is not None:
            return cached

        discovered = self._discover_model_map(client=client, unit_value=unit_value)
        with self._cache_lock:
            self._map_cache[cache_key] = discovered
        return discovered

    def _build_cache_key(self, device: DeviceResponse, unit_value: int) -> tuple[object, ...]:
        if device.protocol == "modbus_rtu":
            return (
                KACO_SUNSPEC_DRIVER,
                device.protocol,
                device.connection_settings.get("port"),
                unit_value,
                device.connection_settings.get("baud_rate"),
                device.connection_settings.get("parity"),
                device.connection_settings.get("stop_bits"),
                device.connection_settings.get("byte_size"),
            )
        return (
            KACO_SUNSPEC_DRIVER,
            device.protocol,
            device.connection_settings.get("host"),
            device.connection_settings.get("port"),
            unit_value,
        )

    def _discover_model_map(
        self,
        *,
        client: object,
        unit_value: int,
    ) -> dict[int, list[DiscoveredSunSpecModel]]:
        response = self._read_registers(
            client=client,
            register_type="holding",
            unit_value=unit_value,
            address=SUNSPEC_BASE_ADDRESS,
            count=2,
        )
        if response.isError():
            raise RuntimeError("Unable to read SunSpec ID from KACO device.")

        registers = list(getattr(response, "registers", []))
        if len(registers) != 2 or tuple(registers) != SUNSPEC_MAGIC_WORDS:
            raise ValueError("SunSpec ID not found at holding registers 40000-40001.")

        discovered: dict[int, list[DiscoveredSunSpecModel]] = {}
        address = SUNSPEC_FIRST_MODEL_ADDRESS
        for _ in range(SUNSPEC_MAX_MODELS):
            header = self._read_registers(
                client=client,
                register_type="holding",
                unit_value=unit_value,
                address=address,
                count=2,
            )
            if header.isError():
                raise RuntimeError(f"Unable to read SunSpec model header at address {address}.")

            did, length = list(getattr(header, "registers", [0, 0]))
            if did == SUNSPEC_END_MODEL_DID:
                return discovered
            if length <= 0:
                raise ValueError(
                    f"Invalid SunSpec model length {length} discovered at address {address}.",
                )

            discovered.setdefault(did, []).append(
                DiscoveredSunSpecModel(did=did, start_address=address, length=length),
            )
            address += 2 + length

        raise ValueError("SunSpec end-of-map marker not found within the supported model limit.")

    def _resolve_point(
        self,
        *,
        point: InverterPoint,
        model_map: dict[int, list[DiscoveredSunSpecModel]],
    ) -> ResolvedSunSpecPoint | None:
        for candidate in self._iter_source_candidates(point):
            model_did = self._coerce_int(candidate.get("model_did"))
            offset = self._coerce_int(candidate.get("offset"))
            if model_did is None or offset is None:
                continue

            instance = self._coerce_int(candidate.get("instance"), default=0) or 0
            matching_models = model_map.get(model_did, [])
            if instance >= len(matching_models):
                continue

            model = matching_models[instance]
            length = self._coerce_int(candidate.get("length"), default=point.length) or point.length
            if offset + length - 1 > model.length + 1:
                continue

            return ResolvedSunSpecPoint(
                point=point,
                model=model,
                absolute_address=model.start_address + offset,
                register_type=str(candidate.get("register_type", point.register_type)),
                length=length,
                datatype=str(candidate.get("datatype", point.datatype)),
                scale_factor_offset=self._coerce_int(candidate.get("scale_factor_offset")),
            )

        return None

    def _resolve_ad_hoc_write(
        self,
        *,
        model_map: dict[int, list[DiscoveredSunSpecModel]],
        resolved_point: ResolvedSunSpecPoint,
        write_definition: dict[str, object],
    ) -> ResolvedSunSpecPoint | None:
        model_did = self._coerce_int(write_definition.get("model_did"), default=resolved_point.model.did)
        offset = self._coerce_int(write_definition.get("offset"))
        if model_did is None or offset is None:
            return None

        instance = self._coerce_int(write_definition.get("instance"), default=0) or 0
        matching_models = model_map.get(model_did, [])
        if instance >= len(matching_models):
            return None

        model = matching_models[instance]
        length = self._coerce_int(write_definition.get("length"), default=1) or 1
        return ResolvedSunSpecPoint(
            point=resolved_point.point,
            model=model,
            absolute_address=model.start_address + offset,
            register_type=str(write_definition.get("register_type", "holding")),
            length=length,
            datatype=str(write_definition.get("datatype", "uint16")),
            scale_factor_offset=self._coerce_int(write_definition.get("scale_factor_offset")),
        )

    def _iter_source_candidates(self, point: InverterPoint) -> list[dict[str, object]]:
        sources = point.protocol_meta.get("sources")
        if isinstance(sources, list):
            candidates = [candidate for candidate in sources if isinstance(candidate, dict)]
            if candidates:
                return candidates

        return [
            {
                "model_did": point.protocol_meta.get("model_did"),
                "offset": point.protocol_meta.get("offset"),
                "instance": point.protocol_meta.get("instance", 0),
                "register_type": point.register_type,
                "length": point.length,
                "datatype": point.datatype,
                "scale_factor_offset": point.protocol_meta.get("scale_factor_offset"),
            }
        ]

    def _group_points(
        self,
        points: list[ResolvedSunSpecPoint],
    ) -> dict[str, list[list[ResolvedSunSpecPoint]]]:
        grouped: dict[str, list[ResolvedSunSpecPoint]] = {}
        for point in points:
            grouped.setdefault(point.register_type, []).append(point)

        blocks_by_type: dict[str, list[list[ResolvedSunSpecPoint]]] = {}
        for register_type, register_points in grouped.items():
            sorted_points = sorted(register_points, key=lambda item: item.absolute_address)
            blocks: list[list[ResolvedSunSpecPoint]] = []
            current_block: list[ResolvedSunSpecPoint] = []
            current_end: int | None = None

            for point in sorted_points:
                point_end = point.absolute_address + point.length - 1
                if current_end is None or point.absolute_address > current_end + 1:
                    if current_block:
                        blocks.append(current_block)
                    current_block = [point]
                    current_end = point_end
                    continue

                current_block.append(point)
                current_end = max(current_end, point_end)

            if current_block:
                blocks.append(current_block)

            blocks_by_type[register_type] = blocks

        return blocks_by_type

    def _read_registers(
        self,
        *,
        client: object,
        register_type: str,
        unit_value: int,
        address: int,
        count: int,
    ) -> object:
        if register_type not in {"holding", "input"}:
            raise ValueError(f"Unsupported SunSpec register type: {register_type}")

        method_name = "read_holding_registers" if register_type == "holding" else "read_input_registers"
        read_method = getattr(client, method_name)

        try:
            return read_method(address, count=count, device_id=unit_value)
        except TypeError:
            try:
                return read_method(address, count=count, slave=unit_value)
            except TypeError:
                return read_method(address, count=count)

    def _write_registers(
        self,
        *,
        client: object,
        register_type: str,
        unit_value: int,
        address: int,
        values: list[int],
    ) -> object:
        if register_type != "holding":
            raise ValueError("SunSpec write operations are only supported on holding registers.")

        if len(values) == 1:
            method_name = "write_register"
            args = (address, values[0])
        else:
            method_name = "write_registers"
            args = (address, values)

        write_method = getattr(client, method_name)
        try:
            return write_method(*args, device_id=unit_value)
        except TypeError:
            try:
                return write_method(*args, slave=unit_value)
            except TypeError:
                return write_method(*args)

    def _decode_register_value(
        self,
        *,
        registers: list[int],
        start_address: int,
        resolved_point: ResolvedSunSpecPoint,
    ) -> str | int | float | bool | None:
        index = resolved_point.absolute_address - start_address
        raw_slice = registers[index : index + resolved_point.length]
        if not raw_slice:
            return None

        datatype = resolved_point.datatype
        if datatype == "int16":
            value = raw_slice[0]
            return value - 0x10000 if value >= 0x8000 else value
        if datatype == "uint16":
            return raw_slice[0]
        if datatype == "int32":
            value = (raw_slice[0] << 16) | (raw_slice[1] if len(raw_slice) > 1 else 0)
            return value - 0x100000000 if value >= 0x80000000 else value
        if datatype == "uint32":
            return (raw_slice[0] << 16) | (raw_slice[1] if len(raw_slice) > 1 else 0)
        if datatype == "int64":
            value = 0
            for register in raw_slice[:4]:
                value = (value << 16) | register
            return value - 0x10000000000000000 if value >= 0x8000000000000000 else value
        if datatype == "uint64":
            value = 0
            for register in raw_slice[:4]:
                value = (value << 16) | register
            return value
        if datatype == "ascii_string":
            raw_bytes = bytearray()
            for register in raw_slice:
                high_byte = (register >> 8) & 0xFF
                low_byte = register & 0xFF
                if high_byte:
                    raw_bytes.append(high_byte)
                if low_byte:
                    raw_bytes.append(low_byte)
            return bytes(raw_bytes).decode("ascii", errors="ignore").strip()

        return raw_slice[0]

    def _encode_command_value(
        self,
        *,
        client: object,
        unit_value: int,
        resolved_point: ResolvedSunSpecPoint,
        value: float,
    ) -> list[int]:
        scaled_value = value / resolved_point.point.scale if resolved_point.point.scale not in {0.0, 1.0} else value

        if resolved_point.scale_factor_offset is not None:
            scale_factor = self._read_scale_factor(
                client=client,
                unit_value=unit_value,
                model=resolved_point.model,
                register_type=resolved_point.register_type,
                offset=resolved_point.scale_factor_offset,
            )
            scaled_value = scaled_value / (10 ** scale_factor)

        integer_value = int(round(scaled_value))
        return self._encode_integer_value(integer_value=integer_value, datatype=resolved_point.datatype)

    def _encode_ad_hoc_write(
        self,
        *,
        write_definition: dict[str, object],
        resolved_point: ResolvedSunSpecPoint,
    ) -> list[int]:
        raw_value = self._coerce_int(write_definition.get("value"))
        if raw_value is None:
            raise ValueError("KACO SunSpec post write is missing a numeric value.")
        return self._encode_integer_value(integer_value=raw_value, datatype=resolved_point.datatype)

    def _read_scale_factor(
        self,
        *,
        client: object,
        unit_value: int,
        model: DiscoveredSunSpecModel,
        register_type: str,
        offset: int,
    ) -> int:
        response = self._read_registers(
            client=client,
            register_type=register_type,
            unit_value=unit_value,
            address=model.start_address + offset,
            count=1,
        )
        if response.isError():
            raise RuntimeError("Unable to read KACO SunSpec scale factor register.")

        registers = list(getattr(response, "registers", []))
        if not registers:
            raise RuntimeError("KACO SunSpec scale factor read returned no registers.")

        raw_value = registers[0]
        return raw_value - 0x10000 if raw_value >= 0x8000 else raw_value

    def _encode_integer_value(self, *, integer_value: int, datatype: str) -> list[int]:
        if datatype in {"uint16", "int16"}:
            return [integer_value & 0xFFFF]
        if datatype in {"uint32", "int32"}:
            normalized = integer_value & 0xFFFFFFFF
            return [(normalized >> 16) & 0xFFFF, normalized & 0xFFFF]
        if datatype in {"uint64", "int64"}:
            normalized = integer_value & 0xFFFFFFFFFFFFFFFF
            return [
                (normalized >> 48) & 0xFFFF,
                (normalized >> 32) & 0xFFFF,
                (normalized >> 16) & 0xFFFF,
                normalized & 0xFFFF,
            ]
        raise ValueError(f"Unsupported KACO SunSpec command datatype: {datatype}")

    def _coerce_int(self, value: object, *, default: int | None = None) -> int | None:
        if value in {None, ""}:
            return default
        return int(value)


kaco_sunspec_service = KacoSunSpecService()
