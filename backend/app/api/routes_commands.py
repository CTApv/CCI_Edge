from fastapi import APIRouter, HTTPException

from app.schemas.command_schemas import (
    ActivePowerLimitRequest,
    CommandResponse,
    NumericCommandRequest,
)
from app.services.command_service import command_service

router = APIRouter(prefix="/api/devices", tags=["commands"])


@router.post("/{device_id}/sinvert/preflight/{command_key}", response_model=CommandResponse)
def sinvert_preflight_route(device_id: str, command_key: str, payload: NumericCommandRequest) -> CommandResponse:
    """Fresh read-only program/consent check. Does not submit or remember a command."""
    from app.services.device_service import device_service
    from app.services.inverter_profile_resolver import inverter_profile_resolver
    from app.services.sinvert_s7_command_service import sinvert_s7_command_service
    device=device_service.get_device(device_id)
    if device is None:raise HTTPException(status_code=404,detail="Device not found")
    model=inverter_profile_resolver.resolve_for_device(device)
    point=next((p for p in model.command_points if p.key==command_key),None) if model else None
    if device.protocol!='s7_tcp' or point is None:raise HTTPException(status_code=400,detail="Comando SINVERT non disponibile")
    result=sinvert_s7_command_service.write(device,point,payload.value,dry_run=True)
    return CommandResponse(success=result.success,
        message="Verifica completata in sola lettura. Nessun comando inviato; i consensi verranno riletti all'invio." if result.success else result.error,
        device_id=device_id,command=command_key,diagnostics=result.diagnostics)


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
