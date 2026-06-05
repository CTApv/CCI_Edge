from pydantic import BaseModel


class SerialPortInfo(BaseModel):
    name: str
    description: str


class SerialPortsResponse(BaseModel):
    ports: list[SerialPortInfo]
