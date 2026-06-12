from typing import Literal, get_args

from pydantic import BaseModel, Field

from app.schemas.device_schemas import ProtocolValue, TransportValue

DeviceStatusValue = Literal["pending", "degraded", "offline", "online", "warning", "fault"]

PROTOCOL_OPTIONS = get_args(ProtocolValue)
TRANSPORT_OPTIONS = get_args(TransportValue)
DEVICE_STATUS_OPTIONS = get_args(DeviceStatusValue)


class SystemOptionsResponse(BaseModel):
    protocols: list[ProtocolValue]
    transports: list[TransportValue]
    device_statuses: list[DeviceStatusValue]


class NetworkInterfaceInfo(BaseModel):
    name: str
    address: str


class NetworkInterfacesResponse(BaseModel):
    interfaces: list[NetworkInterfaceInfo]


class NetworkConfigAddress(BaseModel):
    address: str
    prefix_length: int


class NetworkConfigApplyAddress(BaseModel):
    address: str
    prefix_length: int = Field(ge=1, le=32)


class NetworkConfigInterface(BaseModel):
    interface_name: str
    device_type: str
    state: str
    connection_name: str | None
    mac_address: str | None
    live_addresses: list[NetworkConfigAddress]
    live_gateway: str | None
    live_dns_servers: list[str]
    ipv4_method: Literal["auto", "manual", "unknown"]
    configured_addresses: list[NetworkConfigAddress]
    gateway: str | None
    dns_servers: list[str]
    autoconnect: bool | None
    use_default_route: bool
    editable: bool


class PendingNetworkChange(BaseModel):
    interface_name: str
    connection_name: str | None
    expires_at: str
    remaining_seconds: int


class NetworkConfigSnapshotResponse(BaseModel):
    supported: bool
    apply_supported: bool
    platform: str
    manager: str
    message: str | None
    confirmation_timeout_seconds: int
    pending_change: PendingNetworkChange | None
    interfaces: list[NetworkConfigInterface]


class NetworkConfigApplyRequest(BaseModel):
    interface_name: str
    ipv4_method: Literal["auto", "manual"]
    address: str | None = None
    prefix_length: int | None = Field(default=None, ge=1, le=32)
    addresses: list[NetworkConfigApplyAddress] = Field(default_factory=list)
    gateway: str | None = None
    dns_servers: list[str] = Field(default_factory=list)
    autoconnect: bool = True
    use_default_route: bool = True


class SystemHealthStatusCounts(BaseModel):
    total: int
    online: int
    pending: int
    offline: int
    warning: int
    fault: int


class SystemHealthPollingSnapshot(BaseModel):
    enabled: bool = False
    running: bool
    thread_start_count: int = 0
    last_thread_started_at: str | None = None
    last_loop_error: str | None = None
    last_loop_error_at: str | None = None
    consecutive_loop_error_count: int = 0
    scheduled_device_count: int
    pollable_device_count: int
    last_cycle_started_at: str | None
    last_cycle_completed_at: str | None
    last_cycle_duration_ms: int | None
    last_due_device_count: int
    last_polled_device_count: int
    last_success_count: int
    last_error_count: int
    last_endpoint_group_count: int
    last_skipped_device_count: int
    next_full_poll_due_in_seconds_min: float | None = None
    next_full_poll_due_in_seconds_max: float | None = None


class SystemHealthLiveCacheSnapshot(BaseModel):
    entry_count: int
    power_history_device_count: int
    power_history_sample_count: int
    connection_lifecycle_count: int


class SystemHealthHistoryStorageSnapshot(BaseModel):
    database_path: str
    current_bytes: int
    max_bytes: int
    usage_percent: float
    row_count: int


class SystemHealthModbusTcpSlaveSnapshot(BaseModel):
    enabled: bool
    running: bool
    host: str
    port: int
    unit_id: int
    startup_error: str | None


class SystemHealthEndpointHotspot(BaseModel):
    endpoint_type: Literal["tcp", "serial"]
    endpoint_label: str
    device_count: int
    online_count: int
    pending_count: int
    offline_count: int
    note: str
    devices: list[str]


class SystemHealthEndpointRuntime(BaseModel):
    endpoint_type: Literal["tcp", "serial"]
    endpoint_label: str
    device_count: int
    online_count: int
    pending_count: int
    offline_count: int
    shared: bool
    state: Literal["idle", "healthy", "degraded", "cooldown"]
    consecutive_connect_failures: int
    remaining_backoff_seconds: float
    cooldown_until: str | None
    last_attempt_at: str | None
    last_success_at: str | None
    last_error_at: str | None
    last_error_stage: str | None
    last_error: str | None
    last_poll_status: str | None
    last_outcome: str
    skipped_polls: int
    queued_full_due_count: int = 0
    queued_heartbeat_due_count: int = 0
    planned_full_count: int = 0
    planned_heartbeat_count: int = 0
    executed_full_count: int = 0
    executed_heartbeat_count: int = 0
    priority_deferral_count: int = 0
    last_priority_at: str | None = None
    last_cycle_started_at: str | None = None
    last_cycle_completed_at: str | None = None
    last_cycle_duration_ms: int | None = None
    last_lock_wait_ms: float | None = None
    average_lock_wait_ms: float | None = None
    last_operation_duration_ms: float | None = None
    average_cycle_duration_ms: float | None = None
    average_operation_duration_ms: float | None = None
    last_round_trip_duration_ms: float | None = None
    average_round_trip_duration_ms: float | None = None
    tcp_sample_count: int = 0
    current_lock_owner_thread_name: str | None = None
    current_lock_held_ms: float | None = None
    modbus_framer: str | None = None
    priority_pending: bool = False
    priority_remaining_ms: float | None = None
    last_command_age_ms: float | None = None
    polling_profile: str = "standard"
    adaptive_mode: str = "standard"
    expected_active_power_cycle_seconds: float | None = None
    active_power_slo_target_seconds: float = 30.0
    active_power_slo_state: Literal["pass", "warning", "fail", "unknown"] = "unknown"
    estimated_full_telemetry_cycle_seconds: float | None = None
    full_telemetry_slo_target_seconds: float = 300.0
    full_telemetry_slo_state: Literal["pass", "warning", "fail", "unknown"] = "unknown"
    recommendations: list[str] = Field(default_factory=list)
    devices: list[str]


class SystemHealthIdentitySnapshot(BaseModel):
    edge_id: str
    edge_id_source: str
    hostname: str
    platform: str
    app_version: str
    build_label: str
    build_commit: str | None
    build_time: str | None
    backend_started_at: str
    backend_path: str


class SystemHealthBroadcastDevice(BaseModel):
    device_id: str
    name: str
    brand: str
    model: str
    protocol: str
    transport: str
    status: str
    unit_id: int | None


class SystemHealthBroadcastGroup(BaseModel):
    endpoint_type: Literal["serial", "rtu_over_tcp", "modbus_tcp_gateway", "unsupported"]
    endpoint_label: str
    broadcast_mode: Literal["rtu_serial", "rtu_over_tcp", "modbus_tcp", "none"]
    state: Literal["ready", "warning", "blocked", "not_applicable"]
    summary: str
    detail: str
    device_count: int
    online_count: int
    model_count: int
    command_profile_count: int
    duplicate_unit_ids: list[int]
    issues: list[str]
    devices: list[SystemHealthBroadcastDevice]


class SystemHealthDataQualityIssueDevice(BaseModel):
    device_id: str
    name: str
    invalid_count: int
    warning_count: int
    unavailable_count: int
    examples: list[str]


class SystemHealthDataQualitySnapshot(BaseModel):
    total_points: int
    valid_points: int
    warning_points: int
    invalid_points: int
    unavailable_points: int
    devices_with_issues: int
    issue_devices: list[SystemHealthDataQualityIssueDevice]


class SystemHealthServiceLevelsSnapshot(BaseModel):
    active_power_target_seconds: float
    full_telemetry_target_seconds: float
    command_target_seconds: float
    active_power_within_target: int
    active_power_over_target: int
    active_power_unknown: int
    full_telemetry_within_target: int
    full_telemetry_over_target: int
    full_telemetry_unknown: int


class SystemHealthResponse(BaseModel):
    generated_at: str
    identity: SystemHealthIdentitySnapshot
    status_counts: SystemHealthStatusCounts
    polling: SystemHealthPollingSnapshot
    live_cache: SystemHealthLiveCacheSnapshot
    history_storage: SystemHealthHistoryStorageSnapshot
    modbus_tcp_slave: SystemHealthModbusTcpSlaveSnapshot
    broadcast_groups: list[SystemHealthBroadcastGroup]
    endpoint_hotspots: list[SystemHealthEndpointHotspot]
    endpoint_runtimes: list[SystemHealthEndpointRuntime]
    data_quality: SystemHealthDataQualitySnapshot
    service_levels: SystemHealthServiceLevelsSnapshot
