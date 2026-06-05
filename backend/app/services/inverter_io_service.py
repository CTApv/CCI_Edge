from dataclasses import dataclass
from struct import pack, unpack
from time import sleep

from pymodbus import FramerType

from app.core.connection_settings import (
    get_poll_retry_count,
    get_poll_timeout_seconds,
    get_write_retry_count,
    get_write_timeout_seconds,
)
from app.models.inverter_model import InverterModel, InverterPoint
from app.schemas.device_schemas import DeviceResponse
from app.services.aurora_service import (
    AURORA_DRIVER,
    aurora_service,
    extract_aurora_exception_diagnostics,
)
from app.services.bonfiglioli_modbus_service import (
    BONFIGLIOLI_DRIVER,
    bonfiglioli_modbus_service,
)
from app.services.connection_manager import connection_manager
from app.services.delta_rs485_service import DELTA_RS485_DRIVER, delta_rs485_service
from app.services.ingeteam_command_service import (
    INGETEAM_UNIT_COMMAND_DRIVER,
    ingeteam_command_service,
)
from app.services.kaco_sunspec_service import (
    KACO_SUNSPEC_DRIVER,
    kaco_sunspec_service,
)
from app.services.xantrex_modbus_service import (
    XANTREX_GT_DRIVER,
    xantrex_modbus_service,
)

ESSENTIAL_UNIT_GROUPS = {
    "power": {"kw", "w", "mw"},
    "voltage": {"v", "kv"},
    "current": {"a", "ka"},
    "frequency": {"hz"},
    "energy": {"kwh", "wh", "mwh"},
    "temperature": {"c", "degc", "°c"},
    "power_factor": {"", "cosphi", "pf"},
}
ESSENTIAL_TELEMETRY_CATEGORIES = (
    "active_power",
    "dc_power",
    "dc_voltage",
    "dc_current",
    "ac_voltage",
    "ac_current",
    "ac_frequency",
    "power_factor",
    "temperature",
    "total_energy",
)
ESSENTIAL_EXCLUDE_TERMS = {
    "fault",
    "guasto",
    "alarm",
    "allarme",
    "warning",
    "errore",
    "error",
    "rated",
    "nominal",
    "nominale",
    "nameplate",
    "targa",
    "limit",
    "limite",
    "max",
    "maximum",
    "min",
    "minimum",
    "reference",
    "riferimento",
    "setpoint",
    "target",
    "peak",
    "picco",
    "runtime",
    "tempo",
    "hours",
    "minutes",
    "second",
}


@dataclass(slots=True, frozen=True)
class TelemetryReadResult:
    values: dict[str, str | float | int | bool | None]
    unit_argument_style: str


@dataclass(slots=True, frozen=True)
class CommandWriteResult:
    success: bool
    diagnostics: dict[str, str | int | float | bool]
    error: str | None = None


class InverterIoService:
    def read_telemetry(
        self,
        device: DeviceResponse,
        inverter_model: InverterModel,
        *,
        essential_only: bool = False,
    ) -> TelemetryReadResult:
        points = (
            self._select_essential_readable_points(inverter_model.telemetry_points)
            if essential_only
            else self._select_readable_points(inverter_model.telemetry_points)
        )
        if not points:
            raise ValueError("Telemetry profile is not available for this model.")
        return self._read_telemetry_points(device, inverter_model, points)

    def read_heartbeat(
        self,
        device: DeviceResponse,
        inverter_model: InverterModel,
    ) -> TelemetryReadResult:
        probe_point = self._select_heartbeat_probe_point(inverter_model)
        if probe_point is not None:
            return self._read_telemetry_points(device, inverter_model, [probe_point])

        points = self._select_heartbeat_points(inverter_model.telemetry_points)
        if not points:
            return self.read_telemetry(device, inverter_model)
        return self._read_telemetry_points(device, inverter_model, points)

    def read_active_power_only(
        self,
        device: DeviceResponse,
        inverter_model: InverterModel,
    ) -> TelemetryReadResult:
        points = self._select_active_power_points(inverter_model.telemetry_points)
        if not points:
            return self.read_heartbeat(device, inverter_model)
        return self._read_telemetry_points(device, inverter_model, points)

    def _read_telemetry_points(
        self,
        device: DeviceResponse,
        inverter_model: InverterModel,
        points: list[InverterPoint],
    ) -> TelemetryReadResult:
        if device.protocol == "modbus_rtu":
            return self._read_modbus_rtu_telemetry(device, inverter_model, points)
        if device.protocol in {"modbus_tcp", "sunspec"}:
            return self._read_modbus_tcp_telemetry(device, inverter_model, points)
        if device.protocol == "delta_rs485":
            return self._read_delta_rs485_telemetry(device, inverter_model, points)
        if device.protocol == "aurora":
            return self._read_aurora_telemetry(device, inverter_model, points)
        raise NotImplementedError(f"Protocol {device.protocol} is not supported.")

    def write_command(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> CommandWriteResult:
        if device.protocol == "modbus_rtu":
            return self._write_modbus_rtu_command(device, point, value)
        if device.protocol in {"modbus_tcp", "sunspec"}:
            return self._write_modbus_tcp_command(device, point, value)
        if device.protocol == "delta_rs485":
            return self._write_delta_rs485_command(device, point, value)
        if device.protocol == "aurora":
            return self._write_aurora_command(device, point, value)
        return CommandWriteResult(
            success=False,
            diagnostics={"stub_mode": False, "stage": "protocol"},
            error=f"Protocol {device.protocol} is not supported.",
        )

    def build_command_broadcast_signature(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> tuple[object, ...] | None:
        if device.protocol not in {"modbus_rtu", "modbus_tcp"}:
            return None
        if point.register_type != "holding":
            return None

        if device.protocol == "modbus_tcp":
            if device.transport != "tcp":
                return None
            if self._uses_ingeteam_command_driver([point]):
                return ingeteam_command_service.build_broadcast_signature(point, value)
            if (
                self._uses_bonfiglioli_parameter_driver([point])
                or self._uses_kaco_sunspec_driver([point])
                or self._uses_xantrex_gt_driver([point])
            ):
                return None
        elif device.transport == "tcp" and (
            self._uses_bonfiglioli_parameter_driver([point])
            or self._uses_ingeteam_command_driver([point])
        ):
            return None

        if self._uses_bonfiglioli_parameter_driver([point]):
            return bonfiglioli_modbus_service.build_broadcast_signature(
                point,
                device.connection_settings,
                value,
            )
        if self._uses_ingeteam_command_driver([point]):
            return ingeteam_command_service.build_broadcast_signature(point, value)

        if (
            self._uses_kaco_sunspec_driver([point])
            or self._uses_xantrex_gt_driver([point])
        ):
            return None

        encoded_values = self._encode_command_value(value, point)
        if encoded_values is None:
            return None

        return (
            "generic_modbus",
            point.register_type,
            point.address,
            tuple(encoded_values),
            bool(point.protocol_meta.get("force_multi_write", False)),
        )

    def write_command_broadcast(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> CommandWriteResult:
        if device.protocol not in {"modbus_rtu", "modbus_tcp"}:
            return CommandWriteResult(
                success=False,
                diagnostics={"stub_mode": False, "stage": "protocol", "broadcast": True},
                error="Broadcast is only supported for Modbus RTU or Modbus TCP gateways.",
            )
        if point.register_type != "holding":
            return CommandWriteResult(
                success=False,
                diagnostics={"stub_mode": False, "stage": "profile", "broadcast": True},
                error="Broadcast writes are only supported on holding registers.",
            )

        if device.protocol == "modbus_tcp":
            if device.transport != "tcp":
                return CommandWriteResult(
                    success=False,
                    diagnostics={"stub_mode": False, "stage": "transport", "broadcast": True},
                    error="Modbus TCP broadcast requires a TCP gateway transport.",
                )
            if self._uses_ingeteam_command_driver([point]):
                try:
                    diagnostics = ingeteam_command_service.write_point_broadcast(
                        device,
                        point,
                        value,
                    )
                    return CommandWriteResult(
                        success=True,
                        diagnostics={**diagnostics, "requested_value": value},
                    )
                except Exception as exc:
                    return CommandWriteResult(
                        success=False,
                        diagnostics={
                            "stub_mode": False,
                            "stage": "write_ingeteam",
                            "driver": INGETEAM_UNIT_COMMAND_DRIVER,
                            "broadcast": True,
                            "gateway_mode": "modbus_tcp",
                        },
                        error=str(exc),
                    )
            if (
                self._uses_bonfiglioli_parameter_driver([point])
                or self._uses_kaco_sunspec_driver([point])
                or self._uses_xantrex_gt_driver([point])
            ):
                return CommandWriteResult(
                    success=False,
                    diagnostics={"stub_mode": False, "stage": "driver", "broadcast": True},
                    error="Modbus TCP broadcast is not enabled for custom command drivers.",
                )
            return self._write_modbus_tcp_broadcast_command(device, point, value)

        if device.transport == "tcp" and (
            self._uses_bonfiglioli_parameter_driver([point])
            or self._uses_ingeteam_command_driver([point])
        ):
            return CommandWriteResult(
                success=False,
                diagnostics={"stub_mode": False, "stage": "driver", "broadcast": True},
                error="RTU-over-TCP broadcast is not enabled for custom command drivers.",
            )

        if self._uses_bonfiglioli_parameter_driver([point]):
            try:
                diagnostics = bonfiglioli_modbus_service.write_point_broadcast(device, point, value)
                return CommandWriteResult(
                    success=True,
                    diagnostics={**diagnostics, "requested_value": value},
                )
            except Exception as exc:
                return CommandWriteResult(
                    success=False,
                    diagnostics={
                        "stub_mode": False,
                        "stage": "write_parameter",
                        "driver": BONFIGLIOLI_DRIVER,
                        "broadcast": True,
                    },
                    error=str(exc),
                )

        if self._uses_ingeteam_command_driver([point]):
            try:
                diagnostics = ingeteam_command_service.write_point_broadcast(device, point, value)
                return CommandWriteResult(
                    success=True,
                    diagnostics={**diagnostics, "requested_value": value},
                )
            except Exception as exc:
                return CommandWriteResult(
                    success=False,
                    diagnostics={
                        "stub_mode": False,
                        "stage": "write_ingeteam",
                        "driver": INGETEAM_UNIT_COMMAND_DRIVER,
                        "broadcast": True,
                    },
                    error=str(exc),
                )

        if (
            self._uses_kaco_sunspec_driver([point])
            or self._uses_xantrex_gt_driver([point])
        ):
            return CommandWriteResult(
                success=False,
                diagnostics={"stub_mode": False, "stage": "driver", "broadcast": True},
                error="Broadcast is not enabled for dynamic-map command drivers.",
            )

        return self._write_modbus_rtu_broadcast_command(device, point, value)

    def _read_modbus_tcp_telemetry(
        self,
        device: DeviceResponse,
        inverter_model: InverterModel,
        points: list[InverterPoint],
    ) -> TelemetryReadResult:
        host = str(device.connection_settings.get("host", ""))
        port = device.connection_settings.get("port")
        unit_id = device.connection_settings.get("unit_id")
        timeout_seconds = get_poll_timeout_seconds(
            device.connection_settings,
            transport=device.transport,
        )
        retries = get_poll_retry_count(
            device.connection_settings,
            transport=device.transport,
        )
        if not host or port is None or unit_id is None:
            raise ValueError("Missing Modbus TCP connection settings.")

        if self._uses_bonfiglioli_parameter_driver(points):
            raw_values = bonfiglioli_modbus_service.read_points(device, points)
            return TelemetryReadResult(
                values=self._apply_point_scaling(points, raw_values),
                unit_argument_style="bonfiglioli_parameter_modbus",
            )
        if self._uses_kaco_sunspec_driver(points):
            raw_values = kaco_sunspec_service.read_points(device, points)
            return TelemetryReadResult(
                values=self._apply_point_scaling(points, raw_values),
                unit_argument_style=KACO_SUNSPEC_DRIVER,
            )
        if self._uses_xantrex_gt_driver(points):
            raw_values = xantrex_modbus_service.read_points(device, points)
            return TelemetryReadResult(
                values=self._apply_point_scaling(points, raw_values),
                unit_argument_style=XANTREX_GT_DRIVER,
            )

        def operation(client: object) -> tuple[dict[str, str | float | int | bool | None], str]:
            raw_values: dict[str, str | int | float | bool | None] = {}
            unit_argument_style = "not_attempted"
            grouped_blocks = self._flatten_point_blocks(
                self._group_points(
                points,
                max_registers_per_request=device.connection_settings.get(
                    "max_registers_per_request",
                ),
                )
            )
            for block_index, (register_type, grouped_points) in enumerate(grouped_blocks):
                response, unit_argument_style = self._read_modbus_point_block_with_retry(
                    client=client,
                    register_type=register_type,
                    unit_value=int(unit_id),
                    points=grouped_points,
                    settings=device.connection_settings,
                )
                if response.isError():
                    if self._is_optional_point_block(grouped_points):
                        continue
                    raise RuntimeError(
                        f"Modbus TCP {register_type} telemetry read returned an error response."
                    )
                registers = list(response.registers)
                start_address = min(point.address for point in grouped_points)
                for point in grouped_points:
                    raw_values[point.key] = self._decode_register_value(
                        registers=registers,
                        start_address=start_address,
                        point=point,
                    )
                if block_index < len(grouped_blocks) - 1:
                    self._wait_between_requests(device.connection_settings)
            return self._apply_point_scaling(points, raw_values), unit_argument_style

        values, unit_argument_style = connection_manager.execute_modbus_tcp(
            host=host,
            port=int(port),
            timeout=timeout_seconds,
            retries=retries,
            operation=operation,
        )
        return TelemetryReadResult(values=values, unit_argument_style=unit_argument_style)

    def _read_modbus_rtu_telemetry(
        self,
        device: DeviceResponse,
        inverter_model: InverterModel,
        points: list[InverterPoint],
    ) -> TelemetryReadResult:
        if device.transport == "tcp":
            host = str(device.connection_settings.get("host", ""))
            port = device.connection_settings.get("port")
            unit_id = device.connection_settings.get("unit_id")
            if unit_id is None:
                unit_id = device.connection_settings.get("slave_id")
            timeout_seconds = get_poll_timeout_seconds(
                device.connection_settings,
                transport=device.transport,
                serial_gateway=True,
            )
            retries = get_poll_retry_count(
                device.connection_settings,
                transport=device.transport,
                serial_gateway=True,
            )
            if not host or port is None or unit_id is None:
                raise ValueError("Missing Modbus RTU over TCP connection settings.")

            def operation(client: object) -> tuple[dict[str, str | float | int | bool | None], str]:
                raw_values: dict[str, str | int | float | bool | None] = {}
                unit_argument_style = "not_attempted"
                grouped_blocks = self._flatten_point_blocks(
                    self._group_points(
                        points,
                        max_registers_per_request=device.connection_settings.get(
                            "max_registers_per_request",
                        ),
                    )
                )
                for block_index, (register_type, grouped_points) in enumerate(grouped_blocks):
                    response, unit_argument_style = self._read_modbus_point_block_with_retry(
                        client=client,
                        register_type=register_type,
                        unit_value=int(unit_id),
                        points=grouped_points,
                        settings=device.connection_settings,
                    )
                    if response.isError():
                        if self._is_optional_point_block(grouped_points):
                            continue
                        raise RuntimeError(
                            f"Modbus RTU over TCP {register_type} telemetry read returned an error response."
                        )
                    registers = list(response.registers)
                    start_address = min(point.address for point in grouped_points)
                    for point in grouped_points:
                        raw_values[point.key] = self._decode_register_value(
                            registers=registers,
                            start_address=start_address,
                            point=point,
                        )
                    if block_index < len(grouped_blocks) - 1:
                        self._wait_between_requests(device.connection_settings)
                return self._apply_point_scaling(points, raw_values), unit_argument_style

            values, unit_argument_style = connection_manager.execute_modbus_tcp(
                host=host,
                port=int(port),
                framer=FramerType.RTU,
                timeout=timeout_seconds,
                retries=retries,
                reset_after_operation=True,
                operation=operation,
            )
            return TelemetryReadResult(values=values, unit_argument_style=unit_argument_style)

        port = str(device.connection_settings.get("port", ""))
        slave_id = device.connection_settings.get("slave_id")
        baud_rate = device.connection_settings.get("baud_rate")
        byte_size = device.connection_settings.get("byte_size")
        parity = device.connection_settings.get("parity")
        stop_bits = device.connection_settings.get("stop_bits")
        timeout_seconds = get_poll_timeout_seconds(
            device.connection_settings,
            transport=device.transport,
        )
        retries = get_poll_retry_count(
            device.connection_settings,
            transport=device.transport,
        )
        if (
            not port
            or slave_id is None
            or baud_rate is None
            or byte_size is None
            or parity is None
            or stop_bits is None
        ):
            raise ValueError("Missing Modbus RTU connection settings.")

        if self._uses_bonfiglioli_parameter_driver(points):
            raw_values = bonfiglioli_modbus_service.read_points(device, points)
            return TelemetryReadResult(
                values=self._apply_point_scaling(points, raw_values),
                unit_argument_style="bonfiglioli_parameter_modbus",
            )
        if self._uses_kaco_sunspec_driver(points):
            raw_values = kaco_sunspec_service.read_points(device, points)
            return TelemetryReadResult(
                values=self._apply_point_scaling(points, raw_values),
                unit_argument_style=KACO_SUNSPEC_DRIVER,
            )
        if self._uses_xantrex_gt_driver(points):
            raw_values = xantrex_modbus_service.read_points(device, points)
            return TelemetryReadResult(
                values=self._apply_point_scaling(points, raw_values),
                unit_argument_style=XANTREX_GT_DRIVER,
            )

        def operation(client: object) -> tuple[dict[str, str | float | int | bool | None], str]:
            raw_values: dict[str, str | int | float | bool | None] = {}
            unit_argument_style = "not_attempted"
            grouped_blocks = self._flatten_point_blocks(
                self._group_points(
                points,
                max_registers_per_request=device.connection_settings.get(
                    "max_registers_per_request",
                ),
                )
            )
            for block_index, (register_type, grouped_points) in enumerate(grouped_blocks):
                response, unit_argument_style = self._read_modbus_point_block_with_retry(
                    client=client,
                    register_type=register_type,
                    unit_value=int(slave_id),
                    points=grouped_points,
                    settings=device.connection_settings,
                )
                if response.isError():
                    if self._is_optional_point_block(grouped_points):
                        continue
                    raise RuntimeError(
                        f"Modbus RTU {register_type} telemetry read returned an error response."
                    )
                registers = list(response.registers)
                start_address = min(point.address for point in grouped_points)
                for point in grouped_points:
                    raw_values[point.key] = self._decode_register_value(
                        registers=registers,
                        start_address=start_address,
                        point=point,
                    )
                if block_index < len(grouped_blocks) - 1:
                    self._wait_between_requests(device.connection_settings)
            return self._apply_point_scaling(points, raw_values), unit_argument_style

        values, unit_argument_style = connection_manager.execute_modbus_rtu(
            port=port,
            baudrate=int(baud_rate),
            bytesize=int(byte_size),
            parity=str(parity),
            stopbits=int(stop_bits),
            timeout=float(timeout_seconds),
            retries=int(retries),
            advanced_options=device.connection_settings,
            operation=operation,
        )
        return TelemetryReadResult(values=values, unit_argument_style=unit_argument_style)

    def _read_delta_rs485_telemetry(
        self,
        device: DeviceResponse,
        inverter_model: InverterModel,
        points: list[InverterPoint],
    ) -> TelemetryReadResult:
        raw_values = delta_rs485_service.read_points(device, inverter_model, points)
        return TelemetryReadResult(
            values=self._apply_point_scaling(points, raw_values),
            unit_argument_style=DELTA_RS485_DRIVER,
        )

    def _read_aurora_telemetry(
        self,
        device: DeviceResponse,
        inverter_model: InverterModel,
        points: list[InverterPoint],
    ) -> TelemetryReadResult:
        raw_values = aurora_service.read_points(device, inverter_model, points)
        return TelemetryReadResult(
            values=self._apply_point_scaling(points, raw_values),
            unit_argument_style=AURORA_DRIVER,
        )

    def _write_modbus_tcp_command(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> CommandWriteResult:
        host = str(device.connection_settings.get("host", ""))
        port = device.connection_settings.get("port")
        unit_id = device.connection_settings.get("unit_id")
        timeout_seconds = get_write_timeout_seconds(device.connection_settings)
        retries = get_write_retry_count(device.connection_settings)
        if not host or port is None or unit_id is None:
            return CommandWriteResult(
                success=False,
                diagnostics={"stub_mode": False, "stage": "settings"},
                error="Missing Modbus TCP connection settings.",
            )

        encoded_values = self._encode_command_value(value, point)
        if encoded_values is None:
            return CommandWriteResult(
                success=False,
                diagnostics={"stub_mode": False, "stage": "profile"},
                error="Unsupported command datatype.",
            )

        if self._uses_bonfiglioli_parameter_driver([point]):
            try:
                diagnostics = bonfiglioli_modbus_service.write_point(device, point, value)
                return CommandWriteResult(
                    success=True,
                    diagnostics={**diagnostics, "requested_value": value},
                )
            except Exception as exc:
                return CommandWriteResult(
                    success=False,
                    diagnostics={
                        "stub_mode": False,
                        "stage": "write_parameter",
                        "driver": BONFIGLIOLI_DRIVER,
                    },
                    error=str(exc),
                )
        if self._uses_ingeteam_command_driver([point]):
            try:
                diagnostics = ingeteam_command_service.write_point(device, point, value)
                return CommandWriteResult(
                    success=True,
                    diagnostics={**diagnostics, "requested_value": value},
                )
            except Exception as exc:
                return CommandWriteResult(
                    success=False,
                    diagnostics={
                        "stub_mode": False,
                        "stage": "write_ingeteam",
                        "driver": INGETEAM_UNIT_COMMAND_DRIVER,
                    },
                    error=str(exc),
                )
        if self._uses_kaco_sunspec_driver([point]):
            try:
                diagnostics = kaco_sunspec_service.write_point(device, point, value)
                return CommandWriteResult(
                    success=True,
                    diagnostics={**diagnostics, "requested_value": value},
                )
            except Exception as exc:
                return CommandWriteResult(
                    success=False,
                    diagnostics={
                        "stub_mode": False,
                        "stage": "write_sunspec",
                        "driver": KACO_SUNSPEC_DRIVER,
                    },
                    error=str(exc),
                )
        if self._uses_xantrex_gt_driver([point]):
            try:
                diagnostics = xantrex_modbus_service.write_point(device, point, value)
                return CommandWriteResult(
                    success=True,
                    diagnostics={**diagnostics, "requested_value": value},
                )
            except Exception as exc:
                return CommandWriteResult(
                    success=False,
                    diagnostics={
                        "stub_mode": False,
                        "stage": "write_xantrex",
                        "driver": XANTREX_GT_DRIVER,
                    },
                    error=str(exc),
                )

        def operation(client: object) -> tuple[object, str]:
            return self._write_modbus_point_with_retry(
                client=client,
                register_type=point.register_type,
                unit_value=int(unit_id),
                address=point.address,
                values=encoded_values,
                settings=device.connection_settings,
                force_multiple=bool(point.protocol_meta.get("force_multi_write", False)),
            )

        response, unit_argument_style = connection_manager.execute_modbus_tcp(
            host=host,
            port=int(port),
            timeout=timeout_seconds,
            retries=retries,
            operation_kind="command",
            operation=operation,
        )

        return CommandWriteResult(
            success=not response.isError(),
            diagnostics={
                "stub_mode": False,
                "host": host,
                "port": int(port),
                "unit_id": int(unit_id),
                "register": point.address,
                "register_type": point.register_type,
                "requested_value": value,
                "encoded_values": ",".join(str(item) for item in encoded_values),
                "unit_argument_style": unit_argument_style,
            },
            error=str(response) if response.isError() else None,
        )

    def _write_modbus_rtu_command(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> CommandWriteResult:
        if device.transport == "tcp":
            host = str(device.connection_settings.get("host", ""))
            port = device.connection_settings.get("port")
            unit_id = device.connection_settings.get("unit_id")
            if unit_id is None:
                unit_id = device.connection_settings.get("slave_id")
            timeout_seconds = get_write_timeout_seconds(device.connection_settings)
            retries = get_write_retry_count(device.connection_settings)
            if not host or port is None or unit_id is None:
                return CommandWriteResult(
                    success=False,
                    diagnostics={"stub_mode": False, "stage": "settings"},
                    error="Missing Modbus RTU over TCP connection settings.",
                )

            encoded_values = self._encode_command_value(value, point)
            if encoded_values is None:
                return CommandWriteResult(
                    success=False,
                    diagnostics={"stub_mode": False, "stage": "profile"},
                    error="Unsupported command datatype.",
                )

            def operation(client: object) -> tuple[object, str]:
                return self._write_modbus_point_with_retry(
                    client=client,
                    register_type=point.register_type,
                    unit_value=int(unit_id),
                    address=point.address,
                    values=encoded_values,
                    settings=device.connection_settings,
                    force_multiple=bool(point.protocol_meta.get("force_multi_write", False)),
                )

            response, unit_argument_style = connection_manager.execute_modbus_tcp(
                host=host,
                port=int(port),
                framer=FramerType.RTU,
                timeout=float(timeout_seconds),
                retries=int(retries),
                reset_after_operation=True,
                operation_kind="command",
                operation=operation,
            )

            return CommandWriteResult(
                success=not response.isError(),
                diagnostics={
                    "stub_mode": False,
                    "host": host,
                    "port": int(port),
                    "unit_id": int(unit_id),
                    "register": point.address,
                    "register_type": point.register_type,
                    "requested_value": value,
                    "encoded_values": ",".join(str(item) for item in encoded_values),
                    "unit_argument_style": unit_argument_style,
                    "gateway_mode": "rtu_over_tcp",
                },
                error=str(response) if response.isError() else None,
            )

        port = str(device.connection_settings.get("port", ""))
        slave_id = device.connection_settings.get("slave_id")
        baud_rate = device.connection_settings.get("baud_rate")
        byte_size = device.connection_settings.get("byte_size")
        parity = device.connection_settings.get("parity")
        stop_bits = device.connection_settings.get("stop_bits")
        timeout_seconds = get_write_timeout_seconds(device.connection_settings)
        retries = get_write_retry_count(device.connection_settings)
        if (
            not port
            or slave_id is None
            or baud_rate is None
            or byte_size is None
            or parity is None
            or stop_bits is None
        ):
            return CommandWriteResult(
                success=False,
                diagnostics={"stub_mode": False, "stage": "settings"},
                error="Missing Modbus RTU connection settings.",
            )

        encoded_values = self._encode_command_value(value, point)
        if encoded_values is None:
            return CommandWriteResult(
                success=False,
                diagnostics={"stub_mode": False, "stage": "profile"},
                error="Unsupported command datatype.",
            )

        if self._uses_bonfiglioli_parameter_driver([point]):
            try:
                diagnostics = bonfiglioli_modbus_service.write_point(device, point, value)
                return CommandWriteResult(
                    success=True,
                    diagnostics={**diagnostics, "requested_value": value},
                )
            except Exception as exc:
                return CommandWriteResult(
                    success=False,
                    diagnostics={
                        "stub_mode": False,
                        "stage": "write_parameter",
                        "driver": BONFIGLIOLI_DRIVER,
                    },
                    error=str(exc),
                )
        if self._uses_ingeteam_command_driver([point]):
            try:
                diagnostics = ingeteam_command_service.write_point(device, point, value)
                return CommandWriteResult(
                    success=True,
                    diagnostics={**diagnostics, "requested_value": value},
                )
            except Exception as exc:
                return CommandWriteResult(
                    success=False,
                    diagnostics={
                        "stub_mode": False,
                        "stage": "write_ingeteam",
                        "driver": INGETEAM_UNIT_COMMAND_DRIVER,
                    },
                    error=str(exc),
                )
        if self._uses_kaco_sunspec_driver([point]):
            try:
                diagnostics = kaco_sunspec_service.write_point(device, point, value)
                return CommandWriteResult(
                    success=True,
                    diagnostics={**diagnostics, "requested_value": value},
                )
            except Exception as exc:
                return CommandWriteResult(
                    success=False,
                    diagnostics={
                        "stub_mode": False,
                        "stage": "write_sunspec",
                        "driver": KACO_SUNSPEC_DRIVER,
                    },
                    error=str(exc),
                )
        if self._uses_xantrex_gt_driver([point]):
            try:
                diagnostics = xantrex_modbus_service.write_point(device, point, value)
                return CommandWriteResult(
                    success=True,
                    diagnostics={**diagnostics, "requested_value": value},
                )
            except Exception as exc:
                return CommandWriteResult(
                    success=False,
                    diagnostics={
                        "stub_mode": False,
                        "stage": "write_xantrex",
                        "driver": XANTREX_GT_DRIVER,
                    },
                    error=str(exc),
                )

        def operation(client: object) -> tuple[object, str]:
            return self._write_modbus_point_with_retry(
                client=client,
                register_type=point.register_type,
                unit_value=int(slave_id),
                address=point.address,
                values=encoded_values,
                settings=device.connection_settings,
                force_multiple=bool(point.protocol_meta.get("force_multi_write", False)),
            )

        response, unit_argument_style = connection_manager.execute_modbus_rtu(
            port=port,
            baudrate=int(baud_rate),
            bytesize=int(byte_size),
            parity=str(parity),
            stopbits=int(stop_bits),
            timeout=float(timeout_seconds),
            retries=int(retries),
            advanced_options=device.connection_settings,
            operation_kind="command",
            operation=operation,
        )

        return CommandWriteResult(
            success=not response.isError(),
            diagnostics={
                "stub_mode": False,
                "port": port,
                "slave_id": int(slave_id),
                "register": point.address,
                "register_type": point.register_type,
                "requested_value": value,
                "encoded_values": ",".join(str(item) for item in encoded_values),
                "unit_argument_style": unit_argument_style,
            },
            error=str(response) if response.isError() else None,
        )

    def _write_modbus_rtu_broadcast_command(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> CommandWriteResult:
        if device.transport == "tcp":
            return self._write_modbus_rtu_over_tcp_broadcast_command(device, point, value)

        port = str(device.connection_settings.get("port", ""))
        baud_rate = device.connection_settings.get("baud_rate")
        byte_size = device.connection_settings.get("byte_size")
        parity = device.connection_settings.get("parity")
        stop_bits = device.connection_settings.get("stop_bits")
        timeout_seconds = get_write_timeout_seconds(device.connection_settings)
        retries = get_write_retry_count(device.connection_settings)
        if (
            not port
            or baud_rate is None
            or byte_size is None
            or parity is None
            or stop_bits is None
        ):
            return CommandWriteResult(
                success=False,
                diagnostics={"stub_mode": False, "stage": "settings", "broadcast": True},
                error="Missing Modbus RTU connection settings.",
            )

        encoded_values = self._encode_command_value(value, point)
        if encoded_values is None:
            return CommandWriteResult(
                success=False,
                diagnostics={"stub_mode": False, "stage": "profile", "broadcast": True},
                error="Unsupported command datatype.",
            )

        def operation(client: object) -> tuple[object, str]:
            return self._write_modbus_point(
                client=client,
                register_type=point.register_type,
                unit_value=0,
                address=point.address,
                values=encoded_values,
                force_multiple=bool(point.protocol_meta.get("force_multi_write", False)),
                no_response_expected=True,
            )

        response, unit_argument_style = connection_manager.execute_modbus_rtu(
            port=port,
            baudrate=int(baud_rate),
            bytesize=int(byte_size),
            parity=str(parity),
            stopbits=int(stop_bits),
            timeout=float(timeout_seconds),
            retries=int(retries),
            advanced_options=device.connection_settings,
            operation_kind="command",
            operation=operation,
        )
        has_error = response is not None and response.isError()

        return CommandWriteResult(
            success=not has_error,
            diagnostics={
                "stub_mode": False,
                "port": port,
                "slave_id": 0,
                "broadcast": True,
                "register": point.address,
                "register_type": point.register_type,
                "requested_value": value,
                "encoded_values": ",".join(str(item) for item in encoded_values),
                "unit_argument_style": unit_argument_style,
            },
            error=str(response) if has_error else None,
        )

    def _write_modbus_tcp_broadcast_command(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> CommandWriteResult:
        host = str(device.connection_settings.get("host", ""))
        port = device.connection_settings.get("port")
        timeout_seconds = get_write_timeout_seconds(device.connection_settings)
        retries = get_write_retry_count(device.connection_settings)
        if not host or port is None:
            return CommandWriteResult(
                success=False,
                diagnostics={
                    "stub_mode": False,
                    "stage": "settings",
                    "broadcast": True,
                    "gateway_mode": "modbus_tcp",
                },
                error="Missing Modbus TCP gateway connection settings.",
            )

        encoded_values = self._encode_command_value(value, point)
        if encoded_values is None:
            return CommandWriteResult(
                success=False,
                diagnostics={
                    "stub_mode": False,
                    "stage": "profile",
                    "broadcast": True,
                    "gateway_mode": "modbus_tcp",
                },
                error="Unsupported command datatype.",
            )

        def operation(client: object) -> tuple[object, str]:
            return self._write_modbus_point(
                client=client,
                register_type=point.register_type,
                unit_value=0,
                address=point.address,
                values=encoded_values,
                force_multiple=bool(point.protocol_meta.get("force_multi_write", False)),
                no_response_expected=True,
            )

        response, unit_argument_style = connection_manager.execute_modbus_tcp(
            host=host,
            port=int(port),
            framer=FramerType.SOCKET,
            timeout=float(timeout_seconds),
            retries=int(retries),
            reset_after_operation=True,
            operation_kind="command",
            operation=operation,
        )
        has_error = response is not None and response.isError()

        return CommandWriteResult(
            success=not has_error,
            diagnostics={
                "stub_mode": False,
                "host": host,
                "port": int(port),
                "unit_id": 0,
                "broadcast": True,
                "register": point.address,
                "register_type": point.register_type,
                "requested_value": value,
                "encoded_values": ",".join(str(item) for item in encoded_values),
                "unit_argument_style": unit_argument_style,
                "gateway_mode": "modbus_tcp",
            },
            error=str(response) if has_error else None,
        )

    def _write_modbus_rtu_over_tcp_broadcast_command(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> CommandWriteResult:
        host = str(device.connection_settings.get("host", ""))
        port = device.connection_settings.get("port")
        timeout_seconds = get_write_timeout_seconds(device.connection_settings)
        retries = get_write_retry_count(device.connection_settings)
        if not host or port is None:
            return CommandWriteResult(
                success=False,
                diagnostics={
                    "stub_mode": False,
                    "stage": "settings",
                    "broadcast": True,
                    "gateway_mode": "rtu_over_tcp",
                },
                error="Missing Modbus RTU over TCP connection settings.",
            )

        encoded_values = self._encode_command_value(value, point)
        if encoded_values is None:
            return CommandWriteResult(
                success=False,
                diagnostics={
                    "stub_mode": False,
                    "stage": "profile",
                    "broadcast": True,
                    "gateway_mode": "rtu_over_tcp",
                },
                error="Unsupported command datatype.",
            )

        def operation(client: object) -> tuple[object, str]:
            return self._write_modbus_point(
                client=client,
                register_type=point.register_type,
                unit_value=0,
                address=point.address,
                values=encoded_values,
                force_multiple=bool(point.protocol_meta.get("force_multi_write", False)),
                no_response_expected=True,
            )

        response, unit_argument_style = connection_manager.execute_modbus_tcp(
            host=host,
            port=int(port),
            framer=FramerType.RTU,
            timeout=float(timeout_seconds),
            retries=int(retries),
            reset_after_operation=True,
            operation_kind="command",
            operation=operation,
        )
        has_error = response is not None and response.isError()

        return CommandWriteResult(
            success=not has_error,
            diagnostics={
                "stub_mode": False,
                "host": host,
                "port": int(port),
                "unit_id": 0,
                "broadcast": True,
                "register": point.address,
                "register_type": point.register_type,
                "requested_value": value,
                "encoded_values": ",".join(str(item) for item in encoded_values),
                "unit_argument_style": unit_argument_style,
                "gateway_mode": "rtu_over_tcp",
            },
            error=str(response) if has_error else None,
        )

    def _write_delta_rs485_command(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> CommandWriteResult:
        try:
            diagnostics = delta_rs485_service.write_point(device, point, value)
            return CommandWriteResult(
                success=True,
                diagnostics=diagnostics,
            )
        except Exception as exc:
            return CommandWriteResult(
                success=False,
                diagnostics={
                    "stub_mode": False,
                    "stage": "write_delta",
                    "driver": DELTA_RS485_DRIVER,
                    "requested_value": value,
                },
                error=str(exc),
            )

    def _write_aurora_command(
        self,
        device: DeviceResponse,
        point: InverterPoint,
        value: float,
    ) -> CommandWriteResult:
        try:
            diagnostics = aurora_service.write_point(device, point, value)
            return CommandWriteResult(
                success=True,
                diagnostics=diagnostics,
            )
        except Exception as exc:
            return CommandWriteResult(
                success=False,
                diagnostics={
                    "stub_mode": False,
                    "stage": "write_aurora",
                    "driver": AURORA_DRIVER,
                    "requested_value": value,
                    **extract_aurora_exception_diagnostics(exc),
                },
                error=str(exc),
            )

    def _group_points(
        self,
        points: list[InverterPoint],
        *,
        max_registers_per_request: object | None = None,
    ) -> dict[str, list[list[InverterPoint]]]:
        grouped: dict[str, list[InverterPoint]] = {}
        for point in points:
            grouped.setdefault(point.register_type, []).append(point)

        request_limit = self._parse_max_registers_per_request(max_registers_per_request)
        chunked_groups: dict[str, list[list[InverterPoint]]] = {}
        for register_type, register_points in grouped.items():
            sorted_points = sorted(register_points, key=lambda item: item.address)
            blocks: list[list[InverterPoint]] = []
            current_block: list[InverterPoint] = []
            current_start: int | None = None
            current_end: int | None = None

            for point in sorted_points:
                point_span = point.length
                if request_limit is not None and point_span > request_limit:
                    raise ValueError(
                        f"Point {point.key} length exceeds max_registers_per_request.",
                    )

                point_end = point.address + point.length - 1
                if current_start is None:
                    current_block = [point]
                    current_start = point.address
                    current_end = point_end
                    continue

                is_contiguous = current_end is not None and point.address <= current_end + 1
                next_span = point_end - current_start + 1
                exceeds_request_limit = request_limit is not None and next_span > request_limit
                current_optional = self._is_optional_point_block(current_block)
                point_optional = bool(point.protocol_meta.get("optional_block", False))
                if (
                    not is_contiguous
                    or exceeds_request_limit
                    or current_optional != point_optional
                ):
                    blocks.append(current_block)
                    current_block = [point]
                    current_start = point.address
                    current_end = point_end
                    continue

                current_block.append(point)
                current_end = max(current_end or point_end, point_end)

            if current_block:
                blocks.append(current_block)

            chunked_groups[register_type] = blocks

        return chunked_groups

    def _flatten_point_blocks(
        self,
        grouped_blocks: dict[str, list[list[InverterPoint]]],
    ) -> list[tuple[str, list[InverterPoint]]]:
        flattened: list[tuple[str, list[InverterPoint]]] = []
        for register_type, point_blocks in grouped_blocks.items():
            for point_block in point_blocks:
                flattened.append((register_type, point_block))
        return flattened

    def _select_readable_points(self, points: list[InverterPoint]) -> list[InverterPoint]:
        referenced_scale_keys = {
            point.scale_factor_key for point in points if point.scale_factor_key is not None
        }
        return [
            point
            for point in points
            if point.visible or point.key in referenced_scale_keys
        ]

    def _select_essential_readable_points(self, points: list[InverterPoint]) -> list[InverterPoint]:
        readable_points = self._select_readable_points(points)
        selected: list[InverterPoint] = []
        selected_keys: set[str] = set()

        def add_point(point: InverterPoint | None) -> None:
            if point is None or point.key in selected_keys:
                return
            selected.append(point)
            selected_keys.add(point.key)

        for category in ESSENTIAL_TELEMETRY_CATEGORIES:
            add_point(self._best_essential_point_for_category(readable_points, category))

        if not selected:
            for point in self._select_heartbeat_points(points):
                add_point(point)

        return self._with_scale_factor_dependencies(selected, readable_points)

    def _select_active_power_points(self, points: list[InverterPoint]) -> list[InverterPoint]:
        readable_points = self._select_readable_points(points)
        active_power_point = self._best_essential_point_for_category(
            readable_points,
            "active_power",
        )
        if active_power_point is not None:
            return self._with_scale_factor_dependencies([active_power_point], readable_points)
        return self._select_heartbeat_points(points)


    def _best_essential_point_for_category(
        self,
        readable_points: list[InverterPoint],
        category: str,
    ) -> InverterPoint | None:
        candidates = [
            (self._essential_category_score(point, category), point)
            for point in readable_points
        ]
        candidates = [(score, point) for score, point in candidates if score > 0]
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _essential_category_score(self, point: InverterPoint, category: str) -> int:
        fingerprint = self._point_fingerprint(point)
        unit = self._normalized_unit(point.unit)
        if self._has_any_term(fingerprint, ESSENTIAL_EXCLUDE_TERMS):
            return 0

        summary_metric = point.protocol_meta.get("summary_metric")
        score = 1

        if category == "active_power":
            if summary_metric == "power_kw":
                score += 1_000
            elif not self._is_active_power_point(fingerprint, unit):
                return 0
            score += self._preferred_term_score(fingerprint, ("active_power", "active power", "potenza attiva"))
        elif category == "dc_power":
            if not self._is_dc_power_point(fingerprint, unit):
                return 0
            score += self._preferred_term_score(fingerprint, ("total", "totale", "input_power", "pv_input", "dc_power"))
        elif category == "dc_voltage":
            if not self._is_dc_voltage_point(fingerprint, unit):
                return 0
            score += self._preferred_term_score(fingerprint, ("dc_link", "dc bus", "bus", "pv_1", "input_1"))
        elif category == "dc_current":
            if not self._is_dc_current_point(fingerprint, unit):
                return 0
            score += self._preferred_term_score(fingerprint, ("dc_current", "pv_1", "input_1"))
        elif category == "ac_voltage":
            if not self._is_ac_voltage_point(fingerprint, unit):
                return 0
            score += self._preferred_term_score(fingerprint, ("grid_voltage", "mains_voltage", "line_voltage", "phase_a", " l1"))
        elif category == "ac_current":
            if not self._is_ac_current_point(fingerprint, unit):
                return 0
            score += self._preferred_term_score(fingerprint, ("grid_current", "mains_current", "phase_a", "current_a", " l1"))
        elif category == "ac_frequency":
            if not self._is_ac_frequency_point(fingerprint, unit):
                return 0
            score += self._preferred_term_score(fingerprint, ("grid", "mains", "rete", "ac"))
        elif category == "power_factor":
            if not self._is_power_factor_point(fingerprint, unit):
                return 0
            score += self._preferred_term_score(fingerprint, ("cosphi", "cos_phi", "power_factor", "power factor"))
        elif category == "temperature":
            if summary_metric == "temperature_c":
                score += 1_000
            elif not self._is_temperature_point(fingerprint, unit):
                return 0
            score += self._preferred_term_score(fingerprint, ("temperature_c", "heat", "temperatura", "inner"))
        elif category == "total_energy":
            if summary_metric == "total_energy_kwh":
                score += 1_000
            elif not self._is_total_energy_point(fingerprint, unit):
                return 0
            score += self._preferred_term_score(fingerprint, ("total_energy", "total energy", "energia totale", "lifetime"))
        else:
            return 0

        return score

    def _preferred_term_score(self, fingerprint: str, terms: tuple[str, ...]) -> int:
        for index, term in enumerate(terms):
            if term in fingerprint:
                return 100 - index
        return 0

    def _point_fingerprint(self, point: InverterPoint) -> str:
        section = str(point.protocol_meta.get("section", ""))
        return f"{point.key} {point.label} {section}".lower()

    def _normalized_unit(self, unit: str) -> str:
        return unit.strip().lower().replace(" ", "")

    def _has_any_term(self, source: str, terms: set[str]) -> bool:
        return any(term in source for term in terms)

    def _unit_in_group(self, unit: str, group: str) -> bool:
        return unit in ESSENTIAL_UNIT_GROUPS[group]

    def _is_dc_power_point(self, fingerprint: str, unit: str) -> bool:
        return (
            self._unit_in_group(unit, "power")
            and self._has_any_term(fingerprint, {"dc", "pv", "fv", "input", "ingresso"})
            and self._has_any_term(fingerprint, {"power", "potenza"})
            and not self._has_any_term(fingerprint, {"reactive", "reattiva", "apparent", "apparente"})
        )

    def _is_dc_voltage_point(self, fingerprint: str, unit: str) -> bool:
        return (
            self._unit_in_group(unit, "voltage")
            and self._has_any_term(fingerprint, {"dc", "pv", "fv", "input", "ingresso"})
            and self._has_any_term(fingerprint, {"voltage", "tensione"})
            and not self._has_any_term(fingerprint, {"frequency", "frequenza", "current", "corrente"})
        )

    def _is_dc_current_point(self, fingerprint: str, unit: str) -> bool:
        return (
            self._unit_in_group(unit, "current")
            and self._has_any_term(fingerprint, {"dc", "pv", "fv", "input", "ingresso"})
            and self._has_any_term(fingerprint, {"current", "corrente"})
            and not self._has_any_term(fingerprint, {"frequency", "frequenza", "voltage", "tensione"})
        )

    def _is_ac_voltage_point(self, fingerprint: str, unit: str) -> bool:
        return (
            self._unit_in_group(unit, "voltage")
            and self._has_any_term(fingerprint, {"ac", "grid", "mains", "rete", "phase", "fase"})
            and self._has_any_term(fingerprint, {"voltage", "tensione"})
            and not self._has_any_term(fingerprint, {"frequency", "frequenza", "current", "corrente"})
        )

    def _is_ac_current_point(self, fingerprint: str, unit: str) -> bool:
        return (
            self._unit_in_group(unit, "current")
            and self._has_any_term(fingerprint, {"ac", "grid", "mains", "rete", "phase", "fase"})
            and self._has_any_term(fingerprint, {"current", "corrente"})
            and not self._has_any_term(fingerprint, {"frequency", "frequenza", "voltage", "tensione"})
        )

    def _is_ac_frequency_point(self, fingerprint: str, unit: str) -> bool:
        return (
            self._unit_in_group(unit, "frequency")
            and self._has_any_term(fingerprint, {"frequency", "frequenza"})
        )

    def _is_active_power_point(self, fingerprint: str, unit: str) -> bool:
        return (
            self._unit_in_group(unit, "power")
            and self._has_any_term(fingerprint, {"active power", "potenza attiva", "active_power"})
            and not self._has_any_term(fingerprint, {"reactive", "reattiva", "apparent", "apparente"})
        )

    def _is_power_factor_point(self, fingerprint: str, unit: str) -> bool:
        return (
            unit in ESSENTIAL_UNIT_GROUPS["power_factor"]
            and self._has_any_term(
                fingerprint,
                {"cosphi", "cos phi", "cos_phi", "power factor", "power_factor", "fattore potenza"},
            )
        )

    def _is_temperature_point(self, fingerprint: str, unit: str) -> bool:
        return (
            self._unit_in_group(unit, "temperature")
            and self._has_any_term(fingerprint, {"temperature", "temperatura", "heat sink", "heatsink"})
        )

    def _is_total_energy_point(self, fingerprint: str, unit: str) -> bool:
        return (
            self._unit_in_group(unit, "energy")
            and self._has_any_term(fingerprint, {"energy", "energia"})
            and self._has_any_term(fingerprint, {"total", "totale", "lifetime"})
            and not self._has_any_term(fingerprint, {"daily", "giornaliera", "day"})
        )

    def _select_heartbeat_points(self, points: list[InverterPoint]) -> list[InverterPoint]:
        readable_points = self._select_readable_points(points)
        if not readable_points:
            return []

        selected: list[InverterPoint] = []
        selected_keys: set[str] = set()

        def add_point(point: InverterPoint | None) -> None:
            if point is None or point.key in selected_keys:
                return
            selected.append(point)
            selected_keys.add(point.key)

        explicit_heartbeat_points = [
            point for point in readable_points if bool(point.protocol_meta.get("heartbeat", False))
        ]
        if explicit_heartbeat_points:
            for point in explicit_heartbeat_points[:3]:
                add_point(point)
            return self._with_scale_factor_dependencies(selected, readable_points)

        for summary_metric in ("status", "power_kw"):
            add_point(
                next(
                    (
                        point
                        for point in readable_points
                        if point.protocol_meta.get("summary_metric") == summary_metric
                    ),
                    None,
                )
            )

        for key in (
            "status",
            "active_power_kw",
            "mains_frequency_hz",
            "dc_link_voltage_v",
            "dc_voltage_v",
            "mains_voltage_v",
            "current_a_a",
        ):
            add_point(next((point for point in readable_points if point.key == key), None))
            if len(selected) >= 3:
                break

        if not selected:
            add_point(readable_points[0])

        return self._with_scale_factor_dependencies(selected[:3], readable_points)

    def _select_heartbeat_probe_point(
        self,
        inverter_model: InverterModel,
    ) -> InverterPoint | None:
        if inverter_model.protocol not in {"modbus_rtu", "modbus_tcp", "sunspec"}:
            return None

        test_register = inverter_model.defaults.get("test_register")
        if not isinstance(test_register, int):
            return None

        raw_test_function = str(inverter_model.defaults.get("test_function", "holding")).lower()
        register_type = "input" if raw_test_function == "input" else "holding"
        try:
            test_count = int(inverter_model.defaults.get("test_count", 1))
        except (TypeError, ValueError):
            test_count = 1

        return InverterPoint(
            key="heartbeat_probe",
            label="Heartbeat probe",
            kind="telemetry",
            register_type=register_type,
            address=test_register,
            length=max(1, test_count),
            datatype="uint16",
            visible=False,
            protocol_meta={
                "heartbeat": True,
                "source": "catalog_test_register",
            },
        )

    def _with_scale_factor_dependencies(
        self,
        selected_points: list[InverterPoint],
        readable_points: list[InverterPoint],
    ) -> list[InverterPoint]:
        selected_keys = {point.key for point in selected_points}
        resolved_points = list(selected_points)
        for point in selected_points:
            if point.scale_factor_key is None or point.scale_factor_key in selected_keys:
                continue
            scale_factor_point = next(
                (candidate for candidate in readable_points if candidate.key == point.scale_factor_key),
                None,
            )
            if scale_factor_point is None:
                continue
            resolved_points.append(scale_factor_point)
            selected_keys.add(scale_factor_point.key)
        return resolved_points

    def _uses_bonfiglioli_parameter_driver(self, points: list[InverterPoint]) -> bool:
        return any(point.protocol_meta.get("driver") == BONFIGLIOLI_DRIVER for point in points)

    def _uses_kaco_sunspec_driver(self, points: list[InverterPoint]) -> bool:
        return any(point.protocol_meta.get("driver") == KACO_SUNSPEC_DRIVER for point in points)

    def _uses_ingeteam_command_driver(self, points: list[InverterPoint]) -> bool:
        return any(
            point.protocol_meta.get("driver") == INGETEAM_UNIT_COMMAND_DRIVER
            for point in points
        )

    def _uses_xantrex_gt_driver(self, points: list[InverterPoint]) -> bool:
        return any(point.protocol_meta.get("driver") == XANTREX_GT_DRIVER for point in points)

    def _is_optional_point_block(self, points: list[InverterPoint]) -> bool:
        return bool(points) and all(
            bool(point.protocol_meta.get("optional_block", False))
            for point in points
        )

    def _read_modbus_point_block(
        self,
        *,
        client: object,
        register_type: str,
        unit_value: int,
        points: list[InverterPoint],
    ) -> tuple[object, str]:
        if register_type not in {"holding", "input"}:
            raise ValueError(f"Unsupported Modbus register type: {register_type}")

        start_address = min(point.address for point in points)
        end_address = max(point.address + point.length - 1 for point in points)
        count = end_address - start_address + 1
        read_method_name = (
            "read_holding_registers" if register_type == "holding" else "read_input_registers"
        )
        read_method = getattr(client, read_method_name)

        try:
            response = read_method(start_address, count=count, device_id=unit_value)
            return response, "device_id"
        except TypeError:
            try:
                response = read_method(start_address, count=count, slave=unit_value)
                return response, "slave"
            except TypeError:
                response = read_method(start_address, count=count)
                return response, "none"

    def _read_modbus_point_block_with_retry(
        self,
        *,
        client: object,
        register_type: str,
        unit_value: int,
        points: list[InverterPoint],
        settings: dict[str, object],
    ) -> tuple[object, str]:
        busy_retry_count = self._device_busy_retry_count(settings)
        attempt = 0
        while True:
            response, unit_argument_style = self._read_modbus_point_block(
                client=client,
                register_type=register_type,
                unit_value=unit_value,
                points=points,
            )
            if not (
                self._retry_on_device_busy(settings)
                and self._is_device_busy_response(response)
                and attempt < busy_retry_count
            ):
                return response, unit_argument_style

            attempt += 1
            self._wait_for_device_busy_retry(settings)

    def _write_modbus_point(
        self,
        *,
        client: object,
        register_type: str,
        unit_value: int,
        address: int,
        values: list[int],
        force_multiple: bool = False,
        no_response_expected: bool = False,
    ) -> tuple[object, str]:
        if register_type != "holding":
            raise ValueError(f"Unsupported Modbus writable register type: {register_type}")

        if len(values) == 1 and not force_multiple:
            write_method_name = "write_register"
            write_args = (address, values[0])
        else:
            write_method_name = "write_registers"
            write_args = (address, values)

        write_method = getattr(client, write_method_name)
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

    def _write_modbus_point_with_retry(
        self,
        *,
        client: object,
        register_type: str,
        unit_value: int,
        address: int,
        values: list[int],
        settings: dict[str, object],
        force_multiple: bool = False,
    ) -> tuple[object, str]:
        busy_retry_count = self._device_busy_retry_count(settings)
        attempt = 0
        while True:
            response, unit_argument_style = self._write_modbus_point(
                client=client,
                register_type=register_type,
                unit_value=unit_value,
                address=address,
                values=values,
                force_multiple=force_multiple,
            )
            if not (
                self._retry_on_device_busy(settings)
                and self._is_device_busy_response(response)
                and attempt < busy_retry_count
            ):
                return response, unit_argument_style

            attempt += 1
            self._wait_for_device_busy_retry(settings)

    def _decode_register_value(
        self,
        *,
        registers: list[int],
        start_address: int,
        point: InverterPoint,
    ) -> str | int | float | None:
        index = point.address - start_address
        raw_slice = registers[index : index + point.length]
        if not raw_slice:
            return 0

        if point.datatype == "int16":
            value = raw_slice[0]
            return value - 0x10000 if value >= 0x8000 else value
        if point.datatype == "uint16":
            return raw_slice[0]
        if point.datatype == "uint8_low":
            return raw_slice[0] & 0x00FF
        if point.datatype == "uint8_high":
            return (raw_slice[0] >> 8) & 0x00FF
        if point.datatype == "int32":
            value = (raw_slice[0] << 16) | (raw_slice[1] if len(raw_slice) > 1 else 0)
            return value - 0x100000000 if value >= 0x80000000 else value
        if point.datatype == "uint32":
            return (raw_slice[0] << 16) | (raw_slice[1] if len(raw_slice) > 1 else 0)
        if point.datatype == "int64":
            value = 0
            for register in raw_slice[:4]:
                value = (value << 16) | register
            return value - 0x10000000000000000 if value >= 0x8000000000000000 else value
        if point.datatype == "uint64":
            value = 0
            for register in raw_slice[:4]:
                value = (value << 16) | register
            return value
        if point.datatype == "int32_swapped":
            value = ((raw_slice[1] if len(raw_slice) > 1 else 0) << 16) | raw_slice[0]
            return value - 0x100000000 if value >= 0x80000000 else value
        if point.datatype == "uint32_swapped":
            return ((raw_slice[1] if len(raw_slice) > 1 else 0) << 16) | raw_slice[0]
        if point.datatype == "float32":
            payload = pack(">HH", raw_slice[0], raw_slice[1] if len(raw_slice) > 1 else 0)
            decoded = float(unpack(">f", payload)[0])
            return None if decoded != decoded else decoded
        if point.datatype == "sf32":
            payload = pack(">HH", raw_slice[1] if len(raw_slice) > 1 else 0, raw_slice[0])
            decoded = float(unpack(">f", payload)[0])
            return None if decoded != decoded else decoded
        if point.datatype == "energy_kilo_remainder_pair":
            whole_units = ((raw_slice[1] if len(raw_slice) > 1 else 0) << 16) | raw_slice[0]
            remainder_units = ((raw_slice[3] if len(raw_slice) > 3 else 0) << 16) | (
                raw_slice[2] if len(raw_slice) > 2 else 0
            )
            return float(whole_units) + (float(remainder_units) / 1000.0)
        if point.datatype == "siel_energy_kwh_pair":
            tenths_of_kwh = raw_slice[0]
            whole_mwh = raw_slice[1] if len(raw_slice) > 1 else 0
            return float(whole_mwh) * 1000.0 + (float(tenths_of_kwh) / 10.0)
        if point.datatype == "ascii_string":
            raw_bytes = bytearray()
            for register in raw_slice:
                high_byte = (register >> 8) & 0xFF
                low_byte = register & 0xFF
                if high_byte != 0:
                    raw_bytes.append(high_byte)
                if low_byte != 0:
                    raw_bytes.append(low_byte)
            return bytes(raw_bytes).decode("ascii", errors="ignore").strip()
        return raw_slice[0]

    def _apply_point_scaling(
        self,
        points: list[InverterPoint],
        raw_values: dict[str, str | int | float | bool | None],
    ) -> dict[str, str | float | int | bool | None]:
        scaled_values: dict[str, str | float | int | bool | None] = {}
        for point in points:
            raw_value = raw_values.get(point.key)
            if raw_value is None:
                continue

            if not isinstance(raw_value, (int, float)):
                scaled_values[point.key] = raw_value
                continue

            value: float | int
            if point.scale_factor_key:
                scale_factor = raw_values.get(point.scale_factor_key)
                if isinstance(scale_factor, (int, float)):
                    value = float(raw_value) * (10 ** float(scale_factor))
                else:
                    value = float(raw_value)
            else:
                value = float(raw_value)

            if point.scale != 1.0:
                value = float(value) * point.scale

            scaled_values[point.key] = value
        return scaled_values

    def _encode_command_value(self, value: float, point: InverterPoint) -> list[int] | None:
        scaled_value = value / point.scale if point.scale not in {0.0, 1.0} else value
        integer_value = int(round(scaled_value))

        if point.datatype in {"uint16", "int16"}:
            return [integer_value & 0xFFFF]
        if point.datatype in {"uint32", "int32"}:
            normalized_value = integer_value & 0xFFFFFFFF
            return [
                (normalized_value >> 16) & 0xFFFF,
                normalized_value & 0xFFFF,
            ]
        if point.datatype in {"uint64", "int64"}:
            normalized_value = integer_value & 0xFFFFFFFFFFFFFFFF
            return [
                (normalized_value >> 48) & 0xFFFF,
                (normalized_value >> 32) & 0xFFFF,
                (normalized_value >> 16) & 0xFFFF,
                normalized_value & 0xFFFF,
            ]
        if point.datatype in {"uint32_swapped", "int32_swapped"}:
            normalized_value = integer_value & 0xFFFFFFFF
            return [
                normalized_value & 0xFFFF,
                (normalized_value >> 16) & 0xFFFF,
            ]
        if point.datatype == "float32":
            payload = pack(">f", float(scaled_value))
            return list(unpack(">HH", payload))
        if point.datatype == "sf32":
            payload = pack(">f", float(scaled_value))
            high_word, low_word = unpack(">HH", payload)
            return [low_word, high_word]
        return None

    def _parse_max_registers_per_request(self, value: object | None) -> int | None:
        if value in {None, ""}:
            return None

        parsed_value = int(value)
        return parsed_value if parsed_value > 0 else None

    def _wait_between_requests(self, settings: dict[str, object]) -> None:
        delay_ms = settings.get("inter_request_delay_ms")
        if delay_ms not in {None, ""}:
            delay_seconds = float(delay_ms) / 1000.0
            if delay_seconds > 0:
                sleep(delay_seconds)
                return

        delay_seconds_value = settings.get("inter_request_delay_seconds")
        if delay_seconds_value in {None, ""}:
            return

        delay_seconds = float(delay_seconds_value)
        if delay_seconds > 0:
            sleep(delay_seconds)

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
        delay_ms = settings.get("device_busy_retry_delay_ms", 0)
        if delay_ms in {None, ""}:
            return
        delay_seconds = float(delay_ms) / 1000.0
        if delay_seconds > 0:
            sleep(delay_seconds)

    def _is_device_busy_response(self, response: object) -> bool:
        return getattr(response, "exception_code", None) == 6


inverter_io_service = InverterIoService()
