from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class InverterPoint:
    key: str
    label: str
    kind: str
    register_type: str
    address: int
    length: int
    datatype: str
    scale: float = 1.0
    unit: str = ""
    writable: bool = False
    visible: bool = True
    scale_factor_key: str | None = None
    protocol_meta: dict[str, str | int | float | bool] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class InverterModel:
    brand: str
    model: str
    protocol: str
    transport: str
    defaults: dict[str, str | int | float | bool] = field(default_factory=dict)
    features: list[str] = field(default_factory=list)
    telemetry_points: list[InverterPoint] = field(default_factory=list)
    command_points: list[InverterPoint] = field(default_factory=list)
    alarm_points: list[InverterPoint] = field(default_factory=list)
    inherits_from: str | None = None
