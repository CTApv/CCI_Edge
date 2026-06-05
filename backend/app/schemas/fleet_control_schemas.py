from typing import Literal

from pydantic import BaseModel, ConfigDict


DiagnosticValue = str | int | float | bool
FleetDispatchOutcome = Literal["ok", "error", "pending", "blocked"]
FleetControlStateValue = Literal["idle", "pending", "aligned", "error", "blocked"]
FleetEligibilityValue = Literal["eligible", "ineligible"]
FleetConfidenceStateValue = Literal["idle", "tracking", "stable", "confirmed", "warning"]
FleetReadinessStateValue = Literal["pass", "warn", "fail"]
FleetTimelineLevelValue = Literal["info", "success", "warning", "error"]


class FleetSetpointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float


class ModbusTcpSlaveConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    cci_enabled: bool
    host: str
    port: int
    unit_id: int
    cci_readback_enabled: bool
    cci_readback_range_percent: float
    cci_readback_stable_seconds: float
    cci_readback_active_power_only: bool


class HsmBridgeConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    hsm_port: str
    inverter_port: str
    hsm_baud_rate: int
    hsm_parity: Literal["N", "E", "O"]
    hsm_stop_bits: int
    hsm_byte_size: int
    frame_gap_ms: int
    forward_delay_ms: int
    ack_timeout_ms: int


class ModbusTcpSlaveStatusResponse(BaseModel):
    class CciConnectionResponse(BaseModel):
        status: Literal["online", "pending", "offline"]
        active_connections: int
        last_connected_at: str | None
        last_disconnected_at: str | None
        last_activity_at: str | None

    enabled: bool
    cci_enabled: bool
    host: str
    port: int
    unit_id: int
    cci_readback_enabled: bool
    cci_readback_range_percent: float
    cci_readback_stable_seconds: float
    cci_readback_active_power_only: bool
    running: bool
    cci_connection: CciConnectionResponse


class HsmBridgeStatusResponse(BaseModel):
    status: Literal["online", "pending", "offline"]
    enabled: bool
    running: bool
    hsm_port: str
    inverter_port: str
    hsm_baud_rate: int
    hsm_parity: Literal["N", "E", "O"]
    hsm_stop_bits: int
    hsm_byte_size: int
    frame_gap_ms: int
    forward_delay_ms: int
    ack_timeout_ms: int
    startup_error: str | None
    queue_depth: int
    frames_received_count: int
    frames_forwarded_count: int
    frames_overwritten_count: int
    ack_ok_count: int
    timeout_count: int
    last_hsm_frame_at: str | None
    last_forward_at: str | None
    last_ack_at: str | None
    last_error_at: str | None
    last_error: str | None
    line_ready: bool
    line_note: str | None
    resolved_protocol: str | None
    resolved_baud_rate: int | None
    resolved_parity: Literal["N", "E", "O"] | None
    resolved_stop_bits: int | None
    resolved_byte_size: int | None


class FleetControlSourcePolicyResponse(BaseModel):
    effective_source_priority: int
    last_rejected_source: str | None
    last_rejected_reason: str | None
    last_rejected_at: str | None


class FleetControlDeviceSummaryResponse(BaseModel):
    total_devices: int
    eligible_devices: int
    aligned_devices: int
    pending_devices: int
    error_devices: int
    blocked_devices: int
    ineligible_devices: int


class FleetDeviceControlStateResponse(BaseModel):
    device_id: str
    name: str
    brand: str
    model: str
    protocol: str
    transport: str
    device_status: str
    eligibility: FleetEligibilityValue
    eligibility_reason: str | None
    control_state: FleetControlStateValue
    desired_percent: float | None
    desired_updated_at: str | None
    desired_source: str | None
    desired_source_priority: int
    last_sent_percent: float | None
    last_applied_percent: float | None
    telemetry_confirmed: bool
    last_command: str | None
    last_resolved_value: float | None
    last_resolved_unit: str | None
    last_dispatch_outcome: FleetDispatchOutcome | None
    last_dispatch_at: str | None
    last_error: str | None
    note: str


class FleetDeviceDispatchResultResponse(BaseModel):
    device_id: str
    name: str
    brand: str
    model: str
    protocol: str
    transport: str
    outcome: FleetDispatchOutcome
    success: bool
    message: str
    command: str | None
    diagnostics: dict[str, DiagnosticValue]
    timestamp: str


class FleetControlConfidenceResponse(BaseModel):
    state: FleetConfidenceStateValue
    requested_percent: float | None
    written_percent: float | None
    confirmed_percent: float | None
    actual_power_kw: float | None
    nominal_power_kw: float | None
    utilization_percent: float | None
    eligible_devices: int
    aligned_devices: int
    pending_devices: int
    error_devices: int
    blocked_devices: int
    telemetry_confirmed_devices: int
    last_target_at: str | None
    last_write_at: str | None
    last_confirmation_at: str | None


class FleetReadinessCheckResponse(BaseModel):
    key: str
    label: str
    state: FleetReadinessStateValue
    summary: str
    detail: str


class FleetReadinessResponse(BaseModel):
    overall_state: FleetReadinessStateValue
    ready_count: int
    warning_count: int
    fail_count: int
    checks: list[FleetReadinessCheckResponse]


class FleetTimelineEventResponse(BaseModel):
    event_id: int
    timestamp: str
    category: str
    level: FleetTimelineLevelValue
    title: str
    message: str
    details: dict[str, DiagnosticValue]


class FleetControlStatusResponse(BaseModel):
    modbus_tcp_slave: ModbusTcpSlaveStatusResponse
    hsm_bridge: HsmBridgeStatusResponse
    active_power_limit_percent: float | None
    updated_at: str | None
    updated_source: str | None
    last_dispatch_at: str | None
    last_dispatch_latency_ms: int | None = None
    last_dispatch_ok_count: int
    last_dispatch_error_count: int
    last_dispatch_skipped_count: int
    eligible_device_count: int
    source_policy: FleetControlSourcePolicyResponse
    device_summary: FleetControlDeviceSummaryResponse
    device_control_states: list[FleetDeviceControlStateResponse]
    last_device_results: list[FleetDeviceDispatchResultResponse]
    control_confidence: FleetControlConfidenceResponse
    readiness: FleetReadinessResponse
    timeline_events: list[FleetTimelineEventResponse]
