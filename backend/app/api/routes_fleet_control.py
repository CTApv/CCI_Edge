from datetime import datetime
from typing import Callable

from fastapi import APIRouter, HTTPException

from app.schemas.fleet_control_schemas import (
    FleetControlConfidenceResponse,
    FleetControlDeviceSummaryResponse,
    FleetReadinessCheckResponse,
    FleetReadinessResponse,
    FleetControlSourcePolicyResponse,
    FleetControlStatusResponse,
    FleetDeviceControlStateResponse,
    FleetDeviceDispatchResultResponse,
    FleetSetpointRequest,
    FleetTimelineEventResponse,
    HsmBridgeConfigRequest,
    HsmBridgeStatusResponse,
    ModbusTcpSlaveConfigRequest,
    ModbusTcpSlaveStatusResponse,
)
from app.services.fleet_dispatch_service import fleet_dispatch_service
from app.services.fleet_runtime_insights_service import fleet_runtime_insights_service
from app.services.fleet_setpoint_service import fleet_setpoint_service
from app.services.hsm_bridge_config_service import hsm_bridge_config_service
from app.services.hsm_bridge_service import hsm_bridge_service
from app.services.modbus_tcp_slave_config_service import modbus_tcp_slave_config_service
from app.services.modbus_tcp_slave_service import modbus_tcp_slave_service
from app.services.runtime_event_service import runtime_event_service

router = APIRouter(prefix="/api/fleet-control", tags=["fleet-control"])


@router.get("/status", response_model=FleetControlStatusResponse)
def get_fleet_control_status() -> FleetControlStatusResponse:
    return _build_status_response()


@router.put("/modbus-slave-config", response_model=FleetControlStatusResponse)
def update_modbus_slave_config(
    payload: ModbusTcpSlaveConfigRequest,
) -> FleetControlStatusResponse:
    previous_config = modbus_tcp_slave_config_service.get_config()
    runtime_reload_required = (
        previous_config.enabled != payload.enabled
        or previous_config.host != (payload.host.strip() or "0.0.0.0")
        or previous_config.port != int(payload.port)
        or previous_config.unit_id != int(payload.unit_id)
    )
    updated_config = modbus_tcp_slave_config_service.update_config(
        enabled=payload.enabled,
        cci_enabled=payload.cci_enabled,
        host=payload.host,
        port=payload.port,
        unit_id=payload.unit_id,
        cci_readback_enabled=payload.cci_readback_enabled,
        cci_readback_range_percent=payload.cci_readback_range_percent,
        cci_readback_stable_seconds=payload.cci_readback_stable_seconds,
        cci_readback_active_power_only=payload.cci_readback_active_power_only,
    )
    if runtime_reload_required:
        modbus_tcp_slave_service.reload_runtime_config()
    modbus_tcp_slave_service.reset_cci_read_tracking()
    modbus_tcp_slave_service.refresh_registers()

    startup_error = modbus_tcp_slave_service.get_startup_error()
    if runtime_reload_required and updated_config.enabled and not modbus_tcp_slave_service.is_running():
        modbus_tcp_slave_config_service.update_config(
            enabled=previous_config.enabled,
            cci_enabled=previous_config.cci_enabled,
            host=previous_config.host,
            port=previous_config.port,
            unit_id=previous_config.unit_id,
            cci_readback_enabled=previous_config.cci_readback_enabled,
            cci_readback_range_percent=previous_config.cci_readback_range_percent,
            cci_readback_stable_seconds=previous_config.cci_readback_stable_seconds,
            cci_readback_active_power_only=previous_config.cci_readback_active_power_only,
        )
        modbus_tcp_slave_service.reload_runtime_config()
        modbus_tcp_slave_service.refresh_registers()
        if startup_error:
            raise HTTPException(
                status_code=409,
                detail=f"Impossibile avviare lo slave Modbus TCP con la nuova configurazione: {startup_error}",
            )
        raise HTTPException(
            status_code=500,
            detail="Lo slave Modbus TCP non e' partito con la nuova configurazione. La configurazione precedente e' stata ripristinata.",
        )

    return _build_status_response()


@router.put("/hsm-bridge-config", response_model=FleetControlStatusResponse)
def update_hsm_bridge_config(
    payload: HsmBridgeConfigRequest,
) -> FleetControlStatusResponse:
    previous_config = hsm_bridge_config_service.get_config()
    updated_config = hsm_bridge_config_service.update_config(
        enabled=payload.enabled,
        hsm_port=payload.hsm_port,
        inverter_port=payload.inverter_port,
        hsm_baud_rate=payload.hsm_baud_rate,
        hsm_parity=payload.hsm_parity,
        hsm_stop_bits=payload.hsm_stop_bits,
        hsm_byte_size=payload.hsm_byte_size,
        frame_gap_ms=payload.frame_gap_ms,
        forward_delay_ms=payload.forward_delay_ms,
        ack_timeout_ms=payload.ack_timeout_ms,
    )
    runtime_reload_required = previous_config != updated_config
    if runtime_reload_required:
        hsm_bridge_service.reload_runtime_config()
    if runtime_reload_required and updated_config.enabled and not hsm_bridge_service.is_running():
        startup_error = hsm_bridge_service.get_runtime_snapshot().startup_error
        hsm_bridge_config_service.update_config(
            enabled=previous_config.enabled,
            hsm_port=previous_config.hsm_port,
            inverter_port=previous_config.inverter_port,
            hsm_baud_rate=previous_config.hsm_baud_rate,
            hsm_parity=previous_config.hsm_parity,
            hsm_stop_bits=previous_config.hsm_stop_bits,
            hsm_byte_size=previous_config.hsm_byte_size,
            frame_gap_ms=previous_config.frame_gap_ms,
            forward_delay_ms=previous_config.forward_delay_ms,
            ack_timeout_ms=previous_config.ack_timeout_ms,
        )
        hsm_bridge_service.reload_runtime_config()
        if startup_error:
            raise HTTPException(
                status_code=409,
                detail=f"Impossibile avviare il bridge HSM con la nuova configurazione: {startup_error}",
            )
        raise HTTPException(
            status_code=500,
            detail="Il bridge HSM non e' partito con la nuova configurazione. La configurazione precedente e' stata ripristinata.",
        )
    return _build_status_response()


@router.post("/setpoint", response_model=FleetControlStatusResponse)
def set_fleet_setpoint(payload: FleetSetpointRequest) -> FleetControlStatusResponse:
    slave_config = modbus_tcp_slave_config_service.get_config()

    if slave_config.cci_enabled:
        modbus_tcp_slave_config_service.update_config(
            enabled=slave_config.enabled,
            cci_enabled=False,
            host=slave_config.host,
            port=slave_config.port,
            unit_id=slave_config.unit_id,
            cci_readback_enabled=slave_config.cci_readback_enabled,
            cci_readback_range_percent=slave_config.cci_readback_range_percent,
            cci_readback_stable_seconds=slave_config.cci_readback_stable_seconds,
            cci_readback_active_power_only=slave_config.cci_readback_active_power_only,
        )
        modbus_tcp_slave_service.reset_cci_read_tracking()

    fleet_setpoint_service.set_active_power_limit_percent(payload.value, source="api")
    modbus_tcp_slave_service.reset_cci_read_tracking()
    fleet_dispatch_service.request_dispatch(
        on_complete=_build_restore_cci_callback(restore_enabled=slave_config.cci_enabled)
    )
    modbus_tcp_slave_service.refresh_registers()
    return _build_status_response()


@router.delete("/setpoint", response_model=FleetControlStatusResponse)
def clear_fleet_setpoint() -> FleetControlStatusResponse:
    fleet_setpoint_service.clear_active_power_limit_percent(source="api")
    modbus_tcp_slave_service.reset_cci_read_tracking()
    modbus_tcp_slave_service.refresh_registers()
    return _build_status_response()


def _build_status_response() -> FleetControlStatusResponse:
    state = fleet_setpoint_service.get_state()
    config = modbus_tcp_slave_config_service.get_config()
    cci_connection = modbus_tcp_slave_service.get_cci_connection_snapshot()
    hsm_config = hsm_bridge_config_service.get_config()
    hsm_runtime = hsm_bridge_service.get_runtime_snapshot()
    raw_device_control_states = fleet_setpoint_service.list_device_control_states()
    device_control_states = [
        FleetDeviceControlStateResponse(
            device_id=item.device_id,
            name=item.name,
            brand=item.brand,
            model=item.model,
            protocol=item.protocol,
            transport=item.transport,
            device_status=item.device_status,
            eligibility=item.eligibility,
            eligibility_reason=item.eligibility_reason,
            control_state=item.control_state,
            desired_percent=item.desired_percent,
            desired_updated_at=item.desired_updated_at,
            desired_source=item.desired_source,
            desired_source_priority=item.desired_source_priority,
            last_sent_percent=item.last_sent_percent,
            last_applied_percent=item.last_applied_percent,
            telemetry_confirmed=item.telemetry_confirmed,
            last_command=item.last_command,
            last_resolved_value=item.last_resolved_value,
            last_resolved_unit=item.last_resolved_unit,
            last_dispatch_outcome=item.last_dispatch_outcome,
            last_dispatch_at=item.last_dispatch_at,
            last_error=item.last_error,
            note=item.note,
        )
        for item in raw_device_control_states
    ]
    device_results = [
        FleetDeviceDispatchResultResponse(
            device_id=result.device_id,
            name=result.name,
            brand=result.brand,
            model=result.model,
            protocol=result.protocol,
            transport=result.transport,
            outcome=result.outcome,
            success=result.success,
            message=result.message,
            command=result.command,
            diagnostics=result.diagnostics,
            timestamp=result.timestamp,
        )
        for result in fleet_setpoint_service.list_device_results()
    ]
    control_confidence = fleet_runtime_insights_service.build_control_confidence(
        state=state,
        device_control_states=raw_device_control_states,
    )
    readiness = fleet_runtime_insights_service.build_readiness(
        device_control_states=raw_device_control_states,
    )
    timeline_events = runtime_event_service.list_recent_events(limit=18)
    total_devices = len(device_control_states)
    eligible_devices = sum(1 for item in device_control_states if item.eligibility == "eligible")
    aligned_devices = sum(1 for item in device_control_states if item.control_state == "aligned")
    pending_devices = sum(1 for item in device_control_states if item.control_state == "pending")
    error_devices = sum(1 for item in device_control_states if item.control_state == "error")
    blocked_devices = sum(1 for item in device_control_states if item.control_state == "blocked")
    ineligible_devices = sum(
        1 for item in device_control_states if item.eligibility == "ineligible"
    )
    return FleetControlStatusResponse(
        modbus_tcp_slave=ModbusTcpSlaveStatusResponse(
            enabled=config.enabled,
            cci_enabled=config.cci_enabled,
            host=config.host,
            port=config.port,
            unit_id=config.unit_id,
            cci_readback_enabled=config.cci_readback_enabled,
            cci_readback_range_percent=config.cci_readback_range_percent,
            cci_readback_stable_seconds=config.cci_readback_stable_seconds,
            cci_readback_active_power_only=config.cci_readback_active_power_only,
            running=modbus_tcp_slave_service.is_running(),
            cci_connection=ModbusTcpSlaveStatusResponse.CciConnectionResponse(
                status=cci_connection.status,
                active_connections=cci_connection.active_connections,
                last_connected_at=cci_connection.last_connected_at,
                last_disconnected_at=cci_connection.last_disconnected_at,
                last_activity_at=cci_connection.last_activity_at,
            ),
        ),
        hsm_bridge=HsmBridgeStatusResponse(
            status=hsm_runtime.status,
            enabled=hsm_config.enabled,
            running=hsm_runtime.running,
            hsm_port=hsm_config.hsm_port,
            inverter_port=hsm_config.inverter_port,
            hsm_baud_rate=hsm_config.hsm_baud_rate,
            hsm_parity=hsm_config.hsm_parity,
            hsm_stop_bits=hsm_config.hsm_stop_bits,
            hsm_byte_size=hsm_config.hsm_byte_size,
            frame_gap_ms=hsm_config.frame_gap_ms,
            forward_delay_ms=hsm_config.forward_delay_ms,
            ack_timeout_ms=hsm_config.ack_timeout_ms,
            startup_error=hsm_runtime.startup_error,
            queue_depth=hsm_runtime.queue_depth,
            frames_received_count=hsm_runtime.frames_received_count,
            frames_forwarded_count=hsm_runtime.frames_forwarded_count,
            frames_overwritten_count=hsm_runtime.frames_overwritten_count,
            ack_ok_count=hsm_runtime.ack_ok_count,
            timeout_count=hsm_runtime.timeout_count,
            last_hsm_frame_at=hsm_runtime.last_hsm_frame_at,
            last_forward_at=hsm_runtime.last_forward_at,
            last_ack_at=hsm_runtime.last_ack_at,
            last_error_at=hsm_runtime.last_error_at,
            last_error=hsm_runtime.last_error,
            line_ready=hsm_runtime.line_ready,
            line_note=hsm_runtime.line_note,
            resolved_protocol=hsm_runtime.resolved_protocol,
            resolved_baud_rate=hsm_runtime.resolved_baud_rate,
            resolved_parity=hsm_runtime.resolved_parity,
            resolved_stop_bits=hsm_runtime.resolved_stop_bits,
            resolved_byte_size=hsm_runtime.resolved_byte_size,
        ),
        active_power_limit_percent=state.active_power_limit_percent,
        updated_at=state.updated_at,
        updated_source=state.updated_source,
        last_dispatch_at=state.last_dispatch_at,
        last_dispatch_latency_ms=_compute_dispatch_latency_ms(
            desired_updated_at=state.updated_at,
            dispatch_at=state.last_dispatch_at,
        ),
        last_dispatch_ok_count=state.last_dispatch_ok_count,
        last_dispatch_error_count=state.last_dispatch_error_count,
        last_dispatch_skipped_count=state.last_dispatch_skipped_count,
        eligible_device_count=state.eligible_device_count,
        source_policy=FleetControlSourcePolicyResponse(
            effective_source_priority=state.effective_source_priority,
            last_rejected_source=state.last_rejected_source,
            last_rejected_reason=state.last_rejected_reason,
            last_rejected_at=state.last_rejected_at,
        ),
        device_summary=FleetControlDeviceSummaryResponse(
            total_devices=total_devices,
            eligible_devices=eligible_devices,
            aligned_devices=aligned_devices,
            pending_devices=pending_devices,
            error_devices=error_devices,
            blocked_devices=blocked_devices,
            ineligible_devices=ineligible_devices,
        ),
        device_control_states=device_control_states,
        last_device_results=device_results,
        control_confidence=FleetControlConfidenceResponse(
            state=control_confidence.state,
            requested_percent=control_confidence.requested_percent,
            written_percent=control_confidence.written_percent,
            confirmed_percent=control_confidence.confirmed_percent,
            actual_power_kw=control_confidence.actual_power_kw,
            nominal_power_kw=control_confidence.nominal_power_kw,
            utilization_percent=control_confidence.utilization_percent,
            eligible_devices=control_confidence.eligible_devices,
            aligned_devices=control_confidence.aligned_devices,
            pending_devices=control_confidence.pending_devices,
            error_devices=control_confidence.error_devices,
            blocked_devices=control_confidence.blocked_devices,
            telemetry_confirmed_devices=control_confidence.telemetry_confirmed_devices,
            last_target_at=control_confidence.last_target_at,
            last_write_at=control_confidence.last_write_at,
            last_confirmation_at=control_confidence.last_confirmation_at,
        ),
        readiness=FleetReadinessResponse(
            overall_state=readiness.overall_state,
            ready_count=readiness.ready_count,
            warning_count=readiness.warning_count,
            fail_count=readiness.fail_count,
            checks=[
                FleetReadinessCheckResponse(
                    key=item.key,
                    label=item.label,
                    state=item.state,
                    summary=item.summary,
                    detail=item.detail,
                )
                for item in readiness.checks
            ],
        ),
        timeline_events=[
            FleetTimelineEventResponse(
                event_id=item.event_id,
                timestamp=item.timestamp,
                category=item.category,
                level=item.level,
                title=item.title,
                message=item.message,
                details=item.details,
            )
            for item in timeline_events
        ],
    )


def _build_restore_cci_callback(*, restore_enabled: bool) -> Callable[[], None]:
    def restore() -> None:
        if not restore_enabled:
            return

        current_config = modbus_tcp_slave_config_service.get_config()
        if current_config.cci_enabled:
            return

        modbus_tcp_slave_config_service.update_config(
            enabled=current_config.enabled,
            cci_enabled=True,
            host=current_config.host,
            port=current_config.port,
            unit_id=current_config.unit_id,
            cci_readback_enabled=current_config.cci_readback_enabled,
            cci_readback_range_percent=current_config.cci_readback_range_percent,
            cci_readback_stable_seconds=current_config.cci_readback_stable_seconds,
            cci_readback_active_power_only=current_config.cci_readback_active_power_only,
        )
        modbus_tcp_slave_service.reset_cci_read_tracking()
        modbus_tcp_slave_service.refresh_registers()

    return restore


def _compute_dispatch_latency_ms(
    *,
    desired_updated_at: str | None,
    dispatch_at: str | None,
) -> int | None:
    if desired_updated_at is None or dispatch_at is None:
        return None
    try:
        desired_timestamp = datetime.fromisoformat(desired_updated_at)
        dispatch_timestamp = datetime.fromisoformat(dispatch_at)
    except ValueError:
        return None
    return max(0, int(round((dispatch_timestamp - desired_timestamp).total_seconds() * 1000)))
