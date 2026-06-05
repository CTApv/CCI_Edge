from app.schemas.device_overview_schemas import (
    DeviceCommandPoint,
    DeviceOverviewDiagnostics,
    DeviceOverviewMetrics,
    DeviceOverviewResponse,
)
from app.services.active_power_limit_resolver import active_power_limit_resolver
from app.schemas.device_schemas import DeviceResponse
from app.services.device_runtime import (
    build_poll_endpoint_key,
    get_last_contact_age_seconds,
    get_last_full_data_age_seconds,
    resolve_communication_state,
    resolve_data_freshness,
)
from app.services.device_command_state_service import DeviceCommandState, device_command_state_service
from app.services.device_service import device_service
from app.services.inverter_profile_resolver import inverter_profile_resolver
from app.services.live_cache import LiveCacheEntry, live_cache
from app.services.polling_engine import poll_device_with_runtime


class DeviceOverviewService:
    def get_overview(
        self,
        device_id: str,
        *,
        allow_live_poll_on_cache_miss: bool = True,
    ) -> DeviceOverviewResponse | None:
        device = device_service.get_device(device_id)
        if device is None:
            return None

        cached_entry = live_cache.get(device.device_id)
        inverter_model = inverter_profile_resolver.resolve_for_device(device)
        command_states = device_command_state_service.list_command_states(device.device_id)
        commands = self._build_command_points(inverter_model, command_states)
        if cached_entry is not None:
            return self._build_cached_overview(device, cached_entry, commands)

        if (
            allow_live_poll_on_cache_miss
            and device.protocol in {"modbus_tcp", "modbus_rtu", "sunspec", "aurora", "delta_rs485"}
        ):
            polled_entry = poll_device_with_runtime(device)
            if polled_entry is not None:
                live_cache.set(device.device_id, polled_entry)
                refreshed_device = device_service.get_device(device.device_id) or device
                return self._build_cached_overview(refreshed_device, polled_entry, commands)

        return self._build_stub_overview(device, commands=commands)

    def _build_cached_overview(
        self,
        device: DeviceResponse,
        cache_entry: LiveCacheEntry,
        commands: list[DeviceCommandPoint],
    ) -> DeviceOverviewResponse:
        endpoint_device_count = self._count_devices_for_endpoint(device)
        lifecycle = live_cache.get_connection_lifecycle(device.device_id)
        diagnostics = cache_entry.diagnostics.model_copy(
            deep=True,
            update={
                "communication_state": resolve_communication_state(
                    device,
                    lifecycle,
                    endpoint_device_count=endpoint_device_count,
                ),
                "data_freshness": resolve_data_freshness(
                    device,
                    lifecycle,
                    endpoint_device_count=endpoint_device_count,
                ),
                "communication_age_seconds": get_last_contact_age_seconds(lifecycle),
                "data_age_seconds": get_last_full_data_age_seconds(lifecycle),
            },
        )
        return DeviceOverviewResponse(
            device=device,
            metrics=cache_entry.metrics.model_copy(deep=True),
            diagnostics=diagnostics,
            telemetry=[item.model_copy(deep=True) for item in cache_entry.telemetry],
            commands=[item.model_copy(deep=True) for item in commands],
        )

    def _build_stub_overview(
        self,
        device: DeviceResponse,
        response_time_ms: int = 0,
        last_poll_status: str = "stub_mode=true; stage=idle",
        last_error: str | None = None,
        commands: list[DeviceCommandPoint] | None = None,
    ) -> DeviceOverviewResponse:
        return DeviceOverviewResponse(
            device=device,
            metrics=DeviceOverviewMetrics(
                power_kw=0.0,
                daily_energy_kwh=0.0,
                total_energy_kwh=0.0,
                temperature_c=25.0,
            ),
            diagnostics=DeviceOverviewDiagnostics(
                last_poll_status=last_poll_status,
                response_time_ms=response_time_ms,
                retries=0,
                last_error=last_error,
                poll_kind="fallback",
                communication_state="pending",
                data_freshness="missing",
            ),
            telemetry=[],
            commands=[item.model_copy(deep=True) for item in commands or []],
        )

    def _count_devices_for_endpoint(self, device: DeviceResponse) -> int:
        endpoint = build_poll_endpoint_key(device)
        if endpoint is None:
            return 1
        devices = device_service.list_devices()
        return max(
            1,
            sum(1 for current in devices if build_poll_endpoint_key(current) == endpoint),
        )

    def _build_command_points(
        self,
        inverter_model: object,
        command_states: dict[str, DeviceCommandState],
    ) -> list[DeviceCommandPoint]:
        if inverter_model is None:
            return []

        command_points: list[DeviceCommandPoint] = []
        active_power_alias_point, hidden_command_keys = active_power_limit_resolver.build_overview_command_alias(
            inverter_model
        )
        if active_power_alias_point is not None:
            command_points.append(
                self._build_command_point(
                    active_power_alias_point,
                    command_states.get(active_power_alias_point.key),
                )
            )

        for point in getattr(inverter_model, "command_points", []):
            if point.key in hidden_command_keys:
                continue
            command_points.append(
                self._build_command_point(point, command_states.get(point.key))
            )
        return command_points

    def _build_command_point(
        self,
        point: object,
        command_state: DeviceCommandState | None = None,
    ) -> DeviceCommandPoint:
        min_value = point.protocol_meta.get("min_value")
        max_value = point.protocol_meta.get("max_value")
        step = point.protocol_meta.get("step")
        return DeviceCommandPoint(
            key=point.key,
            label=point.label,
            unit=point.unit,
            section=str(point.protocol_meta.get("section", "Control")),
            datatype=point.datatype,
            scale=point.scale,
            min_value=float(min_value) if isinstance(min_value, (int, float)) else None,
            max_value=float(max_value) if isinstance(max_value, (int, float)) else None,
            step=float(step) if isinstance(step, (int, float)) else None,
            last_set_value=command_state.last_set_value if command_state is not None else None,
            last_set_display=command_state.last_set_display if command_state is not None else None,
            last_set_at=command_state.last_set_at if command_state is not None else None,
        )
