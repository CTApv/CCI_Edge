from app.models.inverter_model import InverterModel, InverterPoint
from app.services.xantrex_modbus_service import XANTREX_GT_DRIVER


def telemetry_point(
    key: str,
    label: str,
    address: int,
    length: int,
    datatype: str,
    *,
    scale: float = 1.0,
    unit: str = "",
    visible: bool = True,
    protocol_meta: dict[str, object] | None = None,
) -> InverterPoint:
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
        protocol_meta=protocol_meta or {},
    )


def command_point(
    key: str,
    label: str,
    address: int,
    datatype: str,
    *,
    scale: float = 1.0,
    unit: str = "",
    protocol_meta: dict[str, object] | None = None,
) -> InverterPoint:
    return InverterPoint(
        key=key,
        label=label,
        kind="command",
        register_type="holding",
        address=address,
        length=1 if datatype in {"uint16", "int16"} else 2,
        datatype=datatype,
        scale=scale,
        unit=unit,
        writable=True,
        protocol_meta=protocol_meta or {},
    )


XANTREX_GT_MODELS = ["GT Series"]

XANTREX_DEVICE_STATE_MAP = {
    0: "Hibernate",
    1: "Power save",
    2: "Safe",
    3: "Operating",
    4: "Diagnostic",
    5: "Loader",
    265: "Quiet time",
    266: "Auto on",
    267: "Auto off",
    268: "Manual on",
    269: "Manual off",
    270: "Generator shutdown",
    271: "External shutdown",
    272: "AGS fault",
    273: "Suspend",
    274: "Not operating",
    769: "Bulk",
    770: "Absorption",
    771: "Overcharge",
    772: "Equalize",
    773: "Float",
    775: "Constant VI",
    785: "Charge",
    786: "Absorption exit pending",
    787: "Ground fault",
    1024: "Inverter",
    1025: "AC passthru",
    1027: "Load sense active",
    1029: "Load sense ready",
    1033: "Grid tied",
    1034: "Grid support",
    1035: "Generator support",
    1036: "Sell to grid",
    1037: "Load shaving",
    1280: "Screen saver",
    1281: "Screen active",
}

XANTREX_SYSTEM_STATE_BITS = {
    0: "Grid to AC load",
    1: "Generator to AC load",
    2: "Battery to generator",
    3: "Battery to grid",
    4: "Grid to battery",
    5: "Generator to battery",
    6: "PV to battery",
    7: "PV to grid",
    8: "Battery to AC load",
}

XANTREX_BIST_RESULT_BITS = {
    0: "GPIO error",
    1: "External RAM error",
    2: "External Flash error",
    3: "NVMEM error",
    4: "RTC error",
}

XANTREX_ACTIVE_FAULT_TYPE_MAP = {
    0: "Auto reset escalating",
    1: "Auto reset",
    2: "Manual fault",
}

XANTREX_LOGGED_FAULT_TYPE_MAP = {
    0: "Auto reset",
    1: "Manual warning",
}

XANTREX_ENABLE_DISABLE_MAP = {
    0: "Disabilitato",
    1: "Abilitato",
}

XANTREX_SYSTEM_CONTROL_MAP = {
    0: "Hibernate",
    1: "Power save",
    2: "Safe",
    3: "Operating",
    4: "Diagnostic",
    252: "Last mode",
}


def xantrex_telemetry_point(
    key: str,
    label: str,
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
    bitmask_labels: dict[int, str] | None = None,
    queue_kind: str | None = None,
    queue_field: str | None = None,
    queue_log_type: int | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {
        "driver": XANTREX_GT_DRIVER,
        "section": section,
    }
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map
    if bitmask_labels is not None:
        protocol_meta["bitmask_labels"] = bitmask_labels
    if queue_kind is not None:
        protocol_meta["queue_kind"] = queue_kind
    if queue_field is not None:
        protocol_meta["queue_field"] = queue_field
    if queue_log_type is not None:
        protocol_meta["queue_log_type"] = queue_log_type

    return telemetry_point(
        key=key,
        label=label,
        address=address,
        length=length,
        datatype=datatype,
        scale=scale,
        unit=unit,
        visible=visible,
        protocol_meta=protocol_meta,
    )


def xantrex_command_point(
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
    enum_map: dict[int, str] | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {
        "driver": XANTREX_GT_DRIVER,
        "section": section,
    }
    if min_value is not None:
        protocol_meta["min_value"] = min_value
    if max_value is not None:
        protocol_meta["max_value"] = max_value
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map

    return command_point(
        key=key,
        label=label,
        address=address,
        datatype=datatype,
        scale=scale,
        unit=unit,
        protocol_meta=protocol_meta,
    )


def build_xantrex_gt_telemetry() -> list[InverterPoint]:
    return [
        xantrex_telemetry_point("product_model_designation", "Modello prodotto", 0x0000, 10, "ascii_string", section="Identificazione"),
        xantrex_telemetry_point("fga_number", "Codice FGA", 0x000A, 10, "ascii_string", section="Identificazione"),
        xantrex_telemetry_point("serial_number", "Seriale", 0x0014, 10, "ascii_string", section="Identificazione"),
        xantrex_telemetry_point("software_part_number", "Part number software", 0x001E, 10, "ascii_string", section="Identificazione"),
        xantrex_telemetry_point("active_faults_count", "Fault attivi", 0x0080, 1, "uint16", section="Stato e allarmi"),
        xantrex_telemetry_point("device_state", "Stato dispositivo", 0x00CF, 1, "uint16", section="Stato e allarmi", summary_metric="status", enum_map=XANTREX_DEVICE_STATE_MAP),
        xantrex_telemetry_point("system_state", "Stato sistema", 0x00D0, 1, "uint16", section="Stato e allarmi", bitmask_labels=XANTREX_SYSTEM_STATE_BITS),
        xantrex_telemetry_point("pv_connection_id", "Connessione FV", 0x0200, 1, "uint16", section="Ingresso FV", visible=False),
        xantrex_telemetry_point("dc_input_voltage_v", "Tensione ingresso DC", 0x0201, 2, "uint32", scale=0.01, unit="V", section="Ingresso FV"),
        xantrex_telemetry_point("dc_input_current_a", "Corrente ingresso DC", 0x0203, 2, "uint32", scale=0.01, unit="A", section="Ingresso FV"),
        xantrex_telemetry_point("dc_input_power_kw", "Potenza ingresso DC", 0x0205, 2, "uint32", scale=0.001, unit="kW", section="Ingresso FV"),
        xantrex_telemetry_point("ac_output_connection_id", "Connessione uscita AC", 0x0700, 1, "uint16", section="Rete AC", visible=False),
        xantrex_telemetry_point("ac_output_voltage_v", "Tensione uscita AC", 0x0701, 2, "uint32", scale=0.01, unit="V", section="Rete AC"),
        xantrex_telemetry_point("ac_output_current_a", "Corrente uscita AC", 0x0703, 2, "uint32", scale=0.01, unit="A", section="Rete AC"),
        xantrex_telemetry_point("ac_output_frequency_hz", "Frequenza uscita AC", 0x0705, 1, "uint16", scale=0.1, unit="Hz", section="Rete AC"),
        xantrex_telemetry_point("active_power_kw", "Potenza attiva", 0x0706, 2, "uint32", scale=0.001, unit="kW", section="Potenza", summary_metric="power_kw"),
        xantrex_telemetry_point("daily_energy_kwh", "Energia giornaliera", 0x0804, 2, "int32", scale=0.1, unit="kWh", section="Contatori", summary_metric="daily_energy_kwh", queue_kind="energy_history", queue_field="energy", queue_log_type=4),
        xantrex_telemetry_point("daily_peak_power_kw", "Picco giornaliero", 0x0806, 2, "int32", scale=0.001, unit="kW", section="Contatori", queue_kind="energy_history", queue_field="peak_power", queue_log_type=4),
        xantrex_telemetry_point("daily_harvest_time_s", "Tempo produzione giornaliero", 0x0808, 2, "uint32", unit="s", section="Contatori", queue_kind="energy_history", queue_field="harvest_time", queue_log_type=4),
        xantrex_telemetry_point("total_energy_kwh", "Energia totale", 0x0804, 2, "int32", scale=0.1, unit="kWh", section="Contatori", summary_metric="total_energy_kwh", queue_kind="energy_history", queue_field="energy", queue_log_type=5),
        xantrex_telemetry_point("lifetime_peak_power_kw", "Picco lifetime", 0x0806, 2, "int32", scale=0.001, unit="kW", section="Contatori", queue_kind="energy_history", queue_field="peak_power", queue_log_type=5),
        xantrex_telemetry_point("lifetime_harvest_time_s", "Tempo produzione lifetime", 0x0808, 2, "uint32", unit="s", section="Contatori", queue_kind="energy_history", queue_field="harvest_time", queue_log_type=5),
        xantrex_telemetry_point("heat_sink_temperature_c", "Temperatura dissipatore", 0x0900, 1, "int16", scale=0.1, unit="C", section="Termico", summary_metric="temperature_c"),
        xantrex_telemetry_point("power_rating_kw", "Potenza nominale", 0x0C00, 2, "uint32", scale=0.001, unit="kW", section="Targa"),
        xantrex_telemetry_point("temperature_min_c", "Temperatura minima supportata", 0x0C02, 1, "int16", scale=0.1, unit="C", section="Targa"),
        xantrex_telemetry_point("temperature_max_c", "Temperatura massima supportata", 0x0C03, 1, "int16", scale=0.1, unit="C", section="Targa"),
        xantrex_telemetry_point("dc_voltage_min_v", "Min tensione DC", 0x0D00, 2, "uint32", scale=0.01, unit="V", section="Targa"),
        xantrex_telemetry_point("dc_voltage_max_v", "Max tensione DC", 0x0D02, 2, "uint32", scale=0.01, unit="V", section="Targa"),
        xantrex_telemetry_point("dc_current_min_a", "Min corrente DC", 0x0D04, 2, "uint32", scale=0.01, unit="A", section="Targa"),
        xantrex_telemetry_point("dc_current_max_a", "Max corrente DC", 0x0D06, 2, "uint32", scale=0.01, unit="A", section="Targa"),
        xantrex_telemetry_point("ac_voltage_min_v", "Min tensione AC", 0x0E00, 2, "uint32", scale=0.01, unit="V", section="Targa"),
        xantrex_telemetry_point("ac_voltage_max_v", "Max tensione AC", 0x0E02, 2, "uint32", scale=0.01, unit="V", section="Targa"),
        xantrex_telemetry_point("ac_current_min_a", "Min corrente AC", 0x0E04, 2, "uint32", scale=0.01, unit="A", section="Targa"),
        xantrex_telemetry_point("ac_current_max_a", "Max corrente AC", 0x0E06, 2, "uint32", scale=0.01, unit="A", section="Targa"),
        xantrex_telemetry_point("ac_frequency_min_hz", "Min frequenza AC", 0x0E08, 1, "uint16", scale=0.1, unit="Hz", section="Targa"),
        xantrex_telemetry_point("ac_frequency_max_hz", "Max frequenza AC", 0x0E09, 1, "uint16", scale=0.1, unit="Hz", section="Targa"),
        xantrex_telemetry_point("self_test_result", "Autotest", 0x0F00, 1, "uint16", section="Stato e allarmi", bitmask_labels=XANTREX_BIST_RESULT_BITS),
        xantrex_telemetry_point("logged_faults_count", "Fault storicizzati", 0x1000, 1, "uint16", section="Stato e allarmi"),
        xantrex_telemetry_point("active_fault_type", "Tipo fault attivo", 0x0082, 1, "uint16", section="Stato e allarmi", enum_map=XANTREX_ACTIVE_FAULT_TYPE_MAP, queue_kind="active_fault", queue_field="type"),
        xantrex_telemetry_point("active_fault_identifier", "ID fault attivo", 0x0083, 1, "uint16", section="Stato e allarmi", queue_kind="active_fault", queue_field="identifier"),
        xantrex_telemetry_point("active_fault_time", "Timestamp fault attivo", 0x0084, 2, "uint32", section="Stato e allarmi", queue_kind="active_fault", queue_field="time"),
        xantrex_telemetry_point("active_fault_text", "Descrizione fault attivo", 0x0086, 20, "ascii_string", section="Stato e allarmi", queue_kind="active_fault", queue_field="text"),
        xantrex_telemetry_point("logged_fault_type", "Tipo ultimo fault", 0x1002, 1, "uint16", section="Stato e allarmi", enum_map=XANTREX_LOGGED_FAULT_TYPE_MAP, queue_kind="fault_log", queue_field="type"),
        xantrex_telemetry_point("logged_fault_identifier", "ID ultimo fault", 0x1003, 1, "uint16", section="Stato e allarmi", queue_kind="fault_log", queue_field="identifier"),
        xantrex_telemetry_point("logged_fault_time", "Timestamp ultimo fault", 0x1004, 2, "uint32", section="Stato e allarmi", queue_kind="fault_log", queue_field="time"),
        xantrex_telemetry_point("logged_fault_text", "Descrizione ultimo fault", 0x1006, 20, "ascii_string", section="Stato e allarmi", queue_kind="fault_log", queue_field="text"),
        xantrex_telemetry_point("loader_version", "Versione loader", 0x1100, 10, "ascii_string", section="Identificazione"),
        xantrex_telemetry_point("application_version", "Versione applicazione", 0x110A, 10, "ascii_string", section="Identificazione"),
    ]


def build_xantrex_gt_commands() -> list[InverterPoint]:
    return [
        xantrex_command_point("system_control_command", "Comando sistema", 0xF001, "uint16", section="Controllo sistema", min_value=0, max_value=252, enum_map=XANTREX_SYSTEM_CONTROL_MAP),
        xantrex_command_point("inverter_enable", "Abilitazione inverter", 0xF201, "uint16", section="Controllo sistema", min_value=0, max_value=1, enum_map=XANTREX_ENABLE_DISABLE_MAP),
        xantrex_command_point("search_mode_enable", "Search mode", 0xF202, "uint16", section="Controllo sistema", min_value=0, max_value=1, enum_map=XANTREX_ENABLE_DISABLE_MAP),
        xantrex_command_point("grid_tie_enable", "Abilitazione grid-tie", 0xF203, "uint16", section="Controllo sistema", min_value=0, max_value=1, enum_map=XANTREX_ENABLE_DISABLE_MAP),
        xantrex_command_point("sell_enable", "Abilitazione vendita", 0xF204, "uint16", section="Controllo sistema", min_value=0, max_value=1, enum_map=XANTREX_ENABLE_DISABLE_MAP),
        xantrex_command_point("force_sell_enable", "Forza vendita", 0xF205, "uint16", section="Controllo sistema", min_value=0, max_value=1, enum_map=XANTREX_ENABLE_DISABLE_MAP),
    ]


def build_xantrex_gt_models(protocol: str, transport: str) -> list[InverterModel]:
    if protocol == "modbus_rtu":
        defaults = {
            "port": "COM1",
            "slave_id": 101,
            "baud_rate": 9600,
            "parity": "N",
            "stop_bits": 1,
            "byte_size": 8,
            "timeout_seconds": 1,
            "retries": 1,
            "poll_interval_seconds": 15,
            "retry_on_device_busy": True,
            "device_busy_retry_count": 10,
            "device_busy_retry_delay_ms": 500,
            "test_register": 0x00CF,
            "test_count": 1,
            "test_function": "holding",
        }
    else:
        defaults = {
            "host": "192.168.1.180",
            "port": 502,
            "unit_id": 101,
            "timeout_seconds": 1,
            "retries": 1,
            "poll_interval_seconds": 15,
            "retry_on_device_busy": True,
            "device_busy_retry_count": 10,
            "device_busy_retry_delay_ms": 500,
            "test_register": 0x00CF,
            "test_count": 1,
            "test_function": "holding",
        }

    return [
        InverterModel(
            brand="Xantrex",
            model=model,
            protocol=protocol,
            transport=transport,
            defaults=defaults,
            features=[
                "lettura via gateway/proxy xantrex",
                "stato inverter e fault queue",
                "storico energia giornaliero e lifetime",
                "controlli inverter base",
                "setpoint potenza attiva non disponibile",
            ],
            telemetry_points=build_xantrex_gt_telemetry(),
            command_points=build_xantrex_gt_commands(),
        )
        for model in XANTREX_GT_MODELS
    ]
