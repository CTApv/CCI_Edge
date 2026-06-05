from fastapi import APIRouter, HTTPException, status

from app.schemas.device_schemas import DeviceCreate, DeviceResponse, DeviceUpdate
from app.services.device_service import device_service
from app.services.live_cache import live_cache
from app.services.polling_engine import poll_device_with_runtime

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("", response_model=list[DeviceResponse])
def list_devices_route() -> list[DeviceResponse]:
    return device_service.list_devices()


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def create_device_route(payload: DeviceCreate) -> DeviceResponse:
    try:
        device = device_service.create_device(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _prime_device_status(device)


@router.delete("", response_model=dict[str, int])
def delete_all_devices_route(confirm: bool = False) -> dict[str, int]:
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm bulk device deletion with confirm=true.",
        )

    return {"deleted_count": device_service.delete_all_devices()}


@router.put("/{device_id}", response_model=DeviceResponse)
def update_device_route(device_id: str, payload: DeviceUpdate) -> DeviceResponse:
    try:
        device = device_service.update_device(device_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    return _prime_device_status(device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device_route(device_id: str) -> None:
    deleted = device_service.delete_device(device_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Device not found")


def _prime_device_status(device: DeviceResponse) -> DeviceResponse:
    entry = poll_device_with_runtime(device)
    if entry is not None:
        live_cache.set(device.device_id, entry)

    return device_service.get_device(device.device_id) or device
