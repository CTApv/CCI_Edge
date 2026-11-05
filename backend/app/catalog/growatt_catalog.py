from app.models.inverter_model import InverterModel, InverterPoint


GROWATT_BRAND = "GROWATT"
GROWATT_MIN_MODEL = "MIN / TL-X / TL-XH / TL-XH US"
GROWATT_TL3_MODEL = "MAX / MID / MAC TL3-X"
GROWATT_MAX_1500_MODEL = "MAX 1500V / MAX-X LV"
GROWATT_MOD_MODEL = "MOD TL3-XH"
GROWATT_MIX_MODEL = "MIX Storage"
GROWATT_SPA_MODEL = "SPA Storage"
GROWATT_SPH_MODEL = "SPH Storage"

GROWATT_MODELS = (
    GROWATT_MIN_MODEL,
    GROWATT_TL3_MODEL,
    GROWATT_MAX_1500_MODEL,
    GROWATT_MOD_MODEL,
    GROWATT_MIX_MODEL,
    GROWATT_SPA_MODEL,
    GROWATT_SPH_MODEL,
)

GROWATT_STATUS_MAP = {
    0: "Attesa",
    1: "Normale",
    3: "Guasto",
}

GROWATT_REMOTE_ON_OFF_MAP = {
    0: "Off",
    1: "On",
    2: "BDC Off",
    3: "BDC On",
}


def build_catalog_meta(*, notes: str) -> dict[str, object]:
    return {
        "verification_status": "manual_verified",
        "source_document": "Growatt Inverter Modbus RTU Protocol",
        "source_version": "V1.24",
        "last_reviewed_at": "2026-06-12",
        "field_tested": False,
        "notes": notes,
    }


def telemetry_point(
    key: str,
    label: str,
    register_type: str,
    address: int,
    length: int,
    datatype: str,
    *,
    scale: float = 1.0,
    unit: str = "",
    section: str,
    visible: bool = True,
    summary_metric: str | None = None,
    enum_map: dict[int, str] | None = None,
    command: str | None = None,
    heartbeat: bool = False,
    optional_block: bool = False,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {
        "section": section,
        "manual_register": address,
    }
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map
    if command is not None:
        protocol_meta["command"] = command
    if heartbeat:
        protocol_meta["heartbeat"] = True
    if optional_block:
        protocol_meta["optional_block"] = True

    return InverterPoint(
        key=key,
        label=label,
        kind="telemetry",
        register_type=register_type,
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
    enum_map: dict[int, str] | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {
        "section": section,
        "manual_register": address,
        "broadcast_supported": True,
    }
    if min_value is not None:
        protocol_meta["min_value"] = min_value
    if max_value is not None:
        protocol_meta["max_value"] = max_value
    if step is not None:
        protocol_meta["step"] = step
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map

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
        protocol_meta=protocol_meta,
    )


def build_common_commands() -> list[InverterPoint]:
    return [
        command_point(
            "start_stop",
            "Accensione / spegnimento remoto",
            0,
            "uint16",
            section="Controllo",
            enum_map=GROWATT_REMOTE_ON_OFF_MAP,
        ),
        command_point(
            "active_power_limit",
            "Limite potenza attiva",
            3,
            "uint16",
            unit="%",
            section="Controllo potenza",
            min_value=0,
            max_value=100,
            step=1,
        ),
        command_point(
            "reactive_power_limit",
            "Limite potenza reattiva",
            4,
            "int16",
            unit="%",
            section="Controllo potenza",
            min_value=-100,
            max_value=100,
            step=1,
        ),
    ]


def build_control_readback() -> list[InverterPoint]:
    return [
        telemetry_point(
            "remote_on_off",
            "Stato comando remoto",
            "holding",
            0,
            1,
            "uint16",
            section="Controllo",
            enum_map=GROWATT_REMOTE_ON_OFF_MAP,
        ),
        telemetry_point(
            "active_power_limit_pct",
            "Limite potenza attiva impostato",
            "holding",
            3,
            1,
            "uint16",
            unit="%",
            section="Controllo potenza",
            command="active_power_limit",
        ),
    ]


def build_pv_points(
    start_register: int,
    count: int,
    *,
    first_index: int = 1,
) -> list[InverterPoint]:
    points: list[InverterPoint] = []
    for offset in range(count):
        index = first_index + offset
        base = start_register + (offset * 4)
        optional = index > 2
        points.extend(
            [
                telemetry_point(
                    f"pv{index}_voltage_v",
                    f"Tensione FV {index}",
                    "input",
                    base,
                    1,
                    "uint16",
                    scale=0.1,
                    unit="V",
                    section="Ingresso FV",
                    optional_block=optional,
                ),
                telemetry_point(
                    f"pv{index}_current_a",
                    f"Corrente FV {index}",
                    "input",
                    base + 1,
                    1,
                    "uint16",
                    scale=0.1,
                    unit="A",
                    section="Ingresso FV",
                    optional_block=optional,
                ),
                telemetry_point(
                    f"pv{index}_power_kw",
                    f"Potenza FV {index}",
                    "input",
                    base + 2,
                    2,
                    "uint32",
                    scale=0.0001,
                    unit="kW",
                    section="Ingresso FV",
                    optional_block=optional,
                ),
            ]
        )
    return points


def build_low_map_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point(
            "status",
            "Stato inverter",
            "input",
            0,
            1,
            "uint16",
            section="Stato e allarmi",
            summary_metric="status",
            enum_map=GROWATT_STATUS_MAP,
            heartbeat=True,
        ),
        telemetry_point("dc_power_kw", "Potenza FV totale", "input", 1, 2, "uint32", scale=0.0001, unit="kW", section="Ingresso FV"),
        *build_pv_points(3, 8),
        telemetry_point("active_power_kw", "Potenza attiva in uscita", "input", 35, 2, "uint32", scale=0.0001, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("mains_frequency_hz", "Frequenza rete", "input", 37, 1, "uint16", scale=0.01, unit="Hz", section="Rete AC"),
        telemetry_point("mains_voltage_v", "Tensione fase 1", "input", 38, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("ac_current_a", "Corrente fase 1", "input", 39, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_voltage_l2_v", "Tensione fase 2", "input", 42, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_current_l2_a", "Corrente fase 2", "input", 43, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_voltage_l3_v", "Tensione fase 3", "input", 46, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_current_l3_a", "Corrente fase 3", "input", 47, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_voltage_ab_v", "Tensione concatenata AB", "input", 50, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_bc_v", "Tensione concatenata BC", "input", 51, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_ca_v", "Tensione concatenata CA", "input", 52, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("daily_energy_kwh", "Energia giornaliera", "input", 53, 2, "uint32", scale=0.1, unit="kWh", section="Energia", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_kwh", "Energia totale", "input", 55, 2, "uint32", scale=0.1, unit="kWh", section="Energia", summary_metric="total_energy_kwh"),
        telemetry_point("total_pv_energy_kwh", "Energia FV totale", "input", 91, 2, "uint32", scale=0.1, unit="kWh", section="Energia"),
        telemetry_point("temperature_c", "Temperatura inverter", "input", 93, 1, "int16", scale=0.1, unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("ipm_temperature_c", "Temperatura IPM", "input", 94, 1, "int16", scale=0.1, unit="C", section="Termico"),
        telemetry_point("boost_temperature_c", "Temperatura boost", "input", 95, 1, "int16", scale=0.1, unit="C", section="Termico"),
        telemetry_point("fault_main_code", "Codice guasto principale", "input", 105, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("fault_sub_code", "Sottocodice guasto", "input", 107, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("warning_high_bits", "Warning high bits", "input", 110, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("warning_sub_code", "Sottocodice warning", "input", 111, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("warning_main_code", "Codice warning principale", "input", 112, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("active_power_percent", "Potenza attiva percentuale", "input", 113, 1, "uint16", unit="%", section="Potenza", optional_block=True),
        *build_control_readback(),
    ]


def build_high_map_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("status", "Stato inverter", "input", 3000, 1, "uint16", section="Stato e allarmi", summary_metric="status", heartbeat=True),
        telemetry_point("dc_power_kw", "Potenza FV totale", "input", 3001, 2, "uint32", scale=0.0001, unit="kW", section="Ingresso FV"),
        *build_pv_points(3003, 4),
        telemetry_point("system_output_power_kw", "Potenza sistema in uscita", "input", 3019, 2, "uint32", scale=0.0001, unit="kW", section="Potenza"),
        telemetry_point("reactive_power_kvar", "Potenza reattiva", "input", 3021, 2, "int32", scale=0.0001, unit="kVAr", section="Potenza"),
        telemetry_point("active_power_kw", "Potenza attiva in uscita", "input", 3023, 2, "uint32", scale=0.0001, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("mains_frequency_hz", "Frequenza rete", "input", 3025, 1, "uint16", scale=0.01, unit="Hz", section="Rete AC"),
        telemetry_point("mains_voltage_v", "Tensione fase 1", "input", 3026, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("ac_current_a", "Corrente fase 1", "input", 3027, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_voltage_l2_v", "Tensione fase 2", "input", 3030, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_current_l2_a", "Corrente fase 2", "input", 3031, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_voltage_l3_v", "Tensione fase 3", "input", 3034, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_current_l3_a", "Corrente fase 3", "input", 3035, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_voltage_ab_v", "Tensione concatenata AB", "input", 3038, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_bc_v", "Tensione concatenata BC", "input", 3039, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_ca_v", "Tensione concatenata CA", "input", 3040, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("daily_energy_kwh", "Energia giornaliera", "input", 3049, 2, "uint32", scale=0.1, unit="kWh", section="Energia", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_kwh", "Energia totale", "input", 3051, 2, "uint32", scale=0.1, unit="kWh", section="Energia", summary_metric="total_energy_kwh"),
        telemetry_point("total_pv_energy_kwh", "Energia FV totale", "input", 3053, 2, "uint32", scale=0.1, unit="kWh", section="Energia"),
        telemetry_point("temperature_c", "Temperatura inverter", "input", 3093, 1, "int16", scale=0.1, unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("ipm_temperature_c", "Temperatura IPM", "input", 3094, 1, "int16", scale=0.1, unit="C", section="Termico"),
        telemetry_point("boost_temperature_c", "Temperatura boost", "input", 3095, 1, "int16", scale=0.1, unit="C", section="Termico"),
        telemetry_point("active_power_percent", "Potenza attiva percentuale", "input", 3101, 1, "uint16", unit="%", section="Potenza"),
        telemetry_point("fault_main_code", "Codice guasto principale", "input", 3105, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("warning_main_code", "Codice warning principale", "input", 3106, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("fault_sub_code", "Sottocodice guasto", "input", 3107, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("warning_sub_code", "Sottocodice warning", "input", 3108, 1, "uint16", section="Stato e allarmi"),
        *build_control_readback(),
    ]


def build_storage_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("storage_work_mode", "Modalita sistema accumulo", "input", 1000, 1, "uint16", section="Accumulo", optional_block=True),
        telemetry_point("battery_discharge_power_kw", "Potenza scarica batteria", "input", 1009, 2, "uint32", scale=0.0001, unit="kW", section="Accumulo", optional_block=True),
        telemetry_point("battery_charge_power_kw", "Potenza carica batteria", "input", 1011, 2, "uint32", scale=0.0001, unit="kW", section="Accumulo", optional_block=True),
        telemetry_point("battery_voltage_v", "Tensione batteria", "input", 1013, 1, "uint16", scale=0.1, unit="V", section="Accumulo", optional_block=True),
        telemetry_point("battery_soc_pct", "SOC batteria", "input", 1014, 1, "uint16", unit="%", section="Accumulo", optional_block=True),
        telemetry_point("power_to_user_kw", "Potenza verso utenza", "input", 1021, 2, "uint32", scale=0.0001, unit="kW", section="Accumulo", optional_block=True),
        telemetry_point("power_to_grid_kw", "Potenza verso rete", "input", 1029, 2, "uint32", scale=0.0001, unit="kW", section="Accumulo", optional_block=True),
        telemetry_point("local_load_power_kw", "Potenza carico locale", "input", 1037, 2, "uint32", scale=0.0001, unit="kW", section="Accumulo", optional_block=True),
        telemetry_point("battery_temperature_c", "Temperatura batteria", "input", 1040, 1, "int16", scale=0.1, unit="C", section="Accumulo", optional_block=True),
    ]


def build_spa_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("status", "Stato inverter", "input", 2000, 1, "uint16", section="Stato e allarmi", summary_metric="status", heartbeat=True),
        telemetry_point("active_power_kw", "Potenza attiva in uscita", "input", 2035, 2, "uint32", scale=0.0001, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("mains_frequency_hz", "Frequenza rete", "input", 2037, 1, "uint16", scale=0.01, unit="Hz", section="Rete AC"),
        telemetry_point("mains_voltage_v", "Tensione fase 1", "input", 2038, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("ac_current_a", "Corrente fase 1", "input", 2039, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("daily_energy_kwh", "Energia giornaliera", "input", 2053, 2, "uint32", scale=0.1, unit="kWh", section="Energia", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_kwh", "Energia totale", "input", 2055, 2, "uint32", scale=0.1, unit="kWh", section="Energia", summary_metric="total_energy_kwh"),
        telemetry_point("temperature_c", "Temperatura inverter", "input", 2093, 1, "int16", scale=0.1, unit="C", section="Termico", summary_metric="temperature_c"),
        *build_storage_telemetry(),
        *build_control_readback(),
    ]


def build_defaults(protocol: str, test_register: int) -> dict[str, str | int | float | bool]:
    common: dict[str, str | int | float | bool] = {
        "timeout_seconds": 2,
        "retries": 1,
        "poll_interval_seconds": 15,
        "heartbeat_interval_seconds": 2,
        "adaptive_communication": False,
        "inter_request_delay_ms": 1000,
        "test_register": test_register,
        "test_count": 1,
        "test_function": "input",
        "max_registers_per_request": 125,
    }
    if protocol == "modbus_rtu":
        return {
            "port": "COM1",
            "slave_id": 1,
            "baud_rate": 9600,
            "parity": "N",
            "stop_bits": 1,
            "byte_size": 8,
            **common,
        }
    return {
        "host": "192.168.1.100",
        "port": 502,
        "unit_id": 1,
        **common,
    }


def build_growatt_models(protocol: str, transport: str) -> list[InverterModel]:
    if (protocol, transport) not in {
        ("modbus_rtu", "serial"),
        ("modbus_tcp", "tcp"),
    }:
        return []

    low_map = build_low_map_telemetry()
    high_map = build_high_map_telemetry()
    storage_map = build_storage_telemetry()
    commands = build_common_commands()
    profiles = [
        (
            GROWATT_MIN_MODEL,
            3000,
            high_map,
            "Mappa input 3000-3374; comprende varianti TL-XH con blocchi accumulo dipendenti dal firmware.",
        ),
        (
            GROWATT_TL3_MODEL,
            0,
            low_map,
            "Mappa input 0-249 per famiglie MAX, MID e MAC TL3-X.",
        ),
        (
            GROWATT_MAX_1500_MODEL,
            0,
            [*low_map, *build_pv_points(875, 8, first_index=9)],
            "Mappa input 0-249 e blocco aggiuntivo PV9-PV16 875-906.",
        ),
        (
            GROWATT_MOD_MODEL,
            3000,
            high_map,
            "Mappa input 3000-3249 per famiglia MOD TL3-XH.",
        ),
        (
            GROWATT_MIX_MODEL,
            0,
            [*low_map, *storage_map],
            "Mappa inverter 0-124 e blocco accumulo 1000-1124.",
        ),
        (
            GROWATT_SPA_MODEL,
            2000,
            build_spa_telemetry(),
            "Mappa inverter 2000-2124 e blocco accumulo 1000-1249.",
        ),
        (
            GROWATT_SPH_MODEL,
            0,
            [*low_map, *storage_map],
            "Mappa inverter 0-124 e blocchi accumulo 1000-1249.",
        ),
    ]

    return [
        InverterModel(
            brand=GROWATT_BRAND,
            model=model,
            protocol=protocol,
            transport=transport,
            defaults=build_defaults(protocol, test_register),
            features=[
                "manuale Growatt V1.24 verificato",
                "telemetria inverter",
                "controllo potenza attiva",
                "broadcast write",
                "intervallo minimo richieste rispettato",
            ],
            telemetry_points=telemetry,
            command_points=commands,
            catalog_meta=build_catalog_meta(
                notes=f"{notes} Comandi percentuali limitati al range operativo 0-100%; valore speciale raw 255 non esposto."
            ),
        )
        for model, test_register, telemetry, notes in profiles
    ]
