from typing import Literal

from pydantic import BaseModel

from app.schemas.device_schemas import DeviceResponse


OverviewValue = str | int | float | bool | None


class DeviceOverviewMetrics(BaseModel):
    power_kw: float
    daily_energy_kwh: float
    total_energy_kwh: float
    temperature_c: float


class DeviceOverviewDiagnostics(BaseModel):
    last_poll_status: str
    response_time_ms: int
    retries: int
    last_error: str | None
    poll_kind: str = "full"
    last_contact_at: str | None = None
    last_valid_data_at: str | None = None
    communication_state: Literal["pending", "online", "offline"] = "pending"
    data_freshness: Literal["fresh", "stale", "missing"] = "missing"
    communication_age_seconds: float | None = None
    data_age_seconds: float | None = None


class DeviceTelemetryPoint(BaseModel):
    key: str
    label: str
    value: OverviewValue
    display_value: str
    raw_value: OverviewValue = None
    unit: str = ""
    section: str = "General"
    visible: bool = True
    writable: bool = False


class DeviceCommandPoint(BaseModel):
    key: str
    label: str
    unit: str = ""
    section: str = "Control"
    datatype: str
    scale: float = 1.0
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    last_set_value: float | None = None
    last_set_display: str | None = None
    last_set_at: str | None = None


class DeviceOverviewResponse(BaseModel):
    device: DeviceResponse
    metrics: DeviceOverviewMetrics
    diagnostics: DeviceOverviewDiagnostics
    telemetry: list[DeviceTelemetryPoint] = []
    commands: list[DeviceCommandPoint] = []
