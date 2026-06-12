const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim() || "/api";
const API_REQUEST_TIMEOUT_MS = 15000;
const API_DISCOVERY_REQUEST_TIMEOUT_MS = 180000;

type RequestOptions = RequestInit & {
  timeoutMs?: number;
};

type ConnectionValue = string | number | boolean;
export type ConnectionSettings = Record<string, ConnectionValue>;

export type DashboardSummary = {
  total_devices: number;
  online_devices: number;
  offline_devices: number;
  active_alarms: number;
  total_power_kw: number;
  nominal_power_kw: number;
  nominal_power_device_count: number;
  power_utilization_percent: number | null;
  daily_energy_kwh: number;
  total_energy_kwh: number;
};

export type FleetDeviceDispatchResult = {
  device_id: string;
  name: string;
  brand: string;
  model: string;
  protocol: string;
  transport: string;
  outcome: "ok" | "error" | "pending" | "blocked";
  success: boolean;
  message: string;
  command: string | null;
  diagnostics: Record<string, string | number | boolean>;
  timestamp: string;
};

export type FleetDeviceControlState = {
  device_id: string;
  name: string;
  brand: string;
  model: string;
  protocol: string;
  transport: string;
  device_status: string;
  eligibility: "eligible" | "ineligible";
  eligibility_reason: string | null;
  control_state: "idle" | "pending" | "aligned" | "error" | "blocked";
  desired_percent: number | null;
  desired_updated_at: string | null;
  desired_source: string | null;
  desired_source_priority: number;
  last_sent_percent: number | null;
  last_applied_percent: number | null;
  telemetry_confirmed: boolean;
  last_command: string | null;
  last_resolved_value: number | null;
  last_resolved_unit: string | null;
  last_dispatch_outcome: "ok" | "error" | "pending" | "blocked" | null;
  last_dispatch_at: string | null;
  last_error: string | null;
  note: string;
};

export type FleetControlSourcePolicy = {
  effective_source_priority: number;
  last_rejected_source: string | null;
  last_rejected_reason: string | null;
  last_rejected_at: string | null;
};

export type FleetControlDeviceSummary = {
  total_devices: number;
  eligible_devices: number;
  aligned_devices: number;
  pending_devices: number;
  error_devices: number;
  blocked_devices: number;
  ineligible_devices: number;
};

export type FleetControlConfidence = {
  state: "idle" | "tracking" | "stable" | "confirmed" | "warning";
  requested_percent: number | null;
  written_percent: number | null;
  confirmed_percent: number | null;
  actual_power_kw: number | null;
  nominal_power_kw: number | null;
  utilization_percent: number | null;
  eligible_devices: number;
  aligned_devices: number;
  pending_devices: number;
  error_devices: number;
  blocked_devices: number;
  telemetry_confirmed_devices: number;
  last_target_at: string | null;
  last_write_at: string | null;
  last_confirmation_at: string | null;
};

export type FleetReadinessCheck = {
  key: string;
  label: string;
  state: "pass" | "warn" | "fail";
  summary: string;
  detail: string;
};

export type FleetReadiness = {
  overall_state: "pass" | "warn" | "fail";
  ready_count: number;
  warning_count: number;
  fail_count: number;
  checks: FleetReadinessCheck[];
};

export type FleetTimelineEvent = {
  event_id: number;
  timestamp: string;
  category: string;
  level: "info" | "success" | "warning" | "error";
  title: string;
  message: string;
  details: Record<string, string | number | boolean>;
};

export type FleetControlStatus = {
  modbus_tcp_slave: {
    enabled: boolean;
    cci_enabled: boolean;
    host: string;
    port: number;
    unit_id: number;
    cci_readback_enabled: boolean;
    cci_readback_range_percent: number;
    cci_readback_stable_seconds: number;
    cci_readback_active_power_only: boolean;
    running: boolean;
    cci_connection: {
      status: "online" | "pending" | "offline";
      active_connections: number;
      last_connected_at: string | null;
      last_disconnected_at: string | null;
      last_activity_at: string | null;
    };
  };
  hsm_bridge: {
    status: "online" | "pending" | "offline";
    enabled: boolean;
    running: boolean;
    hsm_port: string;
    inverter_port: string;
    hsm_baud_rate: number;
    hsm_parity: "N" | "E" | "O";
    hsm_stop_bits: number;
    hsm_byte_size: number;
    frame_gap_ms: number;
    forward_delay_ms: number;
    ack_timeout_ms: number;
    startup_error: string | null;
    queue_depth: number;
    frames_received_count: number;
    frames_forwarded_count: number;
    frames_overwritten_count: number;
    ack_ok_count: number;
    timeout_count: number;
    last_hsm_frame_at: string | null;
    last_forward_at: string | null;
    last_ack_at: string | null;
    last_error_at: string | null;
    last_error: string | null;
    line_ready: boolean;
    line_note: string | null;
    resolved_protocol: string | null;
    resolved_baud_rate: number | null;
    resolved_parity: "N" | "E" | "O" | null;
    resolved_stop_bits: number | null;
    resolved_byte_size: number | null;
  };
  active_power_limit_percent: number | null;
  updated_at: string | null;
  updated_source: string | null;
  last_dispatch_at: string | null;
  last_dispatch_latency_ms: number | null;
  last_dispatch_ok_count: number;
  last_dispatch_error_count: number;
  last_dispatch_skipped_count: number;
  eligible_device_count: number;
  source_policy: FleetControlSourcePolicy;
  device_summary: FleetControlDeviceSummary;
  device_control_states: FleetDeviceControlState[];
  last_device_results: FleetDeviceDispatchResult[];
  control_confidence: FleetControlConfidence;
  readiness: FleetReadiness;
  timeline_events: FleetTimelineEvent[];
};

export type ModbusTcpSlaveConfigPayload = {
  enabled: boolean;
  cci_enabled: boolean;
  host: string;
  port: number;
  unit_id: number;
  cci_readback_enabled: boolean;
  cci_readback_range_percent: number;
  cci_readback_stable_seconds: number;
  cci_readback_active_power_only: boolean;
};

export type HsmBridgeConfigPayload = {
  enabled: boolean;
  hsm_port: string;
  inverter_port: string;
  hsm_baud_rate: number;
  hsm_parity: "N" | "E" | "O";
  hsm_stop_bits: number;
  hsm_byte_size: number;
  frame_gap_ms: number;
  forward_delay_ms: number;
  ack_timeout_ms: number;
};

export type Device = {
  device_id: string;
  name: string;
  brand: string;
  model: string;
  protocol: string;
  transport: string;
  connection_settings: ConnectionSettings;
  status: string;
  created_at: string;
};

export type CatalogModel = {
  brand: string;
  model: string;
  protocol: string;
  transport: string;
  defaults: ConnectionSettings;
  features: string[];
  verification: {
    status: string;
    source_document: string | null;
    source_version: string | null;
    last_reviewed_at: string | null;
    field_tested: boolean;
    notes: string | null;
  };
  telemetry_count: number;
  visible_telemetry_count: number;
  command_count: number;
  writable_command_count: number;
  alarm_count: number;
  discovery_signature: {
    register: number | null;
    function: string | null;
  };
  capabilities: {
    has_active_power_limit: boolean;
    has_reactive_power_control: boolean;
    has_start_stop_control: boolean;
    supports_live_telemetry: boolean;
    supports_power_history: boolean;
  };
};

export type SystemOptions = {
  protocols: string[];
  transports: string[];
  device_statuses: string[];
};

export type SerialPortInfo = {
  name: string;
  description: string;
};

export type SerialPortsResponse = {
  ports: SerialPortInfo[];
};

export type NetworkInterfaceInfo = {
  name: string;
  address: string;
};

export type NetworkInterfacesResponse = {
  interfaces: NetworkInterfaceInfo[];
};

export type NetworkConfigAddress = {
  address: string;
  prefix_length: number;
};

export type NetworkConfigInterface = {
  interface_name: string;
  device_type: string;
  state: string;
  connection_name: string | null;
  mac_address: string | null;
  live_addresses: NetworkConfigAddress[];
  live_gateway: string | null;
  live_dns_servers: string[];
  ipv4_method: "auto" | "manual" | "unknown";
  configured_addresses: NetworkConfigAddress[];
  gateway: string | null;
  dns_servers: string[];
  autoconnect: boolean | null;
  use_default_route: boolean;
  editable: boolean;
};

export type PendingNetworkChange = {
  interface_name: string;
  connection_name: string | null;
  expires_at: string;
  remaining_seconds: number;
};

export type NetworkConfigSnapshot = {
  supported: boolean;
  apply_supported: boolean;
  platform: string;
  manager: string;
  message: string | null;
  confirmation_timeout_seconds: number;
  pending_change: PendingNetworkChange | null;
  interfaces: NetworkConfigInterface[];
};

export type NetworkConfigApplyPayload = {
  interface_name: string;
  ipv4_method: "auto" | "manual";
  address: string | null;
  prefix_length: number | null;
  addresses?: NetworkConfigAddress[];
  gateway: string | null;
  dns_servers: string[];
  autoconnect: boolean;
  use_default_route: boolean;
};

export type SystemHealthStatusCounts = {
  total: number;
  online: number;
  pending: number;
  offline: number;
  warning: number;
  fault: number;
};

export type SystemHealthPollingSnapshot = {
  enabled: boolean;
  running: boolean;
  thread_start_count: number;
  last_thread_started_at: string | null;
  last_loop_error: string | null;
  last_loop_error_at: string | null;
  consecutive_loop_error_count: number;
  scheduled_device_count: number;
  pollable_device_count: number;
  last_cycle_started_at: string | null;
  last_cycle_completed_at: string | null;
  last_cycle_duration_ms: number | null;
  last_due_device_count: number;
  last_polled_device_count: number;
  last_success_count: number;
  last_error_count: number;
  last_endpoint_group_count: number;
  last_skipped_device_count: number;
  next_full_poll_due_in_seconds_min: number | null;
  next_full_poll_due_in_seconds_max: number | null;
};

export type SystemHealthLiveCacheSnapshot = {
  entry_count: number;
  power_history_device_count: number;
  power_history_sample_count: number;
  connection_lifecycle_count: number;
};

export type SystemHealthHistoryStorageSnapshot = {
  database_path: string;
  current_bytes: number;
  max_bytes: number;
  usage_percent: number;
  row_count: number;
};

export type SystemHealthModbusTcpSlaveSnapshot = {
  enabled: boolean;
  running: boolean;
  host: string;
  port: number;
  unit_id: number;
  startup_error: string | null;
};

export type SystemHealthEndpointHotspot = {
  endpoint_type: "tcp" | "serial";
  endpoint_label: string;
  device_count: number;
  online_count: number;
  pending_count: number;
  offline_count: number;
  note: string;
  devices: string[];
};

export type SystemHealthEndpointRuntime = {
  endpoint_type: "tcp" | "serial";
  endpoint_label: string;
  device_count: number;
  online_count: number;
  pending_count: number;
  offline_count: number;
  shared: boolean;
  state: "idle" | "healthy" | "degraded" | "cooldown";
  consecutive_connect_failures: number;
  remaining_backoff_seconds: number;
  cooldown_until: string | null;
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error_stage: string | null;
  last_error: string | null;
  last_poll_status: string | null;
  last_outcome: string;
  skipped_polls: number;
  queued_full_due_count: number;
  queued_heartbeat_due_count: number;
  planned_full_count: number;
  planned_heartbeat_count: number;
  executed_full_count: number;
  executed_heartbeat_count: number;
  priority_deferral_count: number;
  last_priority_at: string | null;
  last_cycle_started_at: string | null;
  last_cycle_completed_at: string | null;
  last_cycle_duration_ms: number | null;
  last_lock_wait_ms: number | null;
  average_lock_wait_ms: number | null;
  last_operation_duration_ms: number | null;
  average_cycle_duration_ms: number | null;
  average_operation_duration_ms: number | null;
  last_round_trip_duration_ms: number | null;
  average_round_trip_duration_ms: number | null;
  tcp_sample_count: number;
  current_lock_owner_thread_name: string | null;
  current_lock_held_ms: number | null;
  modbus_framer: string | null;
  priority_pending: boolean;
  priority_remaining_ms: number | null;
  last_command_age_ms: number | null;
  polling_profile: string;
  adaptive_mode: string;
  expected_active_power_cycle_seconds: number | null;
  active_power_slo_target_seconds: number;
  active_power_slo_state: "pass" | "warning" | "fail" | "unknown";
  estimated_full_telemetry_cycle_seconds: number | null;
  full_telemetry_slo_target_seconds: number;
  full_telemetry_slo_state: "pass" | "warning" | "fail" | "unknown";
  recommendations: string[];
  devices: string[];
};

export type SystemHealthIdentitySnapshot = {
  edge_id: string;
  edge_id_source: string;
  hostname: string;
  platform: string;
  app_version: string;
  build_label: string;
  build_commit: string | null;
  build_time: string | null;
  backend_started_at: string;
  backend_path: string;
};

export type SystemHealthBroadcastDevice = {
  device_id: string;
  name: string;
  brand: string;
  model: string;
  protocol: string;
  transport: string;
  status: string;
  unit_id: number | null;
};

export type SystemHealthBroadcastGroup = {
  endpoint_type: "serial" | "rtu_over_tcp" | "modbus_tcp_gateway" | "unsupported";
  endpoint_label: string;
  broadcast_mode: "rtu_serial" | "rtu_over_tcp" | "modbus_tcp" | "none";
  state: "ready" | "warning" | "blocked" | "not_applicable";
  summary: string;
  detail: string;
  device_count: number;
  online_count: number;
  model_count: number;
  command_profile_count: number;
  duplicate_unit_ids: number[];
  issues: string[];
  devices: SystemHealthBroadcastDevice[];
};

export type SystemHealthDataQualityIssueDevice = {
  device_id: string;
  name: string;
  invalid_count: number;
  warning_count: number;
  unavailable_count: number;
  examples: string[];
};

export type SystemHealthDataQualitySnapshot = {
  total_points: number;
  valid_points: number;
  warning_points: number;
  invalid_points: number;
  unavailable_points: number;
  devices_with_issues: number;
  issue_devices: SystemHealthDataQualityIssueDevice[];
};

export type SystemHealthServiceLevelsSnapshot = {
  active_power_target_seconds: number;
  full_telemetry_target_seconds: number;
  command_target_seconds: number;
  active_power_within_target: number;
  active_power_over_target: number;
  active_power_unknown: number;
  full_telemetry_within_target: number;
  full_telemetry_over_target: number;
  full_telemetry_unknown: number;
};

export type SystemHealthResponse = {
  generated_at: string;
  identity: SystemHealthIdentitySnapshot;
  status_counts: SystemHealthStatusCounts;
  polling: SystemHealthPollingSnapshot;
  live_cache: SystemHealthLiveCacheSnapshot;
  history_storage: SystemHealthHistoryStorageSnapshot;
  modbus_tcp_slave: SystemHealthModbusTcpSlaveSnapshot;
  broadcast_groups: SystemHealthBroadcastGroup[];
  endpoint_hotspots: SystemHealthEndpointHotspot[];
  endpoint_runtimes: SystemHealthEndpointRuntime[];
  data_quality: SystemHealthDataQualitySnapshot;
  service_levels: SystemHealthServiceLevelsSnapshot;
};

export type CreateDevicePayload = {
  name: string;
  brand: string;
  model: string;
  protocol: string;
  transport: string;
  connection_settings: ConnectionSettings;
};

export type ProtocolTestPayload = {
  protocol: string;
  transport: string;
  brand?: string;
  model?: string;
  connection_settings: ConnectionSettings;
  profile_overrides?: Record<string, unknown>;
  operation_id?: string | null;
  operation_label?: string | null;
};

export type ProtocolTestResult = {
  success: boolean;
  protocol: string;
  transport: string;
  message: string;
  diagnostics: Record<string, string | number | boolean>;
};

export type DeviceOverviewMetrics = {
  power_kw: number;
  daily_energy_kwh: number;
  total_energy_kwh: number;
  temperature_c: number;
};

export type DeviceTelemetryValue = string | number | boolean | null;

export type DeviceOverviewTelemetryPoint = {
  key: string;
  label: string;
  value: DeviceTelemetryValue;
  raw_value: DeviceTelemetryValue;
  display_value: string;
  unit: string;
  section: string;
  visible: boolean;
  writable: boolean;
  quality: "valid" | "warning" | "invalid" | "unavailable";
  quality_reason: string | null;
};

export type DeviceOverviewCommandPoint = {
  key: string;
  label: string;
  unit: string;
  section: string;
  datatype: string;
  scale: number;
  min_value: number | null;
  max_value: number | null;
  step: number | null;
  last_set_value: number | null;
  last_set_display: string | null;
  last_set_at: string | null;
};

export type DeviceOverviewDiagnostics = {
  last_poll_status: string;
  response_time_ms: number;
  retries: number;
  last_error: string | null;
  poll_kind: string;
  last_contact_at: string | null;
  last_valid_data_at: string | null;
  communication_state: "pending" | "online" | "offline";
  data_freshness: "fresh" | "stale" | "missing";
  communication_age_seconds: number | null;
  data_age_seconds: number | null;
};

export type DeviceOverview = {
  device: Device;
  metrics: DeviceOverviewMetrics;
  diagnostics: DeviceOverviewDiagnostics;
  telemetry: DeviceOverviewTelemetryPoint[];
  commands: DeviceOverviewCommandPoint[];
};

export type PowerHistorySeries = {
  device_id: string | null;
  label: string;
  timestamps: string[];
  values: number[];
};

export type FleetPowerHistoryResponse = {
  labels: string[];
  device_series: PowerHistorySeries[];
  total_series: PowerHistorySeries;
};

export type DevicePowerHistoryResponse = {
  device_id: string;
  labels: string[];
  timestamps: string[];
  values: number[];
};

export type PowerHistoryQuery = {
  start?: string;
  end?: string;
  max_points?: number;
};

export type ModbusScanFunction = "holding" | "input";
export type RtuDiscoveryProtocol = "auto" | "modbus_rtu" | "aurora";

export type RtuScanRequest = {
  operation_id?: string | null;
  operation_label?: string | null;
  port: string;
  baud_rate: number;
  parity: string;
  stop_bits: number;
  byte_size: number;
  timeout_seconds: number;
  retries: number;
  slave_ids: number[];
  registers: number[];
  function: ModbusScanFunction;
  handle_local_echo?: boolean;
  use_rs485_mode?: boolean;
  rs485_rts_level_for_tx?: boolean;
  rs485_rts_level_for_rx?: boolean;
  rs485_loopback?: boolean;
  rs485_delay_before_tx_ms?: number;
  rs485_delay_before_rx_ms?: number;
};

export type RtuScanMatch = {
  slave_id: number;
  register: number;
  function: ModbusScanFunction;
  raw_values: number[];
};

export type RtuScanResponse = {
  matches: RtuScanMatch[];
};

export type TcpScanRequest = {
  operation_id?: string | null;
  operation_label?: string | null;
  host_start: string;
  host_end: string;
  port: number;
  timeout_seconds: number;
  retries: number;
  unit_ids: number[];
  registers: number[];
  function: ModbusScanFunction;
};

export type TcpScanMatch = {
  host: string;
  unit_id: number;
  register: number;
  function: ModbusScanFunction;
  raw_values: number[];
};

export type TcpScanResponse = {
  matches: TcpScanMatch[];
};

export type DiscoveryCandidateProfile = {
  brand: string;
  model: string;
  protocol: string;
  transport: string;
};

export type DeviceDiscoveryRtuRequest = {
  operation_id?: string | null;
  operation_label?: string | null;
  port: string;
  preferred_brand?: string | null;
  preferred_model?: string | null;
  baud_rate: number;
  parity: string;
  stop_bits: number;
  byte_size: number;
  timeout_seconds: number;
  retries: number;
  scan_protocol?: RtuDiscoveryProtocol;
  slave_ids: number[];
  handle_local_echo?: boolean;
  use_rs485_mode?: boolean;
  rs485_rts_level_for_tx?: boolean;
  rs485_rts_level_for_rx?: boolean;
  rs485_loopback?: boolean;
  rs485_delay_before_tx_ms?: number;
  rs485_delay_before_rx_ms?: number;
};

export type DeviceDiscoveryRtuResult = {
  port: string;
  unit_id: number;
  register: number;
  function: ModbusScanFunction;
  raw_values: number[];
  signature_label?: string | null;
  candidate_brands: string[];
  candidate_profile_count: number;
  candidate_profiles: DiscoveryCandidateProfile[];
};

export type DeviceDiscoveryRtuResponse = {
  duration_ms: number;
  request_count: number;
  results: DeviceDiscoveryRtuResult[];
};

export type DeviceDiscoveryTcpRequest = {
  operation_id?: string | null;
  operation_label?: string | null;
  host_start: string;
  host_end: string;
  port_start: number;
  port_end: number;
  timeout_seconds: number;
  retries: number;
  unit_ids: number[];
  preferred_brand?: string | null;
  preferred_model?: string | null;
  gateway_protocol_mode?: "tcp" | "rtu_over_tcp";
};

export type DeviceDiscoveryTcpResult = {
  host: string;
  port: number;
  unit_id: number;
  register: number;
  function: ModbusScanFunction;
  raw_values: number[];
  candidate_brands: string[];
  candidate_profile_count: number;
  candidate_profiles: DiscoveryCandidateProfile[];
};

export type DeviceDiscoveryTcpResponse = {
  duration_ms: number;
  request_count: number;
  results: DeviceDiscoveryTcpResult[];
};

export type ProtocolOperationState = {
  active: boolean;
  operation_id: string | null;
  kind: string | null;
  label: string | null;
  status: "idle" | "running" | "cancelling";
  started_at: string | null;
  updated_at: string | null;
  request_count: number;
  active_requests: number;
  active_connections: number;
  cancel_requested: boolean;
};

export type ProtocolOperationControlPayload = {
  operation_id?: string | null;
  reason?: string | null;
};

export type ActivePowerLimitPayload = {
  value: number;
};

export type NumericCommandPayload = {
  value: number;
};

export type CommandResponse = {
  success: boolean;
  message: string;
  device_id: string;
  command: string;
  diagnostics: Record<string, string | number | boolean>;
};

export type UpdateDevicePayload = CreateDevicePayload & {
  status: string;
};

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  let response: Response;
  const { timeoutMs, signal: externalSignal, ...fetchInit } = init ?? {};
  const controller = new AbortController();
  const handleExternalAbort = () => controller.abort();
  if (externalSignal?.aborted) {
    handleExternalAbort();
  } else {
    externalSignal?.addEventListener("abort", handleExternalAbort, { once: true });
  }
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs ?? API_REQUEST_TIMEOUT_MS);

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...fetchInit,
      signal: controller.signal,
    });
  } catch (error) {
    if (
      typeof error === "object" &&
      error !== null &&
      "name" in error &&
      error.name === "AbortError"
    ) {
      if (externalSignal?.aborted) {
        throw new Error("Operazione annullata.");
      }
      throw new Error("Il backend non ha risposto in tempo utile. Riprova tra qualche secondo.");
    }
    throw new Error(`Impossibile raggiungere il backend all'indirizzo ${API_BASE_URL}.`);
  } finally {
    window.clearTimeout(timeoutId);
    externalSignal?.removeEventListener("abort", handleExternalAbort);
  }

  if (!response.ok) {
    let detail = "";
    const contentType = response.headers.get("content-type") ?? "";

    if (contentType.includes("application/json")) {
      try {
        const body = (await response.json()) as { detail?: string | Array<{ msg?: string }> };
        if (typeof body.detail === "string" && body.detail.length > 0) {
          detail = ` ${body.detail}`;
        } else if (Array.isArray(body.detail) && body.detail.length > 0) {
          const firstMessage = body.detail
            .map((entry) => (typeof entry?.msg === "string" ? entry.msg : ""))
            .find((message) => message.length > 0);
          if (firstMessage) {
            detail = ` ${firstMessage}`;
          }
        }
      } catch {
        detail = "";
      }
    }

    throw new Error(`Richiesta al backend fallita (${response.status}).${detail}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

function buildQueryString(query?: Record<string, string | number | boolean | undefined>): string {
  if (!query) {
    return "";
  }

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined) {
      continue;
    }
    params.set(key, String(value));
  }

  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
}

export const getDashboardSummary = () => request<DashboardSummary>("/dashboard/summary");
export const getFleetControlStatus = () => request<FleetControlStatus>("/fleet-control/status");
export const setFleetControlSetpoint = (payload: ActivePowerLimitPayload) =>
  request<FleetControlStatus>("/fleet-control/setpoint", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const clearFleetControlSetpoint = () =>
  request<FleetControlStatus>("/fleet-control/setpoint", {
    method: "DELETE",
  });
export const updateModbusTcpSlaveConfig = (payload: ModbusTcpSlaveConfigPayload) =>
  request<FleetControlStatus>("/fleet-control/modbus-slave-config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const updateHsmBridgeConfig = (payload: HsmBridgeConfigPayload) =>
  request<FleetControlStatus>("/fleet-control/hsm-bridge-config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const getDevices = () => request<Device[]>("/devices");
export const getDevice = (deviceId: string) => request<Device>(`/devices/${deviceId}`);
export const sendActivePowerLimit = (deviceId: string, payload: ActivePowerLimitPayload) =>
  request<CommandResponse>(`/devices/${deviceId}/commands/active-power-limit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const sendDeviceCommand = (
  deviceId: string,
  commandKey: string,
  payload: NumericCommandPayload,
) =>
  request<CommandResponse>(`/devices/${deviceId}/commands/${commandKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const getDeviceOverview = (
  deviceId: string,
  options?: { refresh?: boolean },
) =>
  request<DeviceOverview>(
    `/devices/${deviceId}/overview${buildQueryString({
      refresh: options?.refresh ?? true,
    })}`,
  );
export const getDashboardPowerHistory = (query?: PowerHistoryQuery) =>
  request<FleetPowerHistoryResponse>(
    `/dashboard/power-history${buildQueryString(query)}`,
  );
export const getDevicePowerHistory = (deviceId: string, query?: PowerHistoryQuery) =>
  request<DevicePowerHistoryResponse>(
    `/devices/${deviceId}/power-history${buildQueryString(query)}`,
  );
export const getCatalogModels = () => request<CatalogModel[]>("/catalog/models");
export const getSystemOptions = () => request<SystemOptions>("/system/options");
export const getSerialPorts = () => request<SerialPortsResponse>("/system/serial-ports");
export const getNetworkInterfaces = () =>
  request<NetworkInterfacesResponse>("/system/network-interfaces");
export const getNetworkConfiguration = () =>
  request<NetworkConfigSnapshot>("/system/network-config");
export const applyNetworkConfiguration = (payload: NetworkConfigApplyPayload) =>
  request<NetworkConfigSnapshot>("/system/network-config/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const confirmNetworkConfiguration = () =>
  request<NetworkConfigSnapshot>("/system/network-config/confirm", {
    method: "POST",
  });
export const rollbackNetworkConfiguration = () =>
  request<NetworkConfigSnapshot>("/system/network-config/rollback", {
    method: "POST",
  });
export const getSystemHealth = () => request<SystemHealthResponse>("/system/health");
export const createDevice = (payload: CreateDevicePayload) =>
  request<Device>("/devices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const testProtocolConnection = (payload: ProtocolTestPayload) =>
  request<ProtocolTestResult>("/protocols/test-connection", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const scanRtuDevices = (
  payload: RtuScanRequest,
  options?: { signal?: AbortSignal },
) =>
  request<RtuScanResponse>("/protocols/scan-rtu", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    timeoutMs: API_DISCOVERY_REQUEST_TIMEOUT_MS,
    signal: options?.signal,
  });
export const scanTcpDevices = (
  payload: TcpScanRequest,
  options?: { signal?: AbortSignal },
) =>
  request<TcpScanResponse>("/protocols/scan-tcp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    timeoutMs: API_DISCOVERY_REQUEST_TIMEOUT_MS,
    signal: options?.signal,
  });
export const discoverRtuDevices = (
  payload: DeviceDiscoveryRtuRequest,
  options?: { signal?: AbortSignal },
) =>
  request<DeviceDiscoveryRtuResponse>("/protocols/discover-rtu", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    timeoutMs: API_DISCOVERY_REQUEST_TIMEOUT_MS,
    signal: options?.signal,
  });
export const discoverTcpDevices = (
  payload: DeviceDiscoveryTcpRequest,
  options?: { signal?: AbortSignal },
) =>
  request<DeviceDiscoveryTcpResponse>("/protocols/discover-tcp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    timeoutMs: API_DISCOVERY_REQUEST_TIMEOUT_MS,
    signal: options?.signal,
  });
export const getProtocolOperationState = () =>
  request<ProtocolOperationState>("/protocols/operation-state");
export const cancelProtocolOperation = (payload: ProtocolOperationControlPayload = {}) =>
  request<ProtocolOperationState>("/protocols/operation-cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const finishProtocolOperation = (payload: ProtocolOperationControlPayload = {}) =>
  request<ProtocolOperationState>("/protocols/operation-finish", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const updateDevice = (deviceId: string, payload: UpdateDevicePayload) =>
  request<Device>(`/devices/${deviceId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const deleteDevice = (deviceId: string) =>
  request<void>(`/devices/${deviceId}`, { method: "DELETE" });
export const deleteAllDevices = () =>
  request<{ deleted_count: number }>("/devices?confirm=true", { method: "DELETE" });
