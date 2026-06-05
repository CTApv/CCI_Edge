from ipaddress import IPv4Address, ip_address
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.connection_settings import normalize_connection_settings
from app.schemas.device_schemas import ProtocolValue, TransportValue


ConnectionValue = str | int | float | bool
DiagnosticValue = str | int | float | bool
ModbusScanFunction = Literal["holding", "input"]
RtuDiscoveryProtocol = Literal["auto", "modbus_rtu", "aurora"]
GatewayProtocolMode = Literal["tcp", "rtu_over_tcp"]
ProtocolOperationStatus = Literal["idle", "running", "cancelling"]

RTU_SCAN_MAX_SLAVE_IDS = 32
RTU_SCAN_MAX_REGISTERS = 32
RTU_SCAN_MAX_REQUESTS = 128
TCP_SCAN_MAX_HOSTS = 512
TCP_SCAN_MAX_UNIT_IDS = 32
TCP_SCAN_MAX_REGISTERS = 8
TCP_SCAN_MAX_REQUESTS = 1024
DISCOVERY_RTU_MAX_SLAVE_IDS = 64
DISCOVERY_TCP_MAX_HOSTS = 256
DISCOVERY_TCP_MAX_PORTS = 16
DISCOVERY_TCP_MAX_UNIT_IDS = 32
DISCOVERY_TCP_MAX_ENDPOINTS = 512
DISCOVERY_CANDIDATE_PROFILE_PREVIEW = 12


class ProtocolOperationStateResponse(BaseModel):
    active: bool
    operation_id: str | None = None
    kind: str | None = None
    label: str | None = None
    status: ProtocolOperationStatus = "idle"
    started_at: str | None = None
    updated_at: str | None = None
    request_count: int = 0
    active_requests: int = 0
    active_connections: int = 0
    cancel_requested: bool = False


class ProtocolOperationControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    operation_id: str | None = None
    reason: str | None = None


class ProtocolTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    protocol: ProtocolValue
    transport: TransportValue
    brand: str | None = None
    model: str | None = None
    connection_settings: dict[str, ConnectionValue]
    profile_overrides: dict[str, object] = Field(default_factory=dict)
    operation_id: str | None = None
    operation_label: str | None = None

    @model_validator(mode="after")
    def normalize_test_connection_settings(self) -> Self:
        self.connection_settings = normalize_connection_settings(
            protocol=self.protocol,
            transport=self.transport,
            settings=self.connection_settings,
            require_required_settings=False,
            enforce_transport_match=False,
        )
        return self


class ProtocolTestResponse(BaseModel):
    success: bool
    protocol: str
    transport: str
    message: str
    diagnostics: dict[str, DiagnosticValue]


class RtuReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    port: str = Field(min_length=1)
    baud_rate: int = Field(gt=0)
    parity: str = Field(min_length=1)
    stop_bits: int = Field(gt=0)
    byte_size: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    retries: int = Field(ge=0)
    slave_id: int = Field(ge=0, le=247)
    function: ModbusScanFunction
    register_address: int = Field(alias="register", ge=0, le=65535)
    count: int = Field(gt=0, le=125)
    handle_local_echo: bool = False
    use_rs485_mode: bool = False
    rs485_rts_level_for_tx: bool = True
    rs485_rts_level_for_rx: bool = False
    rs485_loopback: bool = False
    rs485_delay_before_tx_ms: float | None = Field(default=None, ge=0)
    rs485_delay_before_rx_ms: float | None = Field(default=None, ge=0)


class RtuReadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    success: bool
    connect_ok: bool
    function_used: ModbusScanFunction
    register_address: int = Field(alias="register")
    count: int
    unit_argument_style: str
    elapsed_ms: int
    tx_trace: list[str]
    rx_trace: list[str]
    raw_values: list[int] | None = None
    error: str | None = None


class RtuScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str | None = None
    operation_label: str | None = None
    port: str = Field(min_length=1)
    baud_rate: int = Field(gt=0)
    parity: str = Field(min_length=1)
    stop_bits: int = Field(gt=0)
    byte_size: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    retries: int = Field(ge=0)
    slave_ids: list[int] = Field(min_length=1, max_length=RTU_SCAN_MAX_SLAVE_IDS)
    registers: list[int] = Field(min_length=1, max_length=RTU_SCAN_MAX_REGISTERS)
    function: ModbusScanFunction = "holding"
    handle_local_echo: bool = False
    use_rs485_mode: bool = False
    rs485_rts_level_for_tx: bool = True
    rs485_rts_level_for_rx: bool = False
    rs485_loopback: bool = False
    rs485_delay_before_tx_ms: float | None = Field(default=None, ge=0)
    rs485_delay_before_rx_ms: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_scan_limits(self) -> "RtuScanRequest":
        if any(slave_id < 0 or slave_id > 247 for slave_id in self.slave_ids):
            raise ValueError("Each RTU scan slave id must be between 0 and 247.")
        if any(register < 0 or register > 65535 for register in self.registers):
            raise ValueError("Each RTU scan register must be between 0 and 65535.")
        if len(self.slave_ids) * len(self.registers) > RTU_SCAN_MAX_REQUESTS:
            raise ValueError("RTU scan request is too large.")
        return self


class RtuScanMatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slave_id: int
    register_address: int = Field(alias="register")
    function: ModbusScanFunction
    raw_values: list[int]


class RtuScanResponse(BaseModel):
    matches: list[RtuScanMatch]


class TcpScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str | None = None
    operation_label: str | None = None
    host_start: str = Field(min_length=7)
    host_end: str = Field(min_length=7)
    port: int = Field(gt=0, le=65535)
    timeout_seconds: float = Field(gt=0)
    retries: int = Field(ge=0)
    unit_ids: list[int] = Field(min_length=1, max_length=TCP_SCAN_MAX_UNIT_IDS)
    registers: list[int] = Field(min_length=1, max_length=TCP_SCAN_MAX_REGISTERS)
    function: ModbusScanFunction = "holding"

    @model_validator(mode="after")
    def validate_scan_limits(self) -> "TcpScanRequest":
        start_ip = self._parse_ipv4(self.host_start)
        end_ip = self._parse_ipv4(self.host_end)
        if start_ip > end_ip:
            raise ValueError("TCP scan host range is invalid.")
        if start_ip.packed[:3] != end_ip.packed[:3]:
            raise ValueError("TCP scan host range must stay within the same /24 subnet.")
        host_count = int(end_ip) - int(start_ip) + 1
        if host_count > TCP_SCAN_MAX_HOSTS:
            raise ValueError("TCP scan host range is too large.")
        if any(unit_id < 0 or unit_id > 247 for unit_id in self.unit_ids):
            raise ValueError("Each TCP scan unit id must be between 0 and 247.")
        if any(register < 0 or register > 65535 for register in self.registers):
            raise ValueError("Each TCP scan register must be between 0 and 65535.")
        if host_count * len(self.unit_ids) * len(self.registers) > TCP_SCAN_MAX_REQUESTS:
            raise ValueError("TCP scan request is too large.")
        return self

    @staticmethod
    def _parse_ipv4(raw_value: str) -> IPv4Address:
        parsed = ip_address(raw_value)
        if not isinstance(parsed, IPv4Address):
            raise ValueError("Only IPv4 host ranges are supported for TCP scan.")
        return parsed


class TcpScanMatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    host: str
    unit_id: int
    register_address: int = Field(alias="register")
    function: ModbusScanFunction
    raw_values: list[int]


class TcpScanResponse(BaseModel):
    matches: list[TcpScanMatch]


class DiscoveryCandidateProfile(BaseModel):
    brand: str
    model: str
    protocol: ProtocolValue
    transport: TransportValue


class DeviceDiscoveryRtuRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str | None = None
    operation_label: str | None = None
    port: str = Field(min_length=1)
    preferred_brand: str | None = None
    preferred_model: str | None = None
    baud_rate: int = Field(gt=0)
    parity: str = Field(min_length=1)
    stop_bits: int = Field(gt=0)
    byte_size: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    retries: int = Field(ge=0)
    scan_protocol: RtuDiscoveryProtocol = "auto"
    slave_ids: list[int] = Field(min_length=1, max_length=DISCOVERY_RTU_MAX_SLAVE_IDS)
    handle_local_echo: bool = False
    use_rs485_mode: bool = False
    rs485_rts_level_for_tx: bool = True
    rs485_rts_level_for_rx: bool = False
    rs485_loopback: bool = False
    rs485_delay_before_tx_ms: float | None = Field(default=None, ge=0)
    rs485_delay_before_rx_ms: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_discovery_limits(self) -> "DeviceDiscoveryRtuRequest":
        if any(slave_id < 0 or slave_id > 247 for slave_id in self.slave_ids):
            raise ValueError("Each RTU discovery slave id must be between 0 and 247.")
        return self


class DeviceDiscoveryRtuResult(BaseModel):
    port: str
    unit_id: int
    register_address: int = Field(alias="register")
    function: ModbusScanFunction
    raw_values: list[int]
    signature_label: str | None = None
    candidate_brands: list[str]
    candidate_profile_count: int
    candidate_profiles: list[DiscoveryCandidateProfile] = Field(
        max_length=DISCOVERY_CANDIDATE_PROFILE_PREVIEW
    )


class DeviceDiscoveryRtuResponse(BaseModel):
    duration_ms: int
    request_count: int
    results: list[DeviceDiscoveryRtuResult]


class DeviceDiscoveryTcpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str | None = None
    operation_label: str | None = None
    host_start: str = Field(min_length=7)
    host_end: str = Field(min_length=7)
    port_start: int = Field(gt=0, le=65535)
    port_end: int = Field(gt=0, le=65535)
    timeout_seconds: float = Field(gt=0)
    retries: int = Field(ge=0)
    unit_ids: list[int] = Field(min_length=1, max_length=DISCOVERY_TCP_MAX_UNIT_IDS)
    preferred_brand: str | None = None
    preferred_model: str | None = None
    gateway_protocol_mode: GatewayProtocolMode = "tcp"

    @model_validator(mode="after")
    def validate_discovery_limits(self) -> "DeviceDiscoveryTcpRequest":
        start_ip = self._parse_ipv4(self.host_start)
        end_ip = self._parse_ipv4(self.host_end)
        if start_ip > end_ip:
            raise ValueError("TCP discovery host range is invalid.")
        if start_ip.packed[:3] != end_ip.packed[:3]:
            raise ValueError("TCP discovery host range must stay within the same /24 subnet.")
        host_count = int(end_ip) - int(start_ip) + 1
        if host_count > DISCOVERY_TCP_MAX_HOSTS:
            raise ValueError("TCP discovery host range is too large.")
        if self.port_start > self.port_end:
            raise ValueError("TCP discovery port range is invalid.")
        port_count = self.port_end - self.port_start + 1
        if port_count > DISCOVERY_TCP_MAX_PORTS:
            raise ValueError("TCP discovery port range is too large.")
        if any(unit_id < 0 or unit_id > 247 for unit_id in self.unit_ids):
            raise ValueError("Each TCP discovery unit id must be between 0 and 247.")
        if host_count * port_count * len(self.unit_ids) > DISCOVERY_TCP_MAX_ENDPOINTS:
            raise ValueError("TCP discovery request is too large.")
        return self

    @staticmethod
    def _parse_ipv4(raw_value: str) -> IPv4Address:
        parsed = ip_address(raw_value)
        if not isinstance(parsed, IPv4Address):
            raise ValueError("Only IPv4 host ranges are supported for TCP discovery.")
        return parsed


class DeviceDiscoveryTcpResult(BaseModel):
    host: str
    port: int
    unit_id: int
    register_address: int = Field(alias="register")
    function: ModbusScanFunction
    raw_values: list[int]
    candidate_brands: list[str]
    candidate_profile_count: int
    candidate_profiles: list[DiscoveryCandidateProfile] = Field(
        max_length=DISCOVERY_CANDIDATE_PROFILE_PREVIEW
    )


class DeviceDiscoveryTcpResponse(BaseModel):
    duration_ms: int
    request_count: int
    results: list[DeviceDiscoveryTcpResult]
