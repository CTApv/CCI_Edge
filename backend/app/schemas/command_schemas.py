from pydantic import BaseModel


DiagnosticValue = str | int | float | bool


class ActivePowerLimitRequest(BaseModel):
    value: float


class NumericCommandRequest(BaseModel):
    value: float


class CommandResponse(BaseModel):
    success: bool
    message: str
    device_id: str
    command: str
    diagnostics: dict[str, DiagnosticValue]
