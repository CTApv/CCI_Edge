from fastapi import APIRouter, HTTPException

from app.schemas.protocol_schemas import (
    DeviceDiscoveryRtuRequest,
    DeviceDiscoveryRtuResponse,
    DeviceDiscoveryTcpRequest,
    DeviceDiscoveryTcpResponse,
    ProtocolOperationControlRequest,
    ProtocolOperationStateResponse,
    ProtocolTestRequest,
    ProtocolTestResponse,
    RtuReadRequest,
    RtuReadResponse,
    RtuScanRequest,
    RtuScanResponse,
    TcpScanRequest,
    TcpScanResponse,
)
from app.services.protocol_test_service import (
    ProtocolOperationBusyError,
    ProtocolOperationCancelledError,
    protocol_test_service,
)

router = APIRouter(prefix="/api/protocols", tags=["protocols"])


def _raise_protocol_operation_error(exc: Exception) -> None:
    if isinstance(exc, ProtocolOperationBusyError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ProtocolOperationCancelledError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


@router.get("/operation-state", response_model=ProtocolOperationStateResponse)
def protocol_operation_state() -> ProtocolOperationStateResponse:
    return protocol_test_service.protocol_operation_state()


@router.post("/operation-cancel", response_model=ProtocolOperationStateResponse)
def cancel_protocol_operation(
    payload: ProtocolOperationControlRequest | None = None,
) -> ProtocolOperationStateResponse:
    return protocol_test_service.cancel_protocol_operation(
        operation_id=payload.operation_id if payload is not None else None,
    )


@router.post("/operation-finish", response_model=ProtocolOperationStateResponse)
def finish_protocol_operation(
    payload: ProtocolOperationControlRequest | None = None,
) -> ProtocolOperationStateResponse:
    return protocol_test_service.finish_protocol_operation(
        operation_id=payload.operation_id if payload is not None else None,
    )


@router.post("/test-connection", response_model=ProtocolTestResponse)
def test_connection(payload: ProtocolTestRequest) -> ProtocolTestResponse:
    try:
        return protocol_test_service.test_connection(payload)
    except (ProtocolOperationBusyError, ProtocolOperationCancelledError) as exc:
        _raise_protocol_operation_error(exc)
        raise


@router.post("/read-rtu", response_model=RtuReadResponse)
def read_rtu(payload: RtuReadRequest) -> RtuReadResponse:
    return protocol_test_service.read_rtu(payload)


@router.post("/read-rtu-raw", response_model=RtuReadResponse)
def read_rtu_raw(payload: RtuReadRequest) -> RtuReadResponse:
    return protocol_test_service.read_rtu_raw(payload)


@router.post("/scan-rtu", response_model=RtuScanResponse)
def scan_rtu(payload: RtuScanRequest) -> RtuScanResponse:
    try:
        return protocol_test_service.scan_rtu(payload)
    except (ProtocolOperationBusyError, ProtocolOperationCancelledError) as exc:
        _raise_protocol_operation_error(exc)
        raise


@router.post("/scan-tcp", response_model=TcpScanResponse)
def scan_tcp(payload: TcpScanRequest) -> TcpScanResponse:
    try:
        return protocol_test_service.scan_tcp(payload)
    except (ProtocolOperationBusyError, ProtocolOperationCancelledError) as exc:
        _raise_protocol_operation_error(exc)
        raise


@router.post("/discover-rtu", response_model=DeviceDiscoveryRtuResponse)
def discover_rtu(payload: DeviceDiscoveryRtuRequest) -> DeviceDiscoveryRtuResponse:
    try:
        return protocol_test_service.discover_rtu(payload)
    except (ProtocolOperationBusyError, ProtocolOperationCancelledError) as exc:
        _raise_protocol_operation_error(exc)
        raise


@router.post("/discover-tcp", response_model=DeviceDiscoveryTcpResponse)
def discover_tcp(payload: DeviceDiscoveryTcpRequest) -> DeviceDiscoveryTcpResponse:
    try:
        return protocol_test_service.discover_tcp(payload)
    except (ProtocolOperationBusyError, ProtocolOperationCancelledError) as exc:
        _raise_protocol_operation_error(exc)
        raise
