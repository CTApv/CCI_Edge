from pydantic import BaseModel


class DashboardActivePowerResponse(BaseModel):
    active_power_kw: float
    active_power_w: float
    online_devices: int
    total_devices: int
    generated_at: str


class DashboardSummaryResponse(BaseModel):
    total_devices: int
    online_devices: int
    offline_devices: int
    active_alarms: int
    total_power_kw: float
    nominal_power_kw: float
    nominal_power_device_count: int
    power_utilization_percent: float | None
    daily_energy_kwh: float
    total_energy_kwh: float
