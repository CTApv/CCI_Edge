from app.models.inverter_model import InverterModel, InverterPoint


CGS_SINVERT_BOX_BRAND = "CGS"
CGS_SINVERT_BOX_MODELS = tuple(
    f"SINVERT BOX ({unit_count} INV U)" for unit_count in range(1, 6)
)


def _meta(*, section: str, manual_id: int, **extra: object) -> dict[str, object]:
    return {
        "section": section,
        "manual_id": manual_id,
        **extra,
    }


def _telemetry_point(
    key: str,
    label: str,
    address: int,
    length: int,
    datatype: str,
    *,
    section: str,
    manual_id: int,
    unit: str = "",
    bitmask_labels: dict[int, str] | None = None,
    command: str | None = None,
) -> InverterPoint:
    extra: dict[str, object] = {}
    if bitmask_labels is not None:
        extra["bitmask_labels"] = bitmask_labels
    if command is not None:
        extra["command"] = command
    return InverterPoint(
        key=key,
        label=label,
        kind="telemetry",
        register_type="holding",
        address=address,
        length=length,
        datatype=datatype,
        unit=unit,
        protocol_meta=_meta(section=section, manual_id=manual_id, **extra),
    )


def _command_point(
    key: str,
    label: str,
    address: int,
    datatype: str,
    *,
    section: str,
    manual_id: int,
    unit: str = "",
    min_value: float | None = None,
    max_value: float | None = None,
    step: float | None = None,
    enum_map: dict[int, str] | None = None,
) -> InverterPoint:
    extra: dict[str, object] = {}
    if min_value is not None:
        extra["min_value"] = min_value
    if max_value is not None:
        extra["max_value"] = max_value
    if step is not None:
        extra["step"] = step
    if enum_map is not None:
        extra["enum_map"] = enum_map
    return InverterPoint(
        key=key,
        label=label,
        kind="command",
        register_type="holding",
        address=address,
        length=2 if datatype == "float32" else 1,
        datatype=datatype,
        unit=unit,
        writable=True,
        protocol_meta=_meta(section=section, manual_id=manual_id, **extra),
    )


def _build_telemetry(unit_count: int) -> list[InverterPoint]:
    points = [
        _telemetry_point(
            "system_status_bits",
            "Stato sistema",
            1,
            1,
            "uint16",
            section="Stato box",
            manual_id=1,
            bitmask_labels={
                0: "Sistema bloccato per manomissione",
                2: "Errore CPU",
                5: "Modalita di regolazione asservita",
                6: "Modalita di regolazione test",
            },
        ),
    ]

    availability_bits = {
        unit_index + 7: f"INV U {unit_index} disponibile alla regolazione"
        for unit_index in range(1, unit_count + 1)
    }
    points.append(
        _telemetry_point(
            "regulation_availability_bits",
            "Disponibilita alla regolazione inverter unit",
            165,
            1,
            "uint16",
            section="Stato inverter unit",
            manual_id=5,
            bitmask_labels=availability_bits,
        )
    )

    running_bits = {
        unit_index + 7: f"INV U {unit_index} in marcia"
        for unit_index in range(1, unit_count + 1)
    }
    communication_error_bits = {
        unit_index + 7: f"Errore comunicazione INV U {unit_index}"
        for unit_index in range(1, unit_count + 1)
    }
    points.extend(
        [
            _telemetry_point(
                "inverter_running_bits",
                "Inverter unit in marcia",
                80,
                1,
                "uint16",
                section="Stato inverter unit",
                manual_id=10,
                bitmask_labels=running_bits,
            ),
            _telemetry_point(
                "communication_error_bits",
                "Errori comunicazione inverter unit",
                81,
                1,
                "uint16",
                section="Stato e allarmi",
                manual_id=15,
                bitmask_labels=communication_error_bits,
            ),
        ]
    )

    for unit_index in range(1, unit_count + 1):
        power_address = 92 + ((unit_index - 1) * 2)
        setpoint_address = 112 + ((unit_index - 1) * 2)
        command_key = "active_power_limit" if unit_index == 1 else f"active_power_limit_inv_u_{unit_index}"
        points.extend(
            [
                _telemetry_point(
                    f"active_power_inv_u_{unit_index}",
                    f"Potenza attiva INV U {unit_index}",
                    power_address,
                    2,
                    "float32",
                    section="Potenza attiva",
                    manual_id=19 + unit_index,
                ),
                _telemetry_point(
                    "active_power_limit" if unit_index == 1 else f"active_power_limit_pct_inv_u_{unit_index}",
                    f"Setpoint limite potenza attiva INV U {unit_index}",
                    setpoint_address,
                    2,
                    "float32",
                    section="Controllo potenza",
                    manual_id=24 + unit_index,
                    unit="%",
                    command=command_key,
                ),
            ]
        )

    points.append(
        _telemetry_point(
            "setpoint_activation_mode",
            "Attivazione setpoint limite (opzione A)",
            167,
            1,
            "int16",
            section="Controllo potenza",
            manual_id=30,
        )
    )
    points.append(
        _telemetry_point(
            "setpoint_activation_bits",
            "Attivazione setpoint limite (opzione B)",
            0,
            1,
            "uint16",
            section="Controllo potenza",
            manual_id=31,
            bitmask_labels={3: "Setpoint limite attivi"},
        )
    )
    return points


def _build_commands(unit_count: int) -> list[InverterPoint]:
    commands = []
    for unit_index in range(1, unit_count + 1):
        commands.append(
            _command_point(
                "active_power_limit" if unit_index == 1 else f"active_power_limit_inv_u_{unit_index}",
                f"Limite potenza attiva INV U {unit_index}",
                112 + ((unit_index - 1) * 2),
                "float32",
                section="Controllo potenza",
                manual_id=24 + unit_index,
                unit="%",
                min_value=0,
                max_value=100,
                step=0.1,
            )
        )
    commands.append(
        _command_point(
            "setpoint_activation_mode",
            "Attivazione setpoint limite (opzione A)",
            167,
            "int16",
            section="Controllo potenza",
            manual_id=30,
            enum_map={-1: "ON", 0: "Usa opzione B (bit)", 1: "OFF"},
        )
    )
    return commands


def build_cgs_sinvert_box_models() -> list[InverterModel]:
    models = []
    for unit_count, model_name in enumerate(CGS_SINVERT_BOX_MODELS, start=1):
        models.append(
            InverterModel(
                brand=CGS_SINVERT_BOX_BRAND,
                model=model_name,
                protocol="modbus_tcp",
                transport="tcp",
                defaults={
                    "host": "192.168.1.100",
                    "port": 502,
                    "unit_id": 1,
                    "timeout": 3.0,
                    "test_register": 1,
                    "test_count": 1,
                    "test_function": "holding",
                    "max_registers_per_request": 125,
                },
                features=[
                    "manuale CGS V1.1 verificato",
                    f"gestione {unit_count} inverter unit",
                    "telemetria e stato box",
                    "controllo potenza attiva per inverter unit",
                ],
                telemetry_points=_build_telemetry(unit_count),
                command_points=_build_commands(unit_count),
                catalog_meta={
                    "verification_status": "manual_verified",
                    "source_document": "MANUALE E MAPPATURA DATI - CGS SINVERT BOX",
                    "source_version": "V1.1",
                    "last_reviewed_at": "2026-10-01",
                    "field_tested": False,
                    "notes": (
                        "Indirizzi riportati come nel manuale. Float32 MSW-first big-endian. "
                        "L'opzione B al bit 3 dell'indirizzo 0 e documentata come alternativa "
                        "all'opzione A ma non viene esposta in scrittura per evitare di sovrascrivere "
                        "gli altri bit del registro senza una lettura-modifica-scrittura atomica."
                    ),
                },
            )
        )
    return models
