from fastapi import APIRouter, HTTPException, Query

from app.schemas.device_overview_schemas import DeviceOverviewResponse
from app.services.device_overview_service import DeviceOverviewService

router = APIRouter(prefix="/api/devices", tags=["devices"])
device_overview_service = DeviceOverviewService()


@router.get("/{device_id}/overview", response_model=DeviceOverviewResponse)
def get_device_overview(
    device_id: str,
    refresh: bool = Query(default=True),
) -> DeviceOverviewResponse:
    overview = device_overview_service.get_overview(
        device_id,
        allow_live_poll_on_cache_miss=refresh,
    )
    if overview is None:
        raise HTTPException(status_code=404, detail="Device not found")

    return overview
