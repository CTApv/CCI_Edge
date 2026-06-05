from app.logger import get_logger
from app.schemas.command_schemas import ActivePowerLimitRequest, CommandResponse
from app.services.active_power_limit_resolver import active_power_limit_resolver
from app.services.device_command_state_service import device_command_state_service
from app.services.device_service import device_service
from app.services.inverter_io_service import inverter_io_service
from app.services.inverter_profile_resolver import inverter_profile_resolver

ACTIVE_POWER_LIMIT_COMMAND = "active_power_limit"
logger = get_logger("pv_edge_manager.commands")


class CommandService:
    def record_active_power_limit_broadcast_success(
        self,
        device_id: str,
        value: float,
    ) -> None:
        device_command_state_service.record_successful_command(
            device_id=device_id,
            command_key=ACTIVE_POWER_LIMIT_COMMAND,
            value=value,
            display_value=self._format_command_display(value, "%"),
        )

    def send_numeric_command(
        self,
        device_id: str,
        *,
        command_key: str,
        value: float,
    ) -> CommandResponse | None:
        device = device_service.get_device(device_id)
        if device is None:
            return None

        inverter_model = inverter_profile_resolver.resolve_for_device(device)
        if inverter_model is None:
            return self._build_response(
                success=False,
                message="Catalog model not found for device.",
                device_id=device_id,
                command_key=command_key,
                diagnostics={"stub_mode": True},
            )

        command_point = inverter_profile_resolver.get_command_point(inverter_model, command_key)
        if command_point is None:
            return self._build_response(
                success=False,
                message=f"Command {command_key} is not available for this model.",
                device_id=device_id,
                command_key=command_key,
                diagnostics={"stub_mode": False, "stage": "profile"},
            )

        try:
            write_result = inverter_io_service.write_command(device, command_point, value)
        except ConnectionError as exc:
            return self._build_response(
                success=False,
                message=self._build_command_message(device.protocol, False),
                device_id=device_id,
                command_key=command_key,
                diagnostics={
                    "stub_mode": False,
                    "stage": "connect",
                    "protocol": device.protocol,
                    "command_key": command_key,
                    "error": str(exc),
                },
            )
        except (ValueError, NotImplementedError) as exc:
            return self._build_response(
                success=False,
                message=self._build_command_message(device.protocol, False),
                device_id=device_id,
                command_key=command_key,
                diagnostics={
                    "stub_mode": False,
                    "stage": self._classify_error_stage(str(exc)),
                    "protocol": device.protocol,
                    "command_key": command_key,
                    "error": str(exc),
                },
            )
        except Exception as exc:
            logger.warning("Command exception for device %s command %s: %s", device_id, command_key, exc)
            return self._build_response(
                success=False,
                message=self._build_command_message(device.protocol, False),
                device_id=device_id,
                command_key=command_key,
                diagnostics={
                    "stub_mode": False,
                    "stage": "exception",
                    "protocol": device.protocol,
                    "command_key": command_key,
                    "error": str(exc),
                },
            )
        if write_result.success:
            device_command_state_service.record_successful_command(
                device_id=device_id,
                command_key=command_key,
                value=value,
                display_value=self._format_command_display(value, command_point.unit),
            )

        return self._build_response(
            success=write_result.success,
            message=self._build_command_message(device.protocol, write_result.success),
            device_id=device_id,
            command_key=command_key,
            diagnostics={
                **write_result.diagnostics,
                "protocol": device.protocol,
                "command_key": command_key,
            }
            | ({"error": write_result.error} if write_result.error else {}),
        )

    def send_active_power_limit(
        self,
        device_id: str,
        payload: ActivePowerLimitRequest,
    ) -> CommandResponse | None:
        return self.send_active_power_limit_value(device_id, payload.value)

    def send_active_power_limit_value(
        self,
        device_id: str,
        value: float,
    ) -> CommandResponse | None:
        device = device_service.get_device(device_id)
        if device is None:
            return None

        inverter_model = inverter_profile_resolver.resolve_for_device(device)
        if inverter_model is None:
            return self._build_response(
                success=False,
                message="Catalog model not found for device.",
                device_id=device_id,
                command_key=ACTIVE_POWER_LIMIT_COMMAND,
                diagnostics={"stub_mode": True},
            )

        resolution = active_power_limit_resolver.resolve_for_write(inverter_model, value)
        if resolution is None:
            return self._build_response(
                success=False,
                message="Active power setpoint is not available for this model.",
                device_id=device_id,
                command_key=ACTIVE_POWER_LIMIT_COMMAND,
                diagnostics={"stub_mode": False, "stage": "profile"},
            )

        try:
            write_result = inverter_io_service.write_command(
                device,
                resolution.command_point,
                resolution.requested_value,
            )
        except ConnectionError as exc:
            return self._build_response(
                success=False,
                message=self._build_command_message(device.protocol, False),
                device_id=device_id,
                command_key=resolution.command_point.key,
                diagnostics={
                    "stub_mode": False,
                    "stage": "connect",
                    "protocol": device.protocol,
                    "command_key": resolution.command_point.key,
                    "requested_command": ACTIVE_POWER_LIMIT_COMMAND,
                    "requested_percent": value,
                    "error": str(exc),
                },
            )
        except (ValueError, NotImplementedError) as exc:
            return self._build_response(
                success=False,
                message=self._build_command_message(device.protocol, False),
                device_id=device_id,
                command_key=resolution.command_point.key,
                diagnostics={
                    "stub_mode": False,
                    "stage": self._classify_error_stage(str(exc)),
                    "protocol": device.protocol,
                    "command_key": resolution.command_point.key,
                    "requested_command": ACTIVE_POWER_LIMIT_COMMAND,
                    "requested_percent": value,
                    "error": str(exc),
                },
            )
        except Exception as exc:
            logger.warning("Active power command exception for device %s: %s", device_id, exc)
            return self._build_response(
                success=False,
                message=self._build_command_message(device.protocol, False),
                device_id=device_id,
                command_key=resolution.command_point.key,
                diagnostics={
                    "stub_mode": False,
                    "stage": "exception",
                    "protocol": device.protocol,
                    "command_key": resolution.command_point.key,
                    "requested_command": ACTIVE_POWER_LIMIT_COMMAND,
                    "requested_percent": value,
                    "error": str(exc),
                },
            )

        if write_result.success:
            device_command_state_service.record_successful_command(
                device_id=device_id,
                command_key=ACTIVE_POWER_LIMIT_COMMAND,
                value=value,
                display_value=self._format_command_display(value, "%"),
            )

        return self._build_response(
            success=write_result.success,
            message=self._build_command_message(device.protocol, write_result.success),
            device_id=device_id,
            command_key=resolution.command_point.key,
            diagnostics={
                **write_result.diagnostics,
                "protocol": device.protocol,
                "command_key": resolution.command_point.key,
                "requested_command": ACTIVE_POWER_LIMIT_COMMAND,
                "requested_percent": value,
                "resolved_value": resolution.requested_value,
                "resolved_unit": resolution.command_point.unit,
                "conversion_mode": resolution.conversion_mode,
            }
            | ({"error": write_result.error} if write_result.error else {}),
        )

    def _build_response(
        self,
        success: bool,
        message: str,
        device_id: str,
        command_key: str,
        diagnostics: dict[str, str | int | float | bool],
    ) -> CommandResponse:
        return CommandResponse(
            success=success,
            message=message,
            device_id=device_id,
            command=command_key,
            diagnostics=diagnostics,
        )

    def _build_command_message(self, protocol: str, success: bool) -> str:
        if protocol in {"modbus_tcp", "sunspec"}:
            return "Modbus TCP command sent." if success else "Modbus TCP command failed."
        if protocol == "modbus_rtu":
            return "Modbus RTU command sent." if success else "Modbus RTU command failed."
        if protocol == "aurora":
            return "Aurora command sent." if success else "Aurora command failed."
        if protocol == "delta_rs485":
            return "Delta RS485 command sent." if success else "Delta RS485 command failed."
        return "Command sent." if success else "Command failed."

    def _classify_error_stage(self, error: str) -> str:
        lowered_error = error.lower()
        if "missing" in lowered_error:
            return "configuration"
        if "not implemented" in lowered_error or "not supported" in lowered_error:
            return "driver"
        return "write"

    def _format_command_display(self, value: float, unit: str) -> str:
        if float(value).is_integer():
            formatted_value = str(int(value))
        else:
            formatted_value = f"{value:.2f}".rstrip("0").rstrip(".")
        return f"{formatted_value} {unit}".strip()


command_service = CommandService()
