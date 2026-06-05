from app.models.inverter_model import InverterModel, InverterPoint


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
    visible: bool = True,
    summary_metric: str | None = None,
    enum_map: dict[int, str] | None = None,
    bitmask_labels: dict[int, str] | None = None,
    optional_block: bool = False,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {"section": section}
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map
    if bitmask_labels is not None:
        protocol_meta["bitmask_labels"] = bitmask_labels
    if optional_block:
        protocol_meta["optional_block"] = True

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
    enum_map: dict[int, str] | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {
        "section": section,
        "force_multi_write": True,
    }
    if min_value is not None:
        protocol_meta["min_value"] = min_value
    if max_value is not None:
        protocol_meta["max_value"] = max_value
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map

    return InverterPoint(
        key=key,
        label=label,
        kind="command",
        register_type="holding",
        address=address,
        length=2 if datatype in {"uint32", "int32"} else 1,
        datatype=datatype,
        scale=scale,
        unit=unit,
        writable=True,
        protocol_meta=protocol_meta,
    )


SCHNEIDER_CONEXT_XC_MODELS = [
    "Conext XC 540",
    "Conext XC 630",
    "Conext XC 680",
]

SCHNEIDER_XC_OPERATIONAL_MODE_MAP = {
    0x0000: "PV offline",
    0x0001: "PV reconnessione",
    0x0002: "PV online",
    0x0100: "CP offline",
    0x0101: "CP reconnessione",
    0x0102: "CP online",
    0x0200: "PVCQ offline",
    0x0201: "PVCQ reconnessione",
    0x0202: "PVCQ online",
}

SCHNEIDER_XC_SYSTEM_STATE_MAP = {
    0: "Initializing",
    1: "Disable",
    2: "Enable",
    3: "Service",
}

SCHNEIDER_XC_BAUD_RATE_MAP = {
    24: "4800",
    28: "9600",
    32: "19200",
    36: "38400",
    40: "57600",
}

SCHNEIDER_XC_PARAMETER_CONTROL_MAP = {
    1: "Panel control",
    2: "Modbus",
}

SCHNEIDER_XC_REMOTE_CONTROL_MAP = {
    0: "Remote start",
    1: "Remote shutdown",
}

SCHNEIDER_XC_PF_CONTROL_FUNCTION_MAP = {
    0: "Off",
    1: "P(F) type 1",
    2: "P(F) type 2",
}

SCHNEIDER_XC_POWER_REFERENCE_SELECTION_MAP = {
    0: "Modbus",
    1: "Analog input",
}

SCHNEIDER_XC_VOLTAGE_SUPPORT_FUNCTION_MAP = {
    0: "Off",
    1: "On",
}

SCHNEIDER_XC_VAC_REGULATION_MAP = {
    0: "Off",
    1: "Q(V)",
    2: "Phi(P)",
}

SCHNEIDER_XC_RECONNECT_POWER_RAMP_TYPE_MAP = {
    0: "Grid error",
    1: "Global",
}

SCHNEIDER_XC_DEVICE_ACTIVE_STATUS_BITS = {
    0: "AC breaker closed",
    1: "DC switch closed",
    2: "Fan in test mode",
}

SCHNEIDER_XC_LOGGER_STATE_BITS = {
    0: "Board not ready",
    1: "Log mode active",
    2: "Read mode active",
    3: "Config mode active",
    8: "RTC battery low",
    9: "NVRAM CRC error",
    10: "RTC error",
}


def build_schneider_conext_xc_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("product_model_designation", "Modello prodotto", 0x0001, 9, "ascii_string", section="Identificazione"),
        telemetry_point("finished_goods_assembly_number", "Codice FGA", 0x000A, 10, "ascii_string", section="Identificazione"),
        telemetry_point("product_serial_number", "Seriale prodotto", 0x0014, 10, "ascii_string", section="Identificazione"),
        telemetry_point("total_energy_kwh", "Energia totale", 0x0802, 2, "uint32", scale=0.1, unit="kWh", section="Contatori", summary_metric="total_energy_kwh"),
        telemetry_point("daily_energy_kwh", "Energia oggi", 0x0804, 2, "uint32", unit="kWh", section="Contatori", summary_metric="daily_energy_kwh"),
        telemetry_point("operation_hours_h", "Ore di funzionamento", 0x081E, 2, "uint32", unit="h", section="Contatori"),
        telemetry_point("status", "Stato operativo", 0x1700, 1, "uint16", section="Stato e allarmi", summary_metric="status", enum_map=SCHNEIDER_XC_OPERATIONAL_MODE_MAP),
        telemetry_point("temperature_power_board_c", "Temperatura power board", 0x1701, 1, "int16", scale=0.1, unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("temperature_heatsink_1_c", "Temperatura heatsink 1", 0x1702, 1, "int16", scale=0.1, unit="C", section="Termico"),
        telemetry_point("temperature_heatsink_2_c", "Temperatura heatsink 2", 0x1703, 1, "int16", scale=0.1, unit="C", section="Termico"),
        telemetry_point("temperature_heatsink_3_c", "Temperatura heatsink 3", 0x1704, 1, "int16", scale=0.1, unit="C", section="Termico"),
        telemetry_point("grid_current_total_a", "Corrente rete totale", 0x1705, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("apparent_power_kva", "Potenza apparente", 0x17F1, 1, "uint16", scale=0.1, unit="kVA", section="Potenza"),
        telemetry_point("reactive_power_kvar", "Potenza reattiva", 0x17F4, 1, "int16", scale=0.1, unit="kVAr", section="Potenza"),
        telemetry_point("grid_voltage_v12_v", "Tensione rete V12", 0x17F8, 1, "int16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_v23_v", "Tensione rete V23", 0x17F9, 1, "int16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_v31_v", "Tensione rete V31", 0x17FA, 1, "int16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_current_line_1_a", "Corrente rete linea 1", 0x17FB, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_current_line_2_a", "Corrente rete linea 2", 0x17FC, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_current_line_3_a", "Corrente rete linea 3", 0x17FD, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("active_power_kw", "Potenza attiva", 0x17FE, 1, "int16", scale=0.1, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("pv_voltage_v", "Tensione FV", 0x17FF, 1, "int16", scale=0.1, unit="V", section="Ingresso FV"),
        telemetry_point("pv_current_a", "Corrente FV", 0x1800, 1, "int16", scale=0.1, unit="A", section="Ingresso FV"),
        telemetry_point("pv_power_kw", "Potenza FV", 0x1801, 1, "int16", scale=0.1, unit="kW", section="Ingresso FV"),
        telemetry_point("grid_frequency_hz", "Frequenza rete", 0x1802, 1, "int16", scale=0.1, unit="Hz", section="Rete AC"),
        telemetry_point("grid_frequency_high_resolution_hz", "Frequenza rete alta risoluzione", 0x1803, 1, "int16", scale=0.01, unit="Hz", section="Rete AC", optional_block=True),
        telemetry_point("dc_voltage_v", "Tensione DC", 0x180D, 1, "int16", scale=0.1, unit="V", section="Ingresso FV"),
        telemetry_point("thermal_loading_pct", "Carico termico", 0x180E, 1, "uint16", scale=0.1, unit="%", section="Termico"),
        telemetry_point("phase_a_frequency_hz", "Frequenza fase A", 0x1818, 1, "uint16", scale=0.1, unit="Hz", section="Rete AC"),
        telemetry_point("phase_b_frequency_hz", "Frequenza fase B", 0x1819, 1, "uint16", scale=0.1, unit="Hz", section="Rete AC"),
        telemetry_point("phase_c_frequency_hz", "Frequenza fase C", 0x181A, 1, "uint16", scale=0.1, unit="Hz", section="Rete AC"),
        telemetry_point("phase_a_real_power_kw", "Potenza attiva fase A", 0x181B, 1, "int16", scale=0.1, unit="kW", section="Potenza"),
        telemetry_point("phase_b_real_power_kw", "Potenza attiva fase B", 0x181C, 1, "int16", scale=0.1, unit="kW", section="Potenza"),
        telemetry_point("phase_c_real_power_kw", "Potenza attiva fase C", 0x181D, 1, "int16", scale=0.1, unit="kW", section="Potenza"),
        telemetry_point("phase_a_reactive_power_kvar", "Potenza reattiva fase A", 0x181E, 1, "int16", scale=0.1, unit="kVAr", section="Potenza"),
        telemetry_point("phase_b_reactive_power_kvar", "Potenza reattiva fase B", 0x181F, 1, "int16", scale=0.1, unit="kVAr", section="Potenza"),
        telemetry_point("phase_c_reactive_power_kvar", "Potenza reattiva fase C", 0x1820, 1, "int16", scale=0.1, unit="kVAr", section="Potenza"),
        telemetry_point("phase_a_apparent_power_kva", "Potenza apparente fase A", 0x1821, 1, "uint16", scale=0.1, unit="kVA", section="Potenza"),
        telemetry_point("phase_b_apparent_power_kva", "Potenza apparente fase B", 0x1822, 1, "uint16", scale=0.1, unit="kVA", section="Potenza"),
        telemetry_point("phase_c_apparent_power_kva", "Potenza apparente fase C", 0x1823, 1, "uint16", scale=0.1, unit="kVA", section="Potenza"),
        telemetry_point("event_code", "Event code", 0x1826, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("system_state", "Stato sistema", 0x1827, 1, "uint16", section="Stato e allarmi", enum_map=SCHNEIDER_XC_SYSTEM_STATE_MAP),
        telemetry_point("alarm_code", "Alarm code", 0x1828, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("disconnect_profile", "Disconnect profile", 0x408E, 1, "uint16", section="Configurazione", optional_block=True),
        telemetry_point("p_analog_filter_time_s", "Filtro analogico P", 0x408F, 1, "uint16", scale=0.01, unit="s", section="Configurazione", optional_block=True),
        telemetry_point("q_analog_filter_time_s", "Filtro analogico Q", 0x4090, 1, "uint16", scale=0.01, unit="s", section="Configurazione", optional_block=True),
        telemetry_point("modbus_user_p_readout_kw", "Setpoint P Modbus", 0x4098, 1, "uint16", scale=0.1, unit="kW", section="Controllo potenza", optional_block=True),
        telemetry_point("modbus_user_q_readout_kvar", "Setpoint Q Modbus", 0x4099, 1, "uint16", scale=0.1, unit="kVAr", section="Controllo reattivo", optional_block=True),
        telemetry_point("data_log_records", "Record data log", 0x4700, 1, "uint16", section="Contatori"),
        telemetry_point("event_log_records", "Record event log", 0x4701, 1, "uint16", section="Contatori"),
        telemetry_point("fault_log_records", "Record service log", 0x4702, 1, "uint16", section="Contatori"),
        telemetry_point("logger_state", "Stato logger", 0x4706, 1, "uint16", section="Stato e allarmi", bitmask_labels=SCHNEIDER_XC_LOGGER_STATE_BITS),
        telemetry_point("rated_input_pv_current_a", "Corrente FV nominale", 0xF801, 1, "uint16", unit="A", section="Targa"),
        telemetry_point("maximum_input_pv_voltage_v", "Tensione FV massima", 0xF802, 1, "uint16", unit="V", section="Targa"),
        telemetry_point("max_tracking_voltage_v", "Tensione tracking massima", 0xF803, 1, "uint16", unit="V", section="Targa"),
        telemetry_point("min_tracking_voltage_v", "Tensione tracking minima", 0xF804, 1, "uint16", unit="V", section="Targa"),
        telemetry_point("max_pv_oc_voltage_v", "Tensione FV OC massima", 0xF805, 1, "uint16", unit="V", section="Targa"),
        telemetry_point("max_stc_pv_sc_current_a", "Corrente FV STC massima", 0xF806, 1, "uint16", unit="A", section="Targa"),
        telemetry_point("rated_apparent_power_kva", "Potenza apparente nominale", 0xF807, 1, "uint16", scale=0.1, unit="kVA", section="Targa"),
        telemetry_point("rated_power_unity_pf_kw", "Potenza nominale a PF unitario", 0xF808, 1, "int16", scale=0.1, unit="kW", section="Targa"),
        telemetry_point("min_input_pv_voltage_v", "Tensione FV minima", 0xF809, 1, "uint16", unit="V", section="Targa"),
        telemetry_point("nominal_line_to_line_voltage_v", "Tensione nominale L-L", 0xF80A, 1, "uint16", unit="V", section="Targa"),
        telemetry_point("nominal_line_current_a", "Corrente nominale linea", 0xF80B, 1, "uint16", unit="A", section="Targa"),
        telemetry_point("rated_reactive_power_kvar", "Potenza reattiva nominale", 0xF80C, 1, "int16", scale=0.1, unit="kVAr", section="Targa"),
        telemetry_point("modbus_unit_id", "Unit ID Modbus", 0x8003, 1, "uint16", section="Configurazione"),
        telemetry_point("modbus_baud_rate", "Baud rate Modbus", 0x8010, 1, "uint16", section="Configurazione", enum_map=SCHNEIDER_XC_BAUD_RATE_MAP),
        telemetry_point("utility_region", "Utility region", 0xFA1F, 1, "uint16", section="Configurazione"),
        telemetry_point("max_dc_operating_voltage_v", "Tensione DC operativa massima", 0xFB94, 1, "uint16", unit="V", section="Targa"),
        telemetry_point("vac_regulation_mode", "Regolazione VAC", 0xFB58, 1, "uint16", section="Controllo reattivo", enum_map=SCHNEIDER_XC_VAC_REGULATION_MAP),
        telemetry_point("power_ramp_rate_pct_per_min", "Velocita ramp power", 0xFB62, 1, "uint16", scale=0.1, unit="%/min", section="Controllo potenza"),
        telemetry_point("reconnect_start_delay_s", "Ritardo avvio riconnessione", 0xFB64, 1, "uint16", unit="s", section="Protezioni rete"),
        telemetry_point("reconnect_power_ramp_type", "Tipo ramp riconnessione", 0xFB65, 1, "uint16", section="Controllo potenza", enum_map=SCHNEIDER_XC_RECONNECT_POWER_RAMP_TYPE_MAP),
        telemetry_point("device_active_status", "Stato attivo dispositivo", 0xFB9F, 1, "uint16", section="Stato e allarmi", bitmask_labels=SCHNEIDER_XC_DEVICE_ACTIVE_STATUS_BITS),
        telemetry_point("fan_speed_v", "Velocita ventola", 0xFBDA, 1, "uint16", scale=0.1, unit="V", section="Termico"),
    ]


def build_schneider_conext_xc_commands() -> list[InverterPoint]:
    return [
        command_point("parameter_control_station", "Stazione controllo parametri", 0xE0E0, "uint16", section="Configurazione", min_value=1, max_value=2, enum_map=SCHNEIDER_XC_PARAMETER_CONTROL_MAP),
        command_point("commit_modbus_settings", "Commit impostazioni Modbus", 0xE0E1, "uint16", section="Configurazione", min_value=1, max_value=1),
        command_point("remote_disable_enable", "Remote disable o enable", 0xEFFE, "uint16", section="Controllo potenza", min_value=0, max_value=1, enum_map=SCHNEIDER_XC_REMOTE_CONTROL_MAP),
        command_point("modbus_unit_id_write", "Scrivi Unit ID Modbus", 0x8003, "uint16", section="Configurazione", min_value=1, max_value=247),
        command_point("modbus_baud_rate_write", "Scrivi baud rate Modbus", 0x8010, "uint16", section="Configurazione", min_value=24, max_value=40, enum_map=SCHNEIDER_XC_BAUD_RATE_MAP),
        command_point("user_active_power_limit_kw", "Limite potenza attiva", 0xFA19, "int16", scale=0.1, unit="kW", section="Controllo potenza", min_value=0, max_value=680.0),
        command_point("user_reactive_power_reference_kvar", "Riferimento potenza reattiva", 0xFA1B, "int16", scale=0.1, unit="kVAr", section="Controllo reattivo", min_value=-680.0, max_value=680.0),
        command_point("user_apparent_power_limit_kva", "Limite potenza apparente", 0xFA1D, "uint16", scale=0.1, unit="kVA", section="Controllo potenza", min_value=0, max_value=680.0),
        command_point("user_phase_current_limit_pct", "Limite corrente di fase", 0xFA1E, "uint16", unit="%", section="Controllo potenza", min_value=5, max_value=100),
        command_point("time_utc_write", "Imposta tempo UTC", 0xFA21, "int32", unit="s", section="Configurazione"),
        command_point("max_tracking_voltage_write_v", "Tracking voltage massima", 0xF803, "uint16", unit="V", section="Ingresso FV", min_value=600, max_value=800),
        command_point("min_tracking_voltage_write_v", "Tracking voltage minima", 0xF804, "uint16", unit="V", section="Ingresso FV", min_value=400, max_value=700),
        command_point("pf_control_function", "Funzione P(f)", 0xF9F6, "uint16", section="Controllo potenza", min_value=0, max_value=2, enum_map=SCHNEIDER_XC_PF_CONTROL_FUNCTION_MAP),
        command_point("phase_angle_reference_deg", "Riferimento angolo di fase", 0xF9FB, "int16", unit="deg", section="Controllo reattivo", min_value=-45, max_value=45),
        command_point("power_reference_selection", "Selezione riferimento potenza", 0xFA48, "uint16", section="Controllo potenza", min_value=0, max_value=1, enum_map=SCHNEIDER_XC_POWER_REFERENCE_SELECTION_MAP),
        command_point("voltage_support_function", "Funzione supporto tensione", 0xFA24, "uint16", section="Controllo reattivo", min_value=0, max_value=1, enum_map=SCHNEIDER_XC_VOLTAGE_SUPPORT_FUNCTION_MAP),
        command_point("vac_regulation_write", "Regolazione VAC", 0xFB58, "uint16", section="Controllo reattivo", min_value=0, max_value=2, enum_map=SCHNEIDER_XC_VAC_REGULATION_MAP),
        command_point("power_ramp_rate_pct_per_min", "Velocita ramp potenza", 0xFB62, "uint16", scale=0.1, unit="%/min", section="Controllo potenza", min_value=0.5, max_value=6000.0),
        command_point("reconnect_start_delay_write_s", "Ritardo avvio riconnessione", 0xFB64, "uint16", unit="s", section="Protezioni rete", min_value=0, max_value=3600),
        command_point("reconnect_power_ramp_type_write", "Tipo ramp riconnessione", 0xFB65, "uint16", section="Controllo potenza", min_value=0, max_value=1, enum_map=SCHNEIDER_XC_RECONNECT_POWER_RAMP_TYPE_MAP),
        command_point("software_reset", "Software reset", 0xFB9E, "uint16", section="Configurazione", min_value=1, max_value=1),
    ]


def build_schneider_conext_xc_models(protocol: str, transport: str) -> list[InverterModel]:
    if protocol == "modbus_rtu":
        defaults = {
            "port": "COM1",
            "slave_id": 247,
            "baud_rate": 19200,
            "parity": "E",
            "stop_bits": 1,
            "byte_size": 8,
            "timeout_seconds": 2,
            "retries": 1,
            "poll_interval_seconds": 15,
            "max_registers_per_request": 100,
            "test_register": 0x1700,
            "test_count": 1,
            "test_function": "holding",
        }
    else:
        defaults = {
            "host": "192.168.1.170",
            "port": 502,
            "unit_id": 247,
            "timeout_seconds": 2,
            "retries": 1,
            "poll_interval_seconds": 15,
            "max_registers_per_request": 100,
            "test_register": 0x1700,
            "test_count": 1,
            "test_function": "holding",
        }

    return [
        InverterModel(
            brand="Schneider",
            model=model,
            protocol=protocol,
            transport=transport,
            defaults=defaults,
            features=[
                "telemetria trifase conext xc",
                "monitoraggio utility scale",
                "stati operativi pv cp pvcq",
                "controllo potenza attiva e reattiva",
                "scritture via fc16",
                "contatori log e stato logger",
            ],
            telemetry_points=build_schneider_conext_xc_telemetry(),
            command_points=build_schneider_conext_xc_commands(),
        )
        for model in SCHNEIDER_CONEXT_XC_MODELS
    ]
