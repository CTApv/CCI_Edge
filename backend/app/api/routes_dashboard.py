from fastapi import APIRouter, Query

from app.schemas.dashboard_schemas import DashboardActivePowerResponse, DashboardSummaryResponse
from app.schemas.power_history_schemas import FleetPowerHistoryResponse
from app.services.dashboard_service import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary() -> DashboardSummaryResponse:
    return dashboard_service.get_summary()


@router.get("/active-power", response_model=DashboardActivePowerResponse)
def get_dashboard_active_power() -> DashboardActivePowerResponse:
    return dashboard_service.get_active_power_sum()


@router.get("/power-history", response_model=FleetPowerHistoryResponse)
def get_dashboard_power_history(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    max_points: int | None = Query(default=240, ge=32, le=900),
) -> FleetPowerHistoryResponse:
    return dashboard_service.get_fleet_power_history(
        start_timestamp=start,
        end_timestamp=end,
        max_points=max_points,
    )
