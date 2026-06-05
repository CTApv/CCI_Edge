from app.models.inverter_model import InverterModel, InverterPoint
from app.services.delta_rs485_service import DELTA_RS485_DRIVER

DELTA_BRAND = "Delta"
DELTA_PROTOCOL = "delta_rs485"

DELTA_OPERATING_STATE_MAP = {
    0: "Standby",
    1: "Sincronizzazione rete",
    2: "In produzione",
    3: "Produzione limitata",
    4: "Allarme o fault",
}


def telemetry_point(
    key: str,
    label: str,
    *,
    datatype: str = "uint16",
    scale: float = 1.0,
    unit: str = "",
    section: str,
    summary_metric: str | None = None,
    enum_map: dict[int, str] | None = None,
    display_format: str | None = None,
    display_width: int | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {
        "driver": DELTA_RS485_DRIVER,
        "section": section,
    }
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map
    if display_format is not None:
        protocol_meta["display_format"] = display_format
    if display_width is not None:
        protocol_meta["display_width"] = display_width

    return InverterPoint(
        key=key,
        label=label,
        kind="telemetry",
        register_type="delta",
        address=0,
        length=1,
        datatype=datatype,
        scale=scale,
        unit=unit,
        protocol_meta=protocol_meta,
    )


def command_point(
    key: str,
    label: str,
    *,
    datatype: str,
    section: str,
    unit: str = "",
    min_value: float | None = None,
    max_value: float | None = None,
    step: float | None = None,
    command_code: int,
    subcommand: int,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {
        "driver": DELTA_RS485_DRIVER,
        "section": section,
        "command_code": command_code,
        "subcommand": subcommand,
    }
    if min_value is not None:
        protocol_meta["min_value"] = min_value
    if max_value is not None:
        protocol_meta["max_value"] = max_value
    if step is not None:
        protocol_meta["step"] = step

    return InverterPoint(
        key=key,
        label=label,
        kind="command",
        register_type="delta",
        address=command_code,
        length=1,
        datatype=datatype,
        unit=unit,
        writable=True,
        protocol_meta=protocol_meta,
    )


DELTA_5000_MODELS = [
    "EOE46010001 PSU SOLAR INVERTER 5000W [SI5000]",
    "EOE46010007 PSU SOLAR INVERTER 5000W DE TS",
    "EOE46010008 PSU SOLAR INVERTER 5000W ES TS",
    "EOE46010009 PSU SOLAR INVERTER 5000W DE DES",
    "EOE46010010 PSU SOLAR INVERTER 5000W ES DES",
    "EOE46010015 PSU SOLAR INVERTER 5000W GR DES",
    "EOE46010016 PSU SOLAR INVERTER 5000W IT DES",
    "EOE46010017 PSU SOLAR INVERTER 5000W IT GAV",
    "EOE46010018 PSU SOLAR INVERTER 5000W IT TS",
    "EOE46010142 PSU SOLAR INVERTER 5000W PT DES",
    "EOE46010144 PSU SOLAR INVERTER 5000W CZ DES",
    "EOE46010146 PSU SOLAR INVERTER 5000W ES GAV",
    "EOE46010147 PSU SOLAR INVERTER 5000W IT GAI",
    "EOE46010175 PSU SOLAR INVERTER 5000W US DES",
    "EOE46010177 PSU SOLAR INVERTER 5000W BE DES",
]

DELTA_3300_MODELS = [
    "EOE46010002 PSU SOLAR INVERTER 3300W DE TS",
    "EOE46010003 PSU SOLAR INVERTER 3300W ES TS",
    "EOE46010004 PSU SOLAR INVERTER 3300W DE DES",
    "EOE46010005 PSU SOLAR INVERTER 3300W ES DES",
    "EOE46010011 PSU SOLAR INVERTER 3300W IT DES",
    "EOE46010012 PSU SOLAR INVERTER 3300W IT GAV",
    "EOE46010013 PSU SOLAR INVERTER 3300W IT TS",
    "EOE46010014 PSU SOLAR INVERTER 3300W GR DES",
    "EOE46010019 PSU SOLAR INVERTER 3300W ES GAV",
    "EOE46010127 PSU SOLAR INVERTER 3300W IT GAI",
    "EOE46010129 PSU SOLAR INVERTER 3300W PT DES",
    "EOE46010130 PSU SOLAR INVERTER 3300W CZ DES",
    "EOE46010133 PSU SOLAR INVERTER 3300W TW DES",
    "EOE46010139 PSU SOLAR INVERTER 3300W BE DES",
    "EOE46010190 PSU SOLAR INVERTER 3300W EU DE",
]

DELTA_2500_MODELS = [
    "EOE45010004 PSU SOLAR INVERTER 2500W DE TS",
    "EOE45010005 PSU SOLAR INVERTER 2500W ES TS",
    "EOE45010006 PSU SOLAR INVERTER 2500W DE DES",
    "EOE45010007 PSU SOLAR INVERTER 2500W ES DES",
    "EOE45010008 PSU SOLAR INVERTER 2500W GR DES",
    "EOE45010009 PSU SOLAR INVERTER 2500W IT DES",
    "EOE45010010 PSU SOLAR INVERTER 2500W IT GAV",
    "EOE45010011 PSU SOLAR INVERTER 2500W IT TS",
    "EOE45010012 PSU SOLAR INVERTER 2500W US DES",
    "EOE45010014 PSU SOLAR INVERTER 2500W ES GAV",
    "EOE45010134 PSU SOLAR INVERTER 2500W TW DES",
    "EOE45010135 PSU SOLAR INVERTER 2500W PT DES",
    "EOE45010136 PSU SOLAR INVERTER 2500W CZ DES",
    "EOE45010137 PSU SOLAR INVERTER 2500W IT GAI",
    "EOE45010138 PSU SOLAR INVERTER 2500W BE DES",
    "EOE45010173 PSU SOLAR INVERTER 2500W US DES",
]


def build_delta_variant_1_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("family_model", "Famiglia inverter", datatype="ascii_string", section="Identificazione"),
        telemetry_point("identified_model_name", "Modello identificato", datatype="ascii_string", section="Identificazione"),
        telemetry_point("delta_variant", "Variante Delta", section="Identificazione"),
        telemetry_point("sap_part_number", "Part number SAP", datatype="ascii_string", section="Identificazione"),
        telemetry_point("sap_serial_number", "Seriale SAP", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_ac_control", "Versione AC control", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_dc_control", "Versione DC control", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_display", "Versione display", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_ens_control", "Versione ENS control", datatype="ascii_string", section="Identificazione"),
        telemetry_point("operating_state", "Stato operativo", section="Stato e allarmi", summary_metric="status", enum_map=DELTA_OPERATING_STATE_MAP),
        telemetry_point("alarm_status_raw", "Alarm status raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("status_dc_raw", "Status DC raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("limits_dc_raw", "Limits DC raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("status_ac_raw", "Status AC raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("limits_ac_raw", "Limits AC raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("warning_status_raw", "Warning status raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("dc_hardware_failure_raw", "DC hardware failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("ac_hardware_failure_raw", "AC hardware failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("ens_hardware_failure_raw", "ENS hardware failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("bulk_failure_raw", "Bulk failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("internal_communication_failure_raw", "Internal communication failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("ac_hardware_disturbance_raw", "AC hardware disturbance raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("active_power_w", "Potenza attiva", scale=0.001, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("daily_energy_wh", "Energia giornaliera", scale=0.001, unit="kWh", section="Contatori", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_decikwh", "Energia totale", scale=0.1, unit="kWh", section="Contatori", summary_metric="total_energy_kwh"),
        telemetry_point("runtime_hours", "Ore di funzionamento", unit="h", section="Contatori"),
        telemetry_point("runtime_minutes", "Minuti runtime corrente", unit="min", section="Contatori"),
        telemetry_point("ac_voltage_v", "Tensione AC", unit="V", section="Rete AC"),
        telemetry_point("ac_current_a", "Corrente AC", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("ac_frequency_hz", "Frequenza AC", scale=0.01, unit="Hz", section="Rete AC"),
        telemetry_point("dc_input_1_voltage_v", "Tensione DC ingresso 1", unit="V", section="Ingresso DC"),
        telemetry_point("dc_input_1_current_a", "Corrente DC ingresso 1", scale=0.1, unit="A", section="Ingresso DC"),
        telemetry_point("dc_input_1_isolation_kohm", "Isolamento ingresso 1", unit="kOhm", section="Ingresso DC"),
        telemetry_point("solar_input_mov_resistance_kohm", "MOV ingresso FV", unit="kOhm", section="Ingresso DC"),
        telemetry_point("dc_side_temperature_c", "Temperatura lato DC", unit="C", section="Termico"),
        telemetry_point("ac_side_temperature_c", "Temperatura lato AC", unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("variant_mismatch", "Mismatch variante profilo", section="Identificazione"),
    ]


def build_delta_variant_3_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("family_model", "Famiglia inverter", datatype="ascii_string", section="Identificazione"),
        telemetry_point("identified_model_name", "Modello identificato", datatype="ascii_string", section="Identificazione"),
        telemetry_point("delta_variant", "Variante Delta", section="Identificazione"),
        telemetry_point("sap_part_number", "Part number SAP", datatype="ascii_string", section="Identificazione"),
        telemetry_point("sap_serial_number", "Seriale SAP", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_ac_control", "Versione AC control", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_dc_control", "Versione DC control", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_display", "Versione display", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_ens_master", "Versione ENS master", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_ens_slave", "Versione ENS slave", datatype="ascii_string", section="Identificazione"),
        telemetry_point("operating_state", "Stato operativo", section="Stato e allarmi", summary_metric="status", enum_map=DELTA_OPERATING_STATE_MAP),
        telemetry_point("alarm_status_raw", "Alarm status raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("status_dc_raw", "Status DC raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("limits_dc_raw", "Limits DC raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("status_ac_raw", "Status AC raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("limits_ac_raw", "Limits AC raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("warning_status_raw", "Warning status raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("dc_hardware_failure_raw", "DC hardware failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("ac_hardware_failure_raw", "AC hardware failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("ens_hardware_failure_raw", "ENS hardware failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("bulk_failure_raw", "Bulk failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("internal_communication_failure_raw", "Internal communication failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("ac_hardware_disturbance_raw", "AC hardware disturbance raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("active_power_w", "Potenza attiva", scale=0.001, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("daily_energy_wh", "Energia giornaliera", scale=0.001, unit="kWh", section="Contatori", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_decikwh", "Energia totale", scale=0.1, unit="kWh", section="Contatori", summary_metric="total_energy_kwh"),
        telemetry_point("runtime_hours", "Ore di funzionamento", unit="h", section="Contatori"),
        telemetry_point("runtime_minutes", "Minuti runtime corrente", unit="min", section="Contatori"),
        telemetry_point("ac_voltage_v", "Tensione AC", unit="V", section="Rete AC"),
        telemetry_point("ac_current_a", "Corrente AC", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("ac_frequency_hz", "Frequenza AC", scale=0.01, unit="Hz", section="Rete AC"),
        telemetry_point("dc_input_1_voltage_v", "Tensione DC ingresso 1", unit="V", section="Ingresso DC"),
        telemetry_point("dc_input_1_current_a", "Corrente DC ingresso 1", scale=0.1, unit="A", section="Ingresso DC"),
        telemetry_point("dc_input_1_isolation_kohm", "Isolamento ingresso 1", unit="kOhm", section="Ingresso DC"),
        telemetry_point("solar_input_mov_resistance_kohm", "MOV ingresso FV", unit="kOhm", section="Ingresso DC"),
        telemetry_point("dc_side_temperature_c", "Temperatura lato DC", unit="C", section="Termico"),
        telemetry_point("ac_side_temperature_c", "Temperatura lato AC", unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("variant_mismatch", "Mismatch variante profilo", section="Identificazione"),
    ]


def build_delta_variant_4_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("family_model", "Famiglia inverter", datatype="ascii_string", section="Identificazione"),
        telemetry_point("identified_model_name", "Modello identificato", datatype="ascii_string", section="Identificazione"),
        telemetry_point("delta_variant", "Variante Delta", section="Identificazione"),
        telemetry_point("sap_part_number", "Part number SAP", datatype="ascii_string", section="Identificazione"),
        telemetry_point("sap_serial_number", "Seriale SAP", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_ac_control", "Versione AC control", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_dc_control", "Versione DC control", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_display", "Versione display", datatype="ascii_string", section="Identificazione"),
        telemetry_point("software_revision_ens_control", "Versione ENS control", datatype="ascii_string", section="Identificazione"),
        telemetry_point("operating_state", "Stato operativo", section="Stato e allarmi", summary_metric="status", enum_map=DELTA_OPERATING_STATE_MAP),
        telemetry_point("alarm_status_raw", "Alarm status raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("status_dc_raw", "Status DC raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("limits_dc_raw", "Limits DC raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("status_ac_raw", "Status AC raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("limits_ac_raw", "Limits AC raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("warning_status_raw", "Warning status raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("dc_hardware_failure_raw", "DC hardware failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("ac_hardware_failure_raw", "AC hardware failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("ens_hardware_failure_raw", "ENS hardware failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("bulk_failure_raw", "Bulk failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("internal_communication_failure_raw", "Internal communication failure raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("ac_hardware_disturbance_raw", "AC hardware disturbance raw", section="Stato e allarmi", display_format="hex", display_width=2),
        telemetry_point("active_power_w", "Potenza attiva", scale=0.001, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("daily_energy_wh", "Energia giornaliera", scale=0.001, unit="kWh", section="Contatori", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_decikwh", "Energia totale", scale=0.1, unit="kWh", section="Contatori", summary_metric="total_energy_kwh"),
        telemetry_point("runtime_hours", "Ore di funzionamento", unit="h", section="Contatori"),
        telemetry_point("runtime_minutes", "Minuti runtime corrente", unit="min", section="Contatori"),
        telemetry_point("ac_voltage_v", "Tensione AC", unit="V", section="Rete AC"),
        telemetry_point("ac_current_a", "Corrente AC", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("ac_frequency_hz", "Frequenza AC", scale=0.01, unit="Hz", section="Rete AC"),
        telemetry_point("dc_input_1_voltage_v", "Tensione DC ingresso 1", unit="V", section="Ingresso DC"),
        telemetry_point("dc_input_1_current_a", "Corrente DC ingresso 1", scale=0.1, unit="A", section="Ingresso DC"),
        telemetry_point("dc_input_1_isolation_kohm", "Isolamento ingresso 1", unit="kOhm", section="Ingresso DC"),
        telemetry_point("dc_input_2_voltage_v", "Tensione DC ingresso 2", unit="V", section="Ingresso DC"),
        telemetry_point("dc_input_2_current_a", "Corrente DC ingresso 2", scale=0.1, unit="A", section="Ingresso DC"),
        telemetry_point("dc_input_2_isolation_kohm", "Isolamento ingresso 2", unit="kOhm", section="Ingresso DC"),
        telemetry_point("solar_input_1_mov_resistance_kohm", "MOV ingresso FV 1", unit="kOhm", section="Ingresso DC"),
        telemetry_point("solar_input_2_mov_resistance_kohm", "MOV ingresso FV 2", unit="kOhm", section="Ingresso DC"),
        telemetry_point("dc_side_temperature_c", "Temperatura lato DC", unit="C", section="Termico"),
        telemetry_point("ac_side_temperature_c", "Temperatura lato AC", unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("variant_mismatch", "Mismatch variante profilo", section="Identificazione"),
    ]


def build_delta_commands() -> list[InverterPoint]:
    return [
        command_point(
            "active_power_limit",
            "Limitazione potenza attiva",
            datatype="uint8",
            section="Controllo potenza",
            unit="%",
            min_value=0,
            max_value=100,
            step=1,
            command_code=13,
            subcommand=136,
        ),
    ]


def build_delta_defaults(variant: int) -> dict[str, str | int | float | bool]:
    return {
        "port": "COM1",
        "address": 1,
        "baud_rate": 19200,
        "parity": "N",
        "stop_bits": 1,
        "byte_size": 8,
        "timeout_seconds": 1.0,
        "retries": 1,
        "poll_interval_seconds": 15,
        "inter_request_delay_ms": 10,
        "retry_delay_ms": 50,
        "delta_variant": variant,
    }


def build_delta_models() -> list[InverterModel]:
    models: list[InverterModel] = []
    variant_1_telemetry = build_delta_variant_1_telemetry()
    variant_3_telemetry = build_delta_variant_3_telemetry()
    variant_4_telemetry = build_delta_variant_4_telemetry()
    commands = build_delta_commands()

    for model_name in DELTA_2500_MODELS:
        models.append(
            InverterModel(
                brand=DELTA_BRAND,
                model=model_name,
                protocol=DELTA_PROTOCOL,
                transport="serial",
                defaults=build_delta_defaults(1),
                features=[
                    "protocollo rs485 proprietario delta",
                    "famiglia pubblica si 2500",
                    "telemetria potenza energia e stato",
                    "limitazione potenza attiva",
                ],
                telemetry_points=variant_1_telemetry,
                command_points=commands,
            )
        )

    for model_name in DELTA_3300_MODELS:
        models.append(
            InverterModel(
                brand=DELTA_BRAND,
                model=model_name,
                protocol=DELTA_PROTOCOL,
                transport="serial",
                defaults=build_delta_defaults(3),
                features=[
                    "protocollo rs485 proprietario delta",
                    "famiglia pubblica si 3300",
                    "telemetria potenza energia e stato",
                    "limitazione potenza attiva",
                ],
                telemetry_points=variant_3_telemetry,
                command_points=commands,
            )
        )

    for model_name in DELTA_5000_MODELS:
        models.append(
            InverterModel(
                brand=DELTA_BRAND,
                model=model_name,
                protocol=DELTA_PROTOCOL,
                transport="serial",
                defaults=build_delta_defaults(4),
                features=[
                    "protocollo rs485 proprietario delta",
                    "famiglia pubblica si 5000",
                    "telemetria potenza energia e stato",
                    "limitazione potenza attiva",
                ],
                telemetry_points=variant_4_telemetry,
                command_points=commands,
            )
        )

    return models
