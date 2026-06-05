from fastapi import APIRouter, HTTPException

from app.schemas.command_schemas import (
    ActivePowerLimitRequest,
    CommandResponse,
    NumericCommandRequest,
)
from app.services.command_service import command_service

router = APIRouter(prefix="/api/devices", tags=["commands"])


@router.post("/{device_id}/commands/active-power-limit", response_model=CommandResponse)
def send_active_power_limit_route(
    device_id: str,
    payload: ActivePowerLimitRequest,
) -> CommandResponse:
    response = command_service.send_active_power_limit(device_id, payload)
    if response is None:
        raise HTTPException(status_code=404, detail="Device not found")

    return response


@router.post("/{device_id}/commands/{command_key}", response_model=CommandResponse)
def send_numeric_command_route(
    device_id: str,
    command_key: str,
    payload: NumericCommandRequest,
) -> CommandResponse:
    response = command_service.send_numeric_command(
        device_id,
        command_key=command_key,
        value=payload.value,
    )
    if response is None:
        raise HTTPException(status_code=404, detail="Device not found")

    return response
