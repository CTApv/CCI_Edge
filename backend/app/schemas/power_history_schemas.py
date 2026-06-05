from pydantic import BaseModel


class PowerHistorySeries(BaseModel):
    device_id: str | None = None
    label: str
    timestamps: list[str]
    values: list[float]


class FleetPowerHistoryResponse(BaseModel):
    labels: list[str]
    device_series: list[PowerHistorySeries]
    total_series: PowerHistorySeries


class DevicePowerHistoryResponse(BaseModel):
    device_id: str
    labels: list[str]
    timestamps: list[str]
    values: list[float]
