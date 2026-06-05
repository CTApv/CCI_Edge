from fastapi import APIRouter, HTTPException, Query

from app.schemas.device_schemas import DeviceResponse
from app.schemas.power_history_schemas import DevicePowerHistoryResponse
from app.services.dashboard_service import dashboard_service
from app.services.device_service import device_service

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(device_id: str) -> DeviceResponse:
    device = device_service.get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    return device


@router.get("/{device_id}/power-history", response_model=DevicePowerHistoryResponse)
def get_device_power_history(
    device_id: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    max_points: int | None = Query(default=None, ge=32, le=900),
) -> DevicePowerHistoryResponse:
    history = dashboard_service.get_device_power_history(
        device_id,
        start_timestamp=start,
        end_timestamp=end,
        max_points=max_points,
    )
    if history is None:
        raise HTTPException(status_code=404, detail="Device not found")

    return history
