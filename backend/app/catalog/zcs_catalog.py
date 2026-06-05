from app.models.inverter_model import InverterModel, InverterPoint


ZCS_BRAND = "ZCS"
ZCS_MODEL = "ZUCCHETTI Azzurro 3PH 60KTL-V3"

ZCS_V3_STATUS_MAP = {
    0: "Stato di attesa",
    1: "Stato di controllo rete AC",
    2: "Connesso alla rete AC (RUN)",
    3: "Stato di alimentazione di emergenza",
    4: "Stato di guasto recuperabile",
    5: "Stato di guasto permanente",
    6: "Stato di aggiornamento",
    7: "Stato di autocarica",
    8: "Stato SVG",
    9: "Stato PID",
    10: "Stato di limitazione della produzione",
    11: "Stato di monitoraggio standby",
}

ZCS_V3_POWER_CONTROL_BITS = {
    0: "Controllo potenza attiva abilitato",
    1: "Controllo potenza reattiva abilitato",
    2: "Modalita reattiva in fattore di potenza",
    3: "SVG abilitato",
    4: "Modalita SVG reattiva",
    5: "Compensazione fattore di potenza SVG",
    8: "Funzionamento notturno abilitato",
}


def telemetry_point(
    key: str,
    label: str,
    address: int,
    length: int,
    datatype: str,
    *,
    scale: float = 1.0,
    unit: str = "",
    section: str,
    summary_metric: str | None = None,
    enum_map: dict[int, str] | None = None,
    bitmask_labels: dict[int, str] | None = None,
    display_format: str | None = None,
    display_prefix: str | None = None,
    display_width: int | None = None,
    visible: bool = True,
    command: str | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {"section": section}
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map
    if bitmask_labels is not None:
        protocol_meta["bitmask_labels"] = bitmask_labels
    if display_format is not None:
        protocol_meta["display_format"] = display_format
    if display_prefix is not None:
        protocol_meta["display_prefix"] = display_prefix
    if display_width is not None:
        protocol_meta["display_width"] = display_width
    if command is not None:
        protocol_meta["command"] = command

    return InverterPoint(
        key=key,
        label=label,
        kind="telemetry",
        register_type="holding",
        address=address,
        length=length,
        datatype=datatype,
        scale=scale,
        unit=unit,
        visible=visible,
        protocol_meta=protocol_meta,
    )


def command_point(
    key: str,
    label: str,
    address: int,
    datatype: str,
    *,
    scale: float = 1.0,
    unit: str = "",
    section: str,
    min_value: float | None = None,
    max_value: float | None = None,
    step: float | None = None,
    protocol_meta: dict[str, object] | None = None,
) -> InverterPoint:
    point_protocol_meta: dict[str, object] = {"section": section}
    if protocol_meta is not None:
        point_protocol_meta.update(protocol_meta)
    if min_value is not None:
        point_protocol_meta["min_value"] = min_value
    if max_value is not None:
        point_protocol_meta["max_value"] = max_value
    if step is not None:
        point_protocol_meta["step"] = step

    return InverterPoint(
        key=key,
        label=label,
        kind="command",
        register_type="holding",
        address=address,
        length=1,
        datatype=datatype,
        scale=scale,
        unit=unit,
        writable=True,
        protocol_meta=point_protocol_meta,
    )


def build_zcs_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point(
            "status",
            "Stato inverter",
            0x0404,
            1,
            "uint16",
            section="Stato e diagnostica",
            summary_metric="status",
            enum_map=ZCS_V3_STATUS_MAP,
        ),
        telemetry_point(
            "active_power_kw",
            "Potenza attiva",
            0x0485,
            1,
            "int16",
            scale=0.01,
            unit="kW",
            section="Potenza",
            summary_metric="power_kw",
        ),
        telemetry_point(
            "reactive_power_kvar",
            "Potenza reattiva",
            0x0486,
            1,
            "int16",
            scale=0.01,
            unit="kVAr",
            section="Potenza",
        ),
        telemetry_point(
            "power_control_register",
            "Registro controllo potenze",
            0x1105,
            1,
            "uint16",
            section="Controllo potenza",
            bitmask_labels=ZCS_V3_POWER_CONTROL_BITS,
            display_format="hex",
            display_prefix="0x",
            display_width=4,
        ),
        telemetry_point(
            "active_power_limit_pct",
            "Setpoint potenza attiva",
            0x1106,
            1,
            "uint16",
            scale=0.1,
            unit="%",
            section="Controllo potenza",
            command="active_power_limit",
        ),
        telemetry_point(
            "reactive_power_setpoint_percent",
            "Setpoint potenza reattiva",
            0x1108,
            1,
            "uint16",
            scale=0.1,
            unit="%",
            section="Controllo reattivo",
        ),
    ]


def build_zcs_commands() -> list[InverterPoint]:
    return [
        command_point(
            "active_power_limit",
            "Setpoint potenza attiva",
            0x1106,
            "uint16",
            scale=0.1,
            unit="%",
            section="Controllo potenza",
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            protocol_meta={"force_multi_write": True, "modbus_write_function": "0x10"},
        ),
        command_point(
            "reactive_power_target_percent",
            "Setpoint potenza reattiva",
            0x1108,
            "uint16",
            scale=0.1,
            unit="%",
            section="Controllo reattivo",
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            protocol_meta={"force_multi_write": True, "modbus_write_function": "0x10"},
        ),
    ]


def build_zcs_defaults(protocol: str) -> dict[str, str | int | float | bool]:
    common_defaults: dict[str, str | int | float | bool] = {
        "timeout_seconds": 2,
        "retries": 1,
        "poll_interval_seconds": 15,
        "test_register": 0x0404,
        "test_count": 1,
        "test_function": "holding",
    }
    if protocol == "modbus_rtu":
        return {
            "port": "COM1",
            "slave_id": 1,
            "baud_rate": 9600,
            "parity": "N",
            "stop_bits": 1,
            "byte_size": 8,
            **common_defaults,
        }
    return {
        "host": "192.168.1.10",
        "port": 502,
        "unit_id": 1,
        **common_defaults,
    }


def build_zcs_models(protocol: str, transport: str) -> list[InverterModel]:
    return [
        InverterModel(
            brand=ZCS_BRAND,
            model=ZCS_MODEL,
            protocol=protocol,
            transport=transport,
            defaults=build_zcs_defaults(protocol),
            features=[
                "mappa registri zcs v3",
                "modbus rtu e modbus tcp",
                "telemetria stato e potenza",
                "setpoint potenza attiva con readback",
                "setpoint potenza reattiva",
            ],
            telemetry_points=build_zcs_telemetry(),
            command_points=build_zcs_commands(),
        )
    ]
