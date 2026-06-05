from dataclasses import dataclass, field


@dataclass(slots=True)
class Device:
    device_id: str
    name: str
    brand: str
    model: str
    protocol: str
    transport: str
    metadata: dict[str, str] = field(default_factory=dict)
