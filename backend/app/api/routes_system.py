from fastapi import APIRouter, HTTPException

from app.schemas.system_schemas import (
    DEVICE_STATUS_OPTIONS,
    NetworkConfigApplyRequest,
    NetworkConfigSnapshotResponse,
    NetworkInterfaceInfo,
    NetworkInterfacesResponse,
    PROTOCOL_OPTIONS,
    SystemHealthResponse,
    TRANSPORT_OPTIONS,
    SystemOptionsResponse,
)
from app.services.network_config_service import network_config_service
from app.services.network_interface_service import network_interface_service
from app.services.system_health_service import system_health_service

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/options", response_model=SystemOptionsResponse)
def get_system_options() -> SystemOptionsResponse:
    return SystemOptionsResponse(
        protocols=list(PROTOCOL_OPTIONS),
        transports=list(TRANSPORT_OPTIONS),
        device_statuses=list(DEVICE_STATUS_OPTIONS),
    )


@router.get("/network-interfaces", response_model=NetworkInterfacesResponse)
def get_network_interfaces() -> NetworkInterfacesResponse:
    return NetworkInterfacesResponse(
        interfaces=[
            NetworkInterfaceInfo(name=interface["name"], address=interface["address"])
            for interface in network_interface_service.list_ipv4_bind_addresses()
        ]
    )


@router.get("/network-config", response_model=NetworkConfigSnapshotResponse)
def get_network_config() -> NetworkConfigSnapshotResponse:
    return NetworkConfigSnapshotResponse.model_validate(network_config_service.get_snapshot())


@router.post("/network-config/apply", response_model=NetworkConfigSnapshotResponse)
def apply_network_config(payload: NetworkConfigApplyRequest) -> NetworkConfigSnapshotResponse:
    try:
        snapshot = network_config_service.apply_configuration(
            interface_name=payload.interface_name,
            ipv4_method=payload.ipv4_method,
            address=payload.address,
            prefix_length=payload.prefix_length,
            addresses=[item.model_dump() for item in payload.addresses],
            gateway=payload.gateway,
            dns_servers=payload.dns_servers,
            autoconnect=payload.autoconnect,
            use_default_route=payload.use_default_route,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return NetworkConfigSnapshotResponse.model_validate(snapshot)


@router.post("/network-config/confirm", response_model=NetworkConfigSnapshotResponse)
def confirm_network_config() -> NetworkConfigSnapshotResponse:
    return NetworkConfigSnapshotResponse.model_validate(
        network_config_service.confirm_pending_change(),
    )


@router.post("/network-config/rollback", response_model=NetworkConfigSnapshotResponse)
def rollback_network_config() -> NetworkConfigSnapshotResponse:
    return NetworkConfigSnapshotResponse.model_validate(
        network_config_service.rollback_pending_change(),
    )


@router.get("/health", response_model=SystemHealthResponse)
def get_system_health() -> SystemHealthResponse:
    return SystemHealthResponse.model_validate(system_health_service.get_snapshot())
