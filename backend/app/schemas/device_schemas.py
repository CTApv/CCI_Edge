from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.connection_settings import (
    merge_model_connection_defaults,
    normalize_connection_settings,
)


ConnectionValue = str | int | float | bool
ProtocolValue = Literal[
    "modbus_rtu",
    "modbus_tcp",
    "sunspec",
    "aurora",
    "delta_rs485",
]
TransportValue = Literal["serial", "tcp"]


class DeviceBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str
    brand: str
    model: str
    protocol: ProtocolValue
    transport: TransportValue
    connection_settings: dict[str, ConnectionValue]
    profile_overrides: dict[str, object] = Field(default_factory=dict)


class DeviceCreate(DeviceBase):
    @model_validator(mode="after")
    def validate_connection_settings(self) -> Self:
        self._validate_identity_fields()
        self.connection_settings = merge_model_connection_defaults(
            brand=self.brand,
            model=self.model,
            protocol=self.protocol,
            transport=self.transport,
            settings=self.connection_settings,
        )
        self.connection_settings = normalize_connection_settings(
            protocol=self.protocol,
            transport=self.transport,
            settings=self.connection_settings,
            require_required_settings=True,
        )
        return self

    def _validate_identity_fields(self) -> None:
        for field_name, label in (("name", "nome"), ("brand", "marca"), ("model", "modello")):
            if getattr(self, field_name).strip() == "":
                raise ValueError(f"Il campo '{label}' e obbligatorio.")


class DeviceUpdate(DeviceBase):
    status: str

    @model_validator(mode="after")
    def validate_connection_settings(self) -> Self:
        for field_name, label in (("name", "nome"), ("brand", "marca"), ("model", "modello")):
            if getattr(self, field_name).strip() == "":
                raise ValueError(f"Il campo '{label}' e obbligatorio.")
        if self.status.strip() == "":
            raise ValueError("Il campo 'stato' e obbligatorio.")
        self.connection_settings = merge_model_connection_defaults(
            brand=self.brand,
            model=self.model,
            protocol=self.protocol,
            transport=self.transport,
            settings=self.connection_settings,
        )
        self.connection_settings = normalize_connection_settings(
            protocol=self.protocol,
            transport=self.transport,
            settings=self.connection_settings,
            require_required_settings=True,
        )
        return self


class DeviceResponse(DeviceBase):
    status: str
    device_id: str
    created_at: str
