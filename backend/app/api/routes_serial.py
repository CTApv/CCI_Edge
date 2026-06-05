from fastapi import APIRouter
from serial.tools import list_ports

from app.schemas.serial_schemas import SerialPortInfo, SerialPortsResponse

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/serial-ports", response_model=SerialPortsResponse)
def list_serial_ports() -> SerialPortsResponse:
    ports = [
        SerialPortInfo(name=port.device, description=port.description or "")
        for port in list_ports.comports()
    ]
    return SerialPortsResponse(ports=ports)
