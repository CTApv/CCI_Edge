from app.models.inverter_model import InverterModel, InverterPoint


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
    visible: bool = True,
    scale_factor_key: str | None = None,
    protocol_meta: dict[str, object] | None = None,
) -> InverterPoint:
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
        scale_factor_key=scale_factor_key,
        protocol_meta=protocol_meta or {},
    )


def command_point(
    key: str,
    label: str,
    register_type: str,
    address: int,
    length: int,
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
        register_type=register_type,
        address=address,
        length=length,
        datatype=datatype,
        scale=scale,
        unit=unit,
        writable=True,
        protocol_meta=protocol_meta or {},
    )


HUAWEI_STATE_1_BITS = {
    0: "Standby",
    1: "Connesso alla rete",
    2: "Connesso alla rete normalmente",
    3: "Derating per power rationing",
    4: "Derating per cause interne",
    5: "Arresto normale",
    6: "Arresto per guasto",
    7: "Arresto per power rationing",
    8: "Shutdown",
    9: "Spot check",
}

HUAWEI_STATE_2_BITS = {
    0: "Lock status sbloccato",
    1: "Connessione FV presente",
    2: "DSP data collection attiva",
}

HUAWEI_STATE_3_BITS = {
    0: "Off-grid",
    1: "Interruttore off-grid attivo",
}

HUAWEI_DEVICE_STATUS_MAP = {
    0x0000: "Standby: inizializzazione",
    0x0001: "Standby: test isolamento",
    0x0002: "Standby: test irraggiamento",
    0x0003: "Standby: test rete",
    0x0100: "Avvio",
    0x0200: "On-grid",
    0x0201: "On-grid limitato",
    0x0202: "On-grid con self-derating",
    0x0203: "Off-grid in esecuzione",
    0x0300: "Shutdown per guasto",
    0x0301: "Shutdown per comando",
    0x0302: "Shutdown per OVGR",
    0x0303: "Shutdown per comunicazione persa",
    0x0304: "Shutdown per power limit",
    0x0305: "Shutdown: avvio manuale richiesto",
    0x0306: "Shutdown: DC switch scollegati",
    0x0307: "Shutdown: rapid cutoff",
    0x0308: "Shutdown: input sotto potenza",
    0x0401: "Grid scheduling: cosphi-P",
    0x0402: "Grid scheduling: Q-U",
    0x0403: "Grid scheduling: PF-U",
    0x0404: "Grid scheduling: dry contact",
    0x0405: "Grid scheduling: Q-P",
    0x0500: "Spot-check pronto",
    0x0501: "Spot-check in corso",
    0x0600: "Inspection",
    0x0700: "AFCI self-check",
    0x0800: "I-V scanning",
    0x0900: "DC input detection",
    0x0A00: "Off-grid charging",
    0xA000: "Standby: no irradiation",
}

HUAWEI_ACTIVE_ADJUSTMENT_MODE_MAP = {
    0: "Percentuale",
    1: "Valore fisso",
}

HUAWEI_ACTIVE_ADJUSTMENT_COMMAND_MAP = {
    40120: "Limitazione attiva in kW",
    40125: "Limitazione attiva in percentuale",
    40126: "Limitazione attiva in W",
    42178: "Potenza attiva massima",
}

HUAWEI_REACTIVE_ADJUSTMENT_MODE_MAP = {
    0: "Power factor",
    1: "Valore assoluto",
    2: "Q/S",
    3: "Curva Q-U",
    4: "Curva cosphi-P/Pn",
    5: "Curva PF-U",
    6: "Curva Q-P",
}

HUAWEI_REACTIVE_ADJUSTMENT_COMMAND_MAP = {
    40122: "Compensazione PF",
    40123: "Compensazione Q/S",
    40129: "Compensazione notturna kVar",
    42809: "Reattiva notturna Q/S",
}

HUAWEI_BATTERY_STATUS_MAP = {
    0: "Offline",
    1: "Standby",
    2: "In funzione",
    3: "Guasto",
    4: "Sleep",
}

HUAWEI_BATTERY_MODE_MAP = {
    0: "Nessuno",
    1: "Carica/scarica forzata",
    2: "Time of Use LG",
    3: "Carica/scarica fissa",
    4: "Massimizza autoconsumo",
    5: "Fully fed to grid",
    6: "Time of Use LUNA2000",
    7: "Remote scheduling massimo autoconsumo",
    8: "Remote scheduling full Internet access",
    9: "Remote scheduling TOU",
    10: "AI energy management",
}

HUAWEI_METER_STATUS_MAP = {
    0: "Offline",
    1: "Normale",
}

HUAWEI_METER_TYPE_MAP = {
    0: "Monofase",
    1: "Trifase",
}

HUAWEI_METER_DETECTION_MAP = {
    0: "Identificazione in corso",
    1: "Modello corretto",
    2: "Modello differente",
}

HUAWEI_ENABLE_DISABLE_MAP = {
    0: "Disabilitato",
    1: "Abilitato",
}

HUAWEI_ACTIVE_CONTROL_MODE_MAP = {
    0: "Illimitato",
    1: "DI active scheduling",
    5: "Zero power grid connection",
    6: "Power-limited grid connection kW",
    7: "Power-limited grid connection percentuale",
}


def huawei_telemetry_point(
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
    display_format: str | None = None,
    display_prefix: str | None = None,
    display_width: int | None = None,
    optional_block: bool = False,
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
    if optional_block:
        protocol_meta["optional_block"] = True

    return telemetry_point(
        key=key,
        label=label,
        register_type="holding",
        address=address,
        length=length,
        datatype=datatype,
        scale=scale,
        unit=unit,
        visible=visible,
        protocol_meta=protocol_meta,
    )


def huawei_command_point(
    key: str,
    label: str,
    address: int,
    length: int,
    datatype: str,
    *,
    scale: float = 1.0,
    unit: str = "",
    section: str = "Controllo rete",
    min_value: float | None = None,
    max_value: float | None = None,
    step: float | None = None,
    enum_map: dict[int, str] | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {"section": section}
    if min_value is not None:
        protocol_meta["min_value"] = min_value
    if max_value is not None:
        protocol_meta["max_value"] = max_value
    if step is not None:
        protocol_meta["step"] = step
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map

    return command_point(
        key=key,
        label=label,
        register_type="holding",
        address=address,
        length=length,
        datatype=datatype,
        scale=scale,
        unit=unit,
        protocol_meta=protocol_meta,
    )


def build_huawei_core_telemetry() -> list[InverterPoint]:
    points = [
        huawei_telemetry_point("model_name", "Modello", 30000, 15, "ascii_string", section="Identificazione"),
        huawei_telemetry_point("serial_number", "Seriale", 30015, 10, "ascii_string", section="Identificazione"),
        huawei_telemetry_point("part_number", "Part number", 30025, 10, "ascii_string", section="Identificazione"),
        huawei_telemetry_point("model_id", "Model ID", 30070, 1, "uint16", section="Identificazione"),
        huawei_telemetry_point("pv_string_count", "Numero stringhe FV", 30071, 1, "uint16", section="Identificazione"),
        huawei_telemetry_point("mpp_tracker_count", "Numero MPPT", 30072, 1, "uint16", section="Identificazione"),
        huawei_telemetry_point("rated_power_kw", "Potenza nominale", 30073, 2, "uint32", scale=0.001, unit="kW", section="Targa"),
        huawei_telemetry_point("max_active_power_kw", "Potenza attiva massima", 30075, 2, "uint32", scale=0.001, unit="kW", section="Targa"),
        huawei_telemetry_point("max_apparent_power_kva", "Potenza apparente massima", 30077, 2, "uint32", scale=0.001, unit="kVA", section="Targa"),
        huawei_telemetry_point("max_reactive_power_feed_kvar", "Qmax immessa", 30079, 2, "int32", scale=0.001, unit="kvar", section="Targa"),
        huawei_telemetry_point("max_reactive_power_absorb_kvar", "Qmax assorbita", 30081, 2, "int32", scale=0.001, unit="kvar", section="Targa"),
        huawei_telemetry_point("state_1", "State 1", 32000, 1, "uint16", section="Stato", bitmask_labels=HUAWEI_STATE_1_BITS),
        huawei_telemetry_point("state_2", "State 2", 32002, 1, "uint16", section="Stato", bitmask_labels=HUAWEI_STATE_2_BITS),
        huawei_telemetry_point("state_3", "State 3", 32003, 2, "uint32", section="Stato", bitmask_labels=HUAWEI_STATE_3_BITS),
        huawei_telemetry_point("alarm_1", "Alarm 1", 32008, 1, "uint16", section="Allarmi", display_format="hex", display_width=4),
        huawei_telemetry_point("alarm_2", "Alarm 2", 32009, 1, "uint16", section="Allarmi", display_format="hex", display_width=4),
        huawei_telemetry_point("alarm_3", "Alarm 3", 32010, 1, "uint16", section="Allarmi", display_format="hex", display_width=4),
        huawei_telemetry_point("input_power_kw", "Potenza ingresso", 32064, 2, "int32", scale=0.001, unit="kW", section="Ingresso FV"),
        huawei_telemetry_point("line_voltage_ab_v", "Tensione AB", 32066, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        huawei_telemetry_point("line_voltage_bc_v", "Tensione BC", 32067, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        huawei_telemetry_point("line_voltage_ca_v", "Tensione CA", 32068, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        huawei_telemetry_point("phase_a_voltage_v", "Tensione fase A", 32069, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        huawei_telemetry_point("phase_b_voltage_v", "Tensione fase B", 32070, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        huawei_telemetry_point("phase_c_voltage_v", "Tensione fase C", 32071, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        huawei_telemetry_point("grid_current_a", "Corrente rete / fase A", 32072, 2, "int32", scale=0.001, unit="A", section="Rete AC"),
        huawei_telemetry_point("phase_b_current_a", "Corrente fase B", 32074, 2, "int32", scale=0.001, unit="A", section="Rete AC"),
        huawei_telemetry_point("phase_c_current_a", "Corrente fase C", 32076, 2, "int32", scale=0.001, unit="A", section="Rete AC"),
        huawei_telemetry_point("peak_active_power_today_kw", "Picco potenza odierno", 32078, 2, "int32", scale=0.001, unit="kW", section="Potenza"),
        huawei_telemetry_point("active_power_kw", "Potenza attiva", 32080, 2, "int32", scale=0.001, unit="kW", section="Potenza", summary_metric="power_kw"),
        huawei_telemetry_point("reactive_power_kvar", "Potenza reattiva", 32082, 2, "int32", scale=0.001, unit="kvar", section="Potenza"),
        huawei_telemetry_point("power_factor", "Fattore di potenza", 32084, 1, "int16", scale=0.001, section="Potenza"),
        huawei_telemetry_point("grid_frequency_hz", "Frequenza rete", 32085, 1, "uint16", scale=0.01, unit="Hz", section="Rete AC"),
        huawei_telemetry_point("efficiency_pct", "Efficienza", 32086, 1, "uint16", scale=0.01, unit="%", section="Termico"),
        huawei_telemetry_point("temperature_c", "Temperatura interna", 32087, 1, "int16", scale=0.1, unit="C", section="Termico", summary_metric="temperature_c"),
        huawei_telemetry_point("insulation_resistance_mohm", "Resistenza isolamento", 32088, 1, "uint16", scale=0.001, unit="MOhm", section="Stato"),
        huawei_telemetry_point("status", "Stato dispositivo", 32089, 1, "uint16", section="Stato", summary_metric="status", enum_map=HUAWEI_DEVICE_STATUS_MAP),
        huawei_telemetry_point("fault_code", "Fault code", 32090, 1, "uint16", section="Allarmi", display_format="hex", display_width=4),
        huawei_telemetry_point("startup_time_epoch", "Startup time", 32091, 2, "uint32", unit="epoch", section="Stato"),
        huawei_telemetry_point("shutdown_time_epoch", "Shutdown time", 32093, 2, "uint32", unit="epoch", section="Stato"),
        huawei_telemetry_point("total_energy_kwh", "Energia totale", 32106, 2, "uint32", scale=0.01, unit="kWh", section="Energia", summary_metric="total_energy_kwh"),
        huawei_telemetry_point("daily_energy_kwh", "Energia giornaliera", 32114, 2, "uint32", scale=0.01, unit="kWh", section="Energia", summary_metric="daily_energy_kwh"),
        huawei_telemetry_point("active_adjustment_mode", "Modalita regolazione attiva", 35300, 1, "uint16", section="Schedulazione rete", enum_map=HUAWEI_ACTIVE_ADJUSTMENT_MODE_MAP, optional_block=True),
        huawei_telemetry_point("active_adjustment_value", "Valore regolazione attiva", 35302, 2, "uint32", section="Schedulazione rete", optional_block=True),
        huawei_telemetry_point("active_adjustment_command", "Comando regolazione attiva", 35303, 1, "uint16", section="Schedulazione rete", enum_map=HUAWEI_ACTIVE_ADJUSTMENT_COMMAND_MAP, optional_block=True),
        huawei_telemetry_point("reactive_adjustment_mode", "Modalita regolazione reattiva", 35304, 1, "uint16", section="Schedulazione rete", enum_map=HUAWEI_REACTIVE_ADJUSTMENT_MODE_MAP, optional_block=True),
        huawei_telemetry_point("reactive_adjustment_value", "Valore regolazione reattiva", 35305, 2, "uint32", section="Schedulazione rete", optional_block=True),
        huawei_telemetry_point("reactive_adjustment_command", "Comando regolazione reattiva", 35307, 1, "uint16", section="Schedulazione rete", enum_map=HUAWEI_REACTIVE_ADJUSTMENT_COMMAND_MAP, optional_block=True),
        huawei_telemetry_point("optimizer_total_count", "Optimizer totali", 37200, 1, "uint16", section="Optimizer", optional_block=True),
        huawei_telemetry_point("optimizer_online_count", "Optimizer online", 37201, 1, "uint16", section="Optimizer", optional_block=True),
        huawei_telemetry_point("optimizer_feature_data", "Optimizer feature data", 37202, 1, "uint16", section="Optimizer", optional_block=True),
    ]

    for pv_index in range(1, 25):
        voltage_address = 32014 + (pv_index * 2)
        current_address = 32015 + (pv_index * 2)
        points.append(
            huawei_telemetry_point(
                f"pv_{pv_index}_voltage_v",
                f"PV{pv_index} tensione",
                voltage_address,
                1,
                "int16",
                scale=0.1,
                unit="V",
                section="Ingressi FV",
            )
        )
        points.append(
            huawei_telemetry_point(
                f"pv_{pv_index}_current_a",
                f"PV{pv_index} corrente",
                current_address,
                1,
                "int16",
                scale=0.01,
                unit="A",
                section="Ingressi FV",
            )
        )

    return points


def build_huawei_meter_telemetry() -> list[InverterPoint]:
    return [
        huawei_telemetry_point("meter_status", "Stato meter", 37100, 1, "uint16", section="Contatore rete", enum_map=HUAWEI_METER_STATUS_MAP, optional_block=True),
        huawei_telemetry_point("meter_phase_a_voltage_v", "Tensione A", 37101, 2, "int32", scale=0.1, unit="V", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_phase_b_voltage_v", "Tensione B", 37103, 2, "int32", scale=0.1, unit="V", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_phase_c_voltage_v", "Tensione C", 37105, 2, "int32", scale=0.1, unit="V", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_phase_a_current_a", "Corrente A", 37107, 2, "int32", scale=0.01, unit="A", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_phase_b_current_a", "Corrente B", 37109, 2, "int32", scale=0.01, unit="A", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_phase_c_current_a", "Corrente C", 37111, 2, "int32", scale=0.01, unit="A", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_active_power_w", "Potenza attiva meter", 37113, 2, "int32", unit="W", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_reactive_power_var", "Potenza reattiva meter", 37115, 2, "int32", unit="var", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_power_factor", "Power factor meter", 37117, 1, "int16", scale=0.001, section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_frequency_hz", "Frequenza meter", 37118, 1, "int16", scale=0.01, unit="Hz", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_positive_active_energy_kwh", "Energia attiva immessa", 37119, 2, "int32", scale=0.01, unit="kWh", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_reverse_active_energy_kwh", "Energia attiva prelevata", 37121, 2, "int32", scale=0.01, unit="kWh", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_reactive_energy_kvarh", "Energia reattiva", 37123, 2, "int32", scale=0.01, unit="kvarh", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_type", "Tipo meter", 37125, 1, "uint16", section="Contatore rete", enum_map=HUAWEI_METER_TYPE_MAP, optional_block=True),
        huawei_telemetry_point("meter_line_voltage_ab_v", "Tensione AB meter", 37126, 2, "int32", scale=0.1, unit="V", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_line_voltage_bc_v", "Tensione BC meter", 37128, 2, "int32", scale=0.1, unit="V", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_line_voltage_ca_v", "Tensione CA meter", 37130, 2, "int32", scale=0.1, unit="V", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_phase_a_active_power_w", "Potenza attiva A", 37132, 2, "int32", unit="W", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_phase_b_active_power_w", "Potenza attiva B", 37134, 2, "int32", unit="W", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_phase_c_active_power_w", "Potenza attiva C", 37136, 2, "int32", unit="W", section="Contatore rete", optional_block=True),
        huawei_telemetry_point("meter_model_detection", "Esito rilevamento modello", 37138, 1, "uint16", section="Contatore rete", enum_map=HUAWEI_METER_DETECTION_MAP, optional_block=True),
    ]


def build_huawei_storage_telemetry() -> list[InverterPoint]:
    return [
        huawei_telemetry_point("esu1_status", "ESU 1 stato", 37000, 1, "uint16", section="Accumulo unita 1", enum_map=HUAWEI_BATTERY_STATUS_MAP, optional_block=True),
        huawei_telemetry_point("esu1_power_w", "ESU 1 potenza carica/scarica", 37001, 2, "int32", unit="W", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_bus_voltage_v", "ESU 1 bus voltage", 37003, 1, "uint16", scale=0.1, unit="V", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_soc_pct", "ESU 1 SOC", 37004, 1, "uint16", scale=0.1, unit="%", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_working_mode", "ESU 1 working mode", 37006, 1, "uint16", section="Accumulo unita 1", enum_map=HUAWEI_BATTERY_MODE_MAP, optional_block=True),
        huawei_telemetry_point("esu1_rated_charge_power_w", "ESU 1 potenza carica nominale", 37007, 2, "uint32", unit="W", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_rated_discharge_power_w", "ESU 1 potenza scarica nominale", 37009, 2, "uint32", unit="W", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_fault_id", "ESU 1 fault ID", 37014, 1, "uint16", section="Accumulo unita 1", display_format="hex", display_width=4, optional_block=True),
        huawei_telemetry_point("esu1_daily_charge_kwh", "ESU 1 carica giornaliera", 37015, 2, "uint32", scale=0.01, unit="kWh", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_daily_discharge_kwh", "ESU 1 scarica giornaliera", 37017, 2, "uint32", scale=0.01, unit="kWh", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_bus_current_a", "ESU 1 bus current", 37021, 1, "int16", scale=0.1, unit="A", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_temperature_c", "ESU 1 temperatura", 37022, 1, "int16", scale=0.1, unit="C", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_remaining_time_min", "ESU 1 tempo residuo", 37025, 1, "uint16", unit="min", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_dcdc_version", "ESU 1 versione DCDC", 37026, 10, "ascii_string", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_bms_version", "ESU 1 versione BMS", 37036, 10, "ascii_string", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("storage_max_charge_power_w", "Accumulo potenza max carica", 37046, 2, "uint32", unit="W", section="Accumulo aggregato", optional_block=True),
        huawei_telemetry_point("storage_max_discharge_power_w", "Accumulo potenza max scarica", 37048, 2, "uint32", unit="W", section="Accumulo aggregato", optional_block=True),
        huawei_telemetry_point("esu1_serial_number", "ESU 1 seriale", 37052, 10, "ascii_string", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_total_charge_kwh", "ESU 1 carica totale", 37066, 2, "uint32", scale=0.01, unit="kWh", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu1_total_discharge_kwh", "ESU 1 scarica totale", 37068, 2, "uint32", scale=0.01, unit="kWh", section="Accumulo unita 1", optional_block=True),
        huawei_telemetry_point("esu2_serial_number", "ESU 2 seriale", 37700, 10, "ascii_string", section="Accumulo unita 2", optional_block=True),
        huawei_telemetry_point("esu2_soc_pct", "ESU 2 SOC", 37738, 1, "uint16", scale=0.1, unit="%", section="Accumulo unita 2", optional_block=True),
        huawei_telemetry_point("esu2_status", "ESU 2 stato", 37741, 1, "uint16", section="Accumulo unita 2", enum_map=HUAWEI_BATTERY_STATUS_MAP, optional_block=True),
        huawei_telemetry_point("esu2_power_w", "ESU 2 potenza carica/scarica", 37743, 2, "int32", unit="W", section="Accumulo unita 2", optional_block=True),
        huawei_telemetry_point("esu2_daily_charge_kwh", "ESU 2 carica giornaliera", 37746, 2, "uint32", scale=0.01, unit="kWh", section="Accumulo unita 2", optional_block=True),
        huawei_telemetry_point("esu2_daily_discharge_kwh", "ESU 2 scarica giornaliera", 37748, 2, "uint32", scale=0.01, unit="kWh", section="Accumulo unita 2", optional_block=True),
        huawei_telemetry_point("esu2_bus_voltage_v", "ESU 2 bus voltage", 37750, 1, "uint16", scale=0.1, unit="V", section="Accumulo unita 2", optional_block=True),
        huawei_telemetry_point("esu2_bus_current_a", "ESU 2 bus current", 37751, 1, "int16", scale=0.1, unit="A", section="Accumulo unita 2", optional_block=True),
        huawei_telemetry_point("esu2_temperature_c", "ESU 2 temperatura", 37752, 1, "int16", scale=0.1, unit="C", section="Accumulo unita 2", optional_block=True),
        huawei_telemetry_point("esu2_total_charge_kwh", "ESU 2 carica totale", 37753, 2, "uint32", scale=0.01, unit="kWh", section="Accumulo unita 2", optional_block=True),
        huawei_telemetry_point("esu2_total_discharge_kwh", "ESU 2 scarica totale", 37755, 2, "uint32", scale=0.01, unit="kWh", section="Accumulo unita 2", optional_block=True),
        huawei_telemetry_point("storage_rated_capacity_wh", "Capacita accumulo", 37758, 2, "uint32", unit="Wh", section="Accumulo aggregato", optional_block=True),
        huawei_telemetry_point("storage_soc_pct", "SOC accumulo", 37760, 1, "uint16", scale=0.1, unit="%", section="Accumulo aggregato", optional_block=True),
        huawei_telemetry_point("storage_status", "Stato accumulo", 37762, 1, "uint16", section="Accumulo aggregato", enum_map=HUAWEI_BATTERY_STATUS_MAP, optional_block=True),
        huawei_telemetry_point("storage_bus_voltage_v", "Bus voltage accumulo", 37763, 1, "uint16", scale=0.1, unit="V", section="Accumulo aggregato", optional_block=True),
        huawei_telemetry_point("storage_bus_current_a", "Bus current accumulo", 37764, 1, "int16", scale=0.1, unit="A", section="Accumulo aggregato", optional_block=True),
        huawei_telemetry_point("storage_power_w", "Potenza accumulo", 37765, 2, "int32", unit="W", section="Accumulo aggregato", optional_block=True),
        huawei_telemetry_point("storage_total_charge_kwh", "Carica totale accumulo", 37780, 2, "uint32", scale=0.01, unit="kWh", section="Accumulo aggregato", optional_block=True),
        huawei_telemetry_point("storage_total_discharge_kwh", "Scarica totale accumulo", 37782, 2, "uint32", scale=0.01, unit="kWh", section="Accumulo aggregato", optional_block=True),
        huawei_telemetry_point("storage_daily_charge_kwh", "Carica giornaliera accumulo", 37784, 2, "uint32", scale=0.01, unit="kWh", section="Accumulo aggregato", optional_block=True),
        huawei_telemetry_point("storage_daily_discharge_kwh", "Scarica giornaliera accumulo", 37786, 2, "uint32", scale=0.01, unit="kWh", section="Accumulo aggregato", optional_block=True),
        huawei_telemetry_point("esu2_software_version", "ESU 2 versione software", 37799, 15, "ascii_string", section="Accumulo unita 2", optional_block=True),
        huawei_telemetry_point("esu1_software_version", "ESU 1 versione software", 37814, 15, "ascii_string", section="Accumulo unita 1", optional_block=True),
    ]


def build_huawei_storage_pack_telemetry() -> list[InverterPoint]:
    pack_sections = [
        ("esu1", 1, 1, 38200, 38210, 38228, 38229, 38233, 38235, 38236, 38238, 38240, 38452, 38453),
        ("esu1", 1, 2, 38242, 38252, 38270, 38271, 38275, 38277, 38278, 38280, 38282, 38454, 38455),
        ("esu1", 1, 3, 38284, 38294, 38312, 38313, 38317, 38319, 38320, 38322, 38324, 38456, 38457),
        ("esu2", 2, 1, 38326, 38336, 38354, 38355, 38359, 38361, 38362, 38364, 38366, 38458, 38459),
        ("esu2", 2, 2, 38368, 38378, 38396, 38397, 38401, 38403, 38404, 38406, 38408, 38460, 38461),
        ("esu2", 2, 3, 38410, 38420, 38438, 38439, 38443, 38445, 38446, 38448, 38450, 38462, 38463),
    ]
    points: list[InverterPoint] = []

    for prefix, unit_index, pack_index, sn_addr, firmware_addr, status_addr, soc_addr, power_addr, voltage_addr, current_addr, charge_addr, discharge_addr, max_temp_addr, min_temp_addr in pack_sections:
        section = f"Accumulo pack ESU {unit_index}"
        label_prefix = f"ESU {unit_index} pack {pack_index}"
        point_prefix = f"{prefix}_pack_{pack_index}"
        points.extend(
            [
                huawei_telemetry_point(
                    f"{point_prefix}_serial_number",
                    f"{label_prefix} seriale",
                    sn_addr,
                    10,
                    "ascii_string",
                    section=section,
                    optional_block=True,
                ),
                huawei_telemetry_point(
                    f"{point_prefix}_firmware_version",
                    f"{label_prefix} firmware",
                    firmware_addr,
                    15,
                    "ascii_string",
                    section=section,
                    optional_block=True,
                ),
                huawei_telemetry_point(
                    f"{point_prefix}_status",
                    f"{label_prefix} stato",
                    status_addr,
                    1,
                    "uint16",
                    section=section,
                    enum_map=HUAWEI_BATTERY_STATUS_MAP,
                    optional_block=True,
                ),
                huawei_telemetry_point(
                    f"{point_prefix}_soc_pct",
                    f"{label_prefix} SOC",
                    soc_addr,
                    1,
                    "uint16",
                    scale=0.1,
                    unit="%",
                    section=section,
                    optional_block=True,
                ),
                huawei_telemetry_point(
                    f"{point_prefix}_power_kw",
                    f"{label_prefix} potenza carica/scarica",
                    power_addr,
                    2,
                    "int32",
                    scale=0.001,
                    unit="kW",
                    section=section,
                    optional_block=True,
                ),
                huawei_telemetry_point(
                    f"{point_prefix}_voltage_v",
                    f"{label_prefix} tensione",
                    voltage_addr,
                    1,
                    "uint16",
                    scale=0.1,
                    unit="V",
                    section=section,
                    optional_block=True,
                ),
                huawei_telemetry_point(
                    f"{point_prefix}_current_a",
                    f"{label_prefix} corrente",
                    current_addr,
                    1,
                    "int16",
                    scale=0.1,
                    unit="A",
                    section=section,
                    optional_block=True,
                ),
                huawei_telemetry_point(
                    f"{point_prefix}_total_charge_kwh",
                    f"{label_prefix} carica totale",
                    charge_addr,
                    2,
                    "uint32",
                    scale=0.01,
                    unit="kWh",
                    section=section,
                    optional_block=True,
                ),
                huawei_telemetry_point(
                    f"{point_prefix}_total_discharge_kwh",
                    f"{label_prefix} scarica totale",
                    discharge_addr,
                    2,
                    "uint32",
                    scale=0.01,
                    unit="kWh",
                    section=section,
                    optional_block=True,
                ),
                huawei_telemetry_point(
                    f"{point_prefix}_max_temperature_c",
                    f"{label_prefix} temperatura massima",
                    max_temp_addr,
                    1,
                    "int16",
                    scale=0.1,
                    unit="C",
                    section=section,
                    optional_block=True,
                ),
                huawei_telemetry_point(
                    f"{point_prefix}_min_temperature_c",
                    f"{label_prefix} temperatura minima",
                    min_temp_addr,
                    1,
                    "int16",
                    scale=0.1,
                    unit="C",
                    section=section,
                    optional_block=True,
                ),
            ]
        )

    return points


def build_huawei_commands() -> list[InverterPoint]:
    return [
        huawei_command_point("system_time_epoch", "System time", 40000, 2, "uint32", unit="epoch", step=1.0),
        huawei_command_point("q_u_curve_mode", "Modo curva Q-U", 40037, 1, "uint16", min_value=0.0, max_value=1.0, step=1.0),
        huawei_command_point("q_u_dispatch_trigger_power_pct", "Trigger potenza curva Q-U", 40038, 1, "uint16", unit="%", min_value=0.0, max_value=100.0, step=1.0),
        huawei_command_point("fixed_active_power_derated_kw", "Limitazione attiva fissa", 40120, 1, "uint16", scale=0.1, unit="kW", min_value=0.0, step=0.1),
        huawei_command_point("reactive_power_compensation_pf", "Compensazione PF", 40122, 1, "int16", scale=0.001, min_value=-1.0, max_value=1.0, step=0.001),
        huawei_command_point("reactive_power_compensation_qs", "Compensazione Q/S", 40123, 1, "int16", scale=0.001, min_value=-1.0, max_value=1.0, step=0.001),
        huawei_command_point("active_power_limit", "Limitazione potenza attiva", 40125, 1, "uint16", scale=0.1, unit="%", min_value=0.0, max_value=100.0, step=0.1),
        huawei_command_point("fixed_active_power_derated_w", "Limitazione attiva fissa W", 40126, 2, "uint32", unit="W", min_value=0.0, step=1.0),
        huawei_command_point("night_reactive_power_kvar", "Compensazione notturna", 40129, 2, "int32", scale=0.001, unit="kvar", step=0.001),
        huawei_command_point("reactive_power_adjustment_time_s", "Tempo regolazione reattiva", 40196, 1, "uint16", unit="s", min_value=1.0, max_value=120.0, step=1.0),
        huawei_command_point("grid_code", "Grid code", 42000, 1, "uint16", step=1.0),
        huawei_command_point("reactive_power_change_gradient_pct_s", "Gradiente potenza reattiva", 42015, 2, "uint32", scale=0.001, unit="%/s", min_value=0.1, max_value=1000.0, step=0.001),
        huawei_command_point("active_power_change_gradient_pct_s", "Gradiente potenza attiva", 42017, 2, "uint32", scale=0.001, unit="%/s", min_value=0.1, max_value=1000.0, step=0.001),
        huawei_command_point("schedule_instruction_valid_duration_s", "Durata validita comando", 42019, 2, "uint32", unit="s", min_value=0.0, max_value=86400.0, step=1.0),
        huawei_command_point("failsafe_active_power_limit_kw", "Failsafe active power limit", 42405, 2, "int32", scale=0.001, unit="kW", step=0.001),
        huawei_command_point("time_zone_minutes", "Timezone", 43006, 1, "int16", unit="min", min_value=-720.0, max_value=840.0, step=1.0),
        huawei_command_point("fast_power_scheduling", "Fast power scheduling", 45086, 1, "uint16", min_value=0.0, max_value=1.0, step=1.0, enum_map=HUAWEI_ENABLE_DISABLE_MAP),
        huawei_command_point("active_power_control_mode", "Modalita controllo potenza attiva", 47415, 1, "uint16", step=1.0, enum_map=HUAWEI_ACTIVE_CONTROL_MODE_MAP),
        huawei_command_point("maximum_feed_grid_power_kw", "Massima potenza immessa in rete", 47416, 2, "int32", scale=0.001, unit="kW", step=0.001),
        huawei_command_point("maximum_feed_grid_power_pct", "Massima potenza immessa in rete percentuale", 47418, 1, "int16", scale=0.1, unit="%", min_value=0.0, max_value=100.0, step=0.1),
    ]


def build_huawei_telemetry() -> list[InverterPoint]:
    return (
        build_huawei_core_telemetry()
        + build_huawei_meter_telemetry()
        + build_huawei_storage_telemetry()
        + build_huawei_storage_pack_telemetry()
    )


HUAWEI_MODELS_RAW = [
    "SUN2000-2KTL-L0",
    "SUN2000-2KTL-L1",
    "SUN2000-3KTL-CNL0",
    "SUN2000-3KTL-L0",
    "SUN2000-3KTL-L1",
    "SUN2000-3KTL-M0",
    "SUN2000-3KTL-M1",
    "SUN2000-3.68KTL-L10",
    "SUN2000-3.8KTL-USL0",
    "SUN2000-4KTL-CNL0",
    "SUN2000-4KTL-L0",
    "SUN2000-4KTL-L1",
    "SUN2000-4KTL-M0",
    "SUN2000-4KTL-M1",
    "SUN2000-4.6KTL-L1",
    "SUN2000-4.95KTL-JPL0",
    "SUN2000-4.95KTL-JPL1",
    "SUN2000-4.95KTL-NHL2",
    "SUN2000-5KTL-CNL0",
    "SUN2000-5KTL-L0",
    "SUN2000-5KTL-L1",
    "SUN2000-5KTL-M0",
    "SUN2000-5KTL-M1",
    "SUN2000-5KTL-USL0",
    "SUN2000-6KTL-CNL0",
    "SUN2000-6KTL-L1",
    "SUN2000-6KTL-M0",
    "SUN2000-6KTL-M1",
    "SUN2000-7.6KTL-USL0",
    "SUN2000-8KTL",
    "SUN2000-8KTL-M0",
    "SUN2000-8KTL-M1",
    "SUN2000-8KTL-M2",
    "SUN2000-9KTL-USL0",
    "SUN2000-10KTL",
    "SUN2000-10KTL-M0",
    "SUN2000-10KTL-M1",
    "SUN2000-10KTL-M2",
    "SUN2000-10KTL-USL0",
    "SUN2000-11.4KTL-USL0",
    "SUN2000-12KTL",
    "SUN2000-12KTL-M0",
    "SUN2000-12KTL-M1",
    "SUN2000-12KTL-M2",
    "SUN2000-15KTL",
    "SUN2000-15KTL-M0",
    "SUN2000-15KTL-M2",
    "SUN2000-15KTL-M3",
    "SUN2000-17KTL",
    "SUN2000-17KTL-M0",
    "SUN2000-17KTL-M2",
    "SUN2000-17KTL-M3",
    "SUN2000-20KTL",
    "SUN2000-20KTL-M0",
    "SUN2000-20KTL-M2",
    "SUN2000-20KTL-M3",
    "SUN2000-22KTL-US",
    "SUN2000-23KTL",
    "SUN2000-23KTL-M3",
    "SUN2000-24.5KTL",
    "SUN2000-24.5KTL-M3",
    "SUN2000-24.7KTL-JP",
    "SUN2000-25KTL-NAM3",
    "SUN2000-25KTL-US",
    "SUN2000-28KTL",
    "SUN2000-28KTL-M3",
    "SUN2000-29.9KTL",
    "SUN2000-29.9KTL-M3",
    "SUN2000-30KTL-A",
    "SUN2000-30KTL-M3",
    "SUN2000-30KTL-NAM3",
    "SUN2000-30KTL-US",
    "SUN2000-33KTL",
    "SUN2000-33KTL-A",
    "SUN2000-33KTL-E001",
    "SUN2000-33KTL-JP",
    "SUN2000-33KTL-NAM3",
    "SUN2000-33KTL-NH",
    "SUN2000-33KTL-NHM3",
    "SUN2000-33KTL-US",
    "SUN2000-36KTL",
    "SUN2000-36KTL-M3",
    "SUN2000-36KTL-NAM3",
    "SUN2000-36KTL-US",
    "SUN2000-40KTL",
    "SUN2000-40KTL-JP",
    "SUN2000-40KTL-M3",
    "SUN2000-40KTL-NAM3",
    "SUN2000-40KTL-NH",
    "SUN2000-40KTL-NHM3",
    "SUN2000-40KTL-US",
    "SUN2000-42KTL",
    "SUN2000-42KTL-M3",
    "SUN2000-43KTL-IN-C1",
    "SUN2000-43KTL-INM3",
    "SUN2000-44KTL-M3",
    "SUN2000-45KTL-US-HV-D0",
    "SUN2000-50KTL",
    "SUN2000-50KTL-C1",
    "SUN2000-50KTL-JPM0",
    "SUN2000-50KTL-JPM1",
    "SUN2000-50KTL-M0",
    "SUN2000-50KTL-M3",
    "SUN2000-55KTL-HV-D1",
    "SUN2000-55KTL-HV-D1-001",
    "SUN2000-55KTL-IN-HV-D1",
    "SUN2000-60KTL-HV-D1",
    "SUN2000-60KTL-HV-D1-001",
    "SUN2000-60KTL-M0",
    "SUN2000-63KTL-JPH0",
    "SUN2000-63KTL-JPM0",
    "SUN2000-65KTL-M0",
    "SUN2000-70KTL-C1",
    "SUN2000-70KTL-INM0",
    "SUN2000-75KTL-C1",
    "SUN2000-90KTL-H0",
    "SUN2000-90KTL-H1",
    "SUN2000-90KTL-H2",
    "SUN2000-95KTL-INH0",
    "SUN2000-95KTL-INH1",
    "SUN2000-100KTL-H0",
    "SUN2000-100KTL-H1",
    "SUN2000-100KTL-H2",
    "SUN2000-100KTL-INM0",
    "SUN2000-100KTL-M0",
    "SUN2000-100KTL-M1",
    "SUN2000-100KTL-USH0",
    "SUN2000-105KTL-H1",
    "SUN2000-110KTL-M0",
    "SUN2000-111KTL-NHM0",
    "SUN2000-125KTL-JPH0",
    "SUN2000-125KTL-M0",
    "SUN2000-168KTL-H1",
    "SUN2000-175KTL-H0",
    "SUN2000-185KTL-H1",
    "SUN2000-185KTL-INH0",
    "SUN2000-193KTL-H0",
    "SUN2000-196KTL-H0",
    "SUN2000-196KTL-H1",
    "SUN2000-196KTL-H3",
    "SUN2000-200KTL-H2",
    "SUN2000-215KTL-H0",
    "SUN2000L-2KTL",
    "SUN2000L-3KTL",
    "SUN2000L-3KTL-CN",
    "SUN2000L-3KTL-CN-4G",
    "SUN2000L-3.68KTL",
    "SUN2000L-4KTL",
    "SUN2000L-4KTL-CN",
    "SUN2000L-4KTL-CN-4G",
    "SUN2000L-4.125KTL-JP",
    "SUN2000L-4.6KTL",
    "SUN2000L-4.95KTL-JP",
    "SUN2000L-5KTL",
    "SUN2000L-5KTL-CN",
    "SUN2000L-5KTL-CN-4G",
    "SUN8000-500KTL",
]

HUAWEI_MODELS = list(dict.fromkeys(HUAWEI_MODELS_RAW))


def build_huawei_models(protocol: str, transport: str) -> list[InverterModel]:
    if protocol == "modbus_rtu":
        defaults = {
            "port": "COM1",
            "slave_id": 1,
            "baud_rate": 9600,
            "parity": "N",
            "stop_bits": 1,
            "byte_size": 8,
            "timeout_seconds": 2,
            "retries": 1,
            "poll_interval_seconds": 15,
            "test_register": 30070,
            "test_count": 1,
            "test_function": "holding",
        }
    else:
        defaults = {
            "host": "192.168.1.160",
            "port": 502,
            "unit_id": 1,
            "timeout_seconds": 2,
            "retries": 1,
            "poll_interval_seconds": 15,
            "test_register": 30070,
            "test_count": 1,
            "test_function": "holding",
        }

    return [
        InverterModel(
            brand="Huawei",
            model=model,
            protocol=protocol,
            transport=transport,
            defaults=defaults,
            features=[
                "telemetria inverter sun2000",
                "stati e fault huawei",
                "contatore rete opzionale",
                "accumulo opzionale",
                "comandi power scheduling",
            ],
            telemetry_points=build_huawei_telemetry(),
            command_points=build_huawei_commands(),
        )
        for model in HUAWEI_MODELS
    ]
