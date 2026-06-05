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


SCHNEIDER_CONEXT_CL_MODELS = [
    "Conext CL 20000E",
    "Conext CL 25000E",
]

SCHNEIDER_OPERATIONAL_MODE_MAP = {
    0x0002: "Riconnessione alla rete",
    0x0003: "Online e produzione",
    0x0015: "Nessun FV",
    0x0016: "Offline per servizi o errori",
    0x0017: "Derating",
}

SCHNEIDER_SUNSPEC_STATUS_MAP = {
    1: "Off",
    3: "Starting",
    4: "MPPT",
    5: "Throttled",
    7: "Fault",
}

SCHNEIDER_BAUD_RATE_MAP = {
    0: "9600",
    1: "19200",
    2: "38400",
    3: "57600",
    4: "115200",
}

SCHNEIDER_REMOTE_OPERATION_MAP = {
    0x0000: "Operazione normale",
    0x6B42: "Reset inverter",
    0x6B43: "Inverter offline",
    0x6B44: "Inverter online",
}

SCHNEIDER_REACTIVE_MODE_MAP = {
    0: "Disabilitato",
    1: "Cosphi fisso",
    2: "Cosphi in funzione di P",
    3: "kVAr fisso",
    4: "kVAr in funzione di U",
}

SCHNEIDER_INVERTER_MODE_MAP = {
    0x0000: "Grid Tie Mode",
    0x6B45: "Local Consumption Mode",
}

SCHNEIDER_RELAY_MODE_MAP = {
    0: "Disabilitato",
    1: "Fault o error o warning",
    2: "Power production",
    3: "Controllo carico esterno",
    4: "Controllo ventole esterne",
    5: "Tutti i service error warning",
}


def schneider_telemetry_point(
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
    scale_factor_key: str | None = None,
    summary_metric: str | None = None,
    enum_map: dict[int, str] | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {"section": section}
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map

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
        scale_factor_key=scale_factor_key,
        protocol_meta=protocol_meta,
    )


def schneider_command_point(
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
    protocol_meta: dict[str, object] = {"section": section}
    if min_value is not None:
        protocol_meta["min_value"] = min_value
    if max_value is not None:
        protocol_meta["max_value"] = max_value
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map

    return command_point(
        key=key,
        label=label,
        register_type="holding",
        address=address,
        length=2 if datatype in {"uint32", "int32"} else 1,
        datatype=datatype,
        scale=scale,
        unit=unit,
        protocol_meta=protocol_meta,
    )


def build_schneider_conext_cl_telemetry() -> list[InverterPoint]:
    return [
        schneider_telemetry_point("product_model_designation", "Modello prodotto", 0x0001, 9, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("product_serial_number", "Seriale prodotto", 0x0014, 10, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("inverter_model_designation", "Modello inverter", 0x0028, 10, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("bos_model_designation", "Modello BOS", 0x0032, 10, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("software_part_number_a", "Part number software A", 0x0082, 10, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("software_part_number_b", "Part number software B", 0x0096, 10, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("software_part_number_c", "Part number software C", 0x00AA, 10, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("software_name_a", "Nome software A", 0x0160, 10, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("software_name_b", "Nome software B", 0x016A, 10, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("software_name_c", "Nome software C", 0x0174, 10, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("build_number_a", "Build software A", 0x0200, 7, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("build_number_b", "Build software B", 0x0207, 7, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("build_number_c", "Build software C", 0x020E, 7, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("software_version_a", "Versione software A", 0x0340, 5, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("software_version_b", "Versione software B", 0x0345, 5, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("software_version_c", "Versione software C", 0x034A, 5, "ascii_string", section="Identificazione"),
        schneider_telemetry_point("total_energy_kwh", "Energia totale", 0x0802, 2, "uint32", scale=0.1, unit="kWh", section="Contatori", summary_metric="total_energy_kwh"),
        schneider_telemetry_point("daily_energy_kwh", "Energia oggi", 0x0804, 2, "uint32", scale=0.1, unit="kWh", section="Contatori", summary_metric="daily_energy_kwh"),
        schneider_telemetry_point("energy_yesterday_kwh", "Energia ieri", 0x0806, 2, "uint32", scale=0.1, unit="kWh", section="Contatori"),
        schneider_telemetry_point("operation_hours_h", "Ore di funzionamento", 0x081E, 2, "uint32", unit="h", section="Contatori"),
        schneider_telemetry_point("status", "Stato operativo", 0x1700, 1, "uint16", section="Stato e allarmi", summary_metric="status", enum_map=SCHNEIDER_OPERATIONAL_MODE_MAP),
        schneider_telemetry_point("control_board_temperature_c", "Temperatura scheda controllo", 0x1701, 1, "int16", scale=0.1, unit="C", section="Termico", summary_metric="temperature_c"),
        schneider_telemetry_point("dc_module_12_temperature_c", "Temperatura modulo DC 12", 0x1702, 1, "int16", scale=0.1, unit="C", section="Termico"),
        schneider_telemetry_point("dc_module_34_temperature_c", "Temperatura modulo DC 34", 0x1703, 1, "int16", scale=0.1, unit="C", section="Termico"),
        schneider_telemetry_point("grid_current_total_a", "Corrente rete totale", 0x1705, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        schneider_telemetry_point("inverter_module_a_temperature_c", "Temperatura inverter modulo A", 0x1706, 1, "int16", scale=0.1, unit="C", section="Termico"),
        schneider_telemetry_point("inverter_module_b_temperature_c", "Temperatura inverter modulo B", 0x1707, 1, "int16", scale=0.1, unit="C", section="Termico"),
        schneider_telemetry_point("inverter_module_c_temperature_c", "Temperatura inverter modulo C", 0x1708, 1, "int16", scale=0.1, unit="C", section="Termico"),
        schneider_telemetry_point("phase_a_neutral_voltage_v", "Tensione fase A-N", 0x1709, 1, "int16", scale=0.1, unit="V", section="Rete AC"),
        schneider_telemetry_point("phase_b_neutral_voltage_v", "Tensione fase B-N", 0x170A, 1, "int16", scale=0.1, unit="V", section="Rete AC"),
        schneider_telemetry_point("phase_c_neutral_voltage_v", "Tensione fase C-N", 0x170B, 1, "int16", scale=0.1, unit="V", section="Rete AC"),
        schneider_telemetry_point("grid_apparent_power_kva", "Potenza apparente rete", 0x17F1, 1, "uint16", scale=0.1, unit="kVA", section="Potenza"),
        schneider_telemetry_point("grid_reactive_power_kvar", "Potenza reattiva rete", 0x17F4, 1, "int16", scale=0.1, unit="kVAr", section="Potenza"),
        schneider_telemetry_point("grid_voltage_v12_v", "Tensione rete V12", 0x17F8, 1, "int16", scale=0.1, unit="V", section="Rete AC"),
        schneider_telemetry_point("grid_voltage_v23_v", "Tensione rete V23", 0x17F9, 1, "int16", scale=0.1, unit="V", section="Rete AC"),
        schneider_telemetry_point("grid_voltage_v31_v", "Tensione rete V31", 0x17FA, 1, "int16", scale=0.1, unit="V", section="Rete AC"),
        schneider_telemetry_point("grid_current_l1_a", "Corrente rete L1", 0x17FB, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        schneider_telemetry_point("grid_current_l2_a", "Corrente rete L2", 0x17FC, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        schneider_telemetry_point("grid_current_l3_a", "Corrente rete L3", 0x17FD, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        schneider_telemetry_point("active_power_kw", "Potenza attiva", 0x17FE, 1, "int16", scale=0.1, unit="kW", section="Potenza", summary_metric="power_kw"),
        schneider_telemetry_point("pv1_voltage_v", "Tensione FV 1", 0x17FF, 1, "int16", scale=0.1, unit="V", section="Ingresso FV"),
        schneider_telemetry_point("pv1_current_a", "Corrente FV 1", 0x1800, 1, "int16", scale=0.1, unit="A", section="Ingresso FV"),
        schneider_telemetry_point("pv1_power_kw", "Potenza FV 1", 0x1801, 1, "int16", scale=0.1, unit="kW", section="Ingresso FV"),
        schneider_telemetry_point("grid_frequency_hz", "Frequenza rete", 0x1802, 1, "uint16", scale=0.1, unit="Hz", section="Rete AC"),
        schneider_telemetry_point("phase_a_power_kw", "Potenza fase A", 0x181B, 1, "int16", scale=0.1, unit="kW", section="Potenza"),
        schneider_telemetry_point("phase_b_power_kw", "Potenza fase B", 0x181C, 1, "int16", scale=0.1, unit="kW", section="Potenza"),
        schneider_telemetry_point("phase_c_power_kw", "Potenza fase C", 0x181D, 1, "int16", scale=0.1, unit="kW", section="Potenza"),
        schneider_telemetry_point("alarm_code", "Codice allarme attivo", 0x1828, 1, "uint16", section="Stato e allarmi"),
        schneider_telemetry_point("pv2_voltage_v", "Tensione FV 2", 0x1829, 1, "int16", scale=0.1, unit="V", section="Ingresso FV"),
        schneider_telemetry_point("pv2_current_a", "Corrente FV 2", 0x182A, 1, "int16", scale=0.1, unit="A", section="Ingresso FV"),
        schneider_telemetry_point("pv2_power_kw", "Potenza FV 2", 0x182F, 1, "int16", scale=0.1, unit="kW", section="Ingresso FV"),
        schneider_telemetry_point("dc_ac_mcu_event_code_1", "Evento MCU DC-AC 1", 0x1900, 2, "uint32", section="Stato e allarmi"),
        schneider_telemetry_point("dc_ac_mcu_event_code_2", "Evento MCU DC-AC 2", 0x1902, 2, "uint32", section="Stato e allarmi"),
        schneider_telemetry_point("dc_dc_mcu_event_code_1", "Evento MCU DC-DC 1", 0x1904, 2, "uint32", section="Stato e allarmi"),
        schneider_telemetry_point("dc_dc_mcu_event_code_2", "Evento MCU DC-DC 2", 0x1906, 2, "uint32", section="Stato e allarmi"),
        schneider_telemetry_point("comm_mcu_event_code_1", "Evento MCU comunicazione 1", 0x1908, 2, "uint32", section="Stato e allarmi"),
        schneider_telemetry_point("comm_mcu_event_code_2", "Evento MCU comunicazione 2", 0x190A, 2, "uint32", section="Stato e allarmi"),
        schneider_telemetry_point("global_utc_time", "Timestamp globale UTC", 0x1920, 2, "uint32", section="Configurazione"),
        schneider_telemetry_point("service_code_1", "Service 1", 0x1922, 1, "uint16", section="Stato e allarmi"),
        schneider_telemetry_point("service_code_1_time", "Timestamp service 1", 0x1923, 2, "uint32", section="Stato e allarmi"),
        schneider_telemetry_point("service_code_2", "Service 2", 0x1925, 1, "uint16", section="Stato e allarmi"),
        schneider_telemetry_point("service_code_2_time", "Timestamp service 2", 0x1926, 2, "uint32", section="Stato e allarmi"),
        schneider_telemetry_point("modbus_address", "Indirizzo Modbus", 0x8003, 1, "uint16", section="Configurazione"),
        schneider_telemetry_point("modbus_baud_rate", "Baud rate Modbus", 0x8010, 1, "uint16", section="Configurazione", enum_map=SCHNEIDER_BAUD_RATE_MAP),
        schneider_telemetry_point("sunspec_ac_current_sf", "SF corrente AC", 0x9C8C, 1, "int16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_ac_voltage_sf", "SF tensione AC", 0x9C93, 1, "int16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_ac_power_sf", "SF potenza AC", 0x9C95, 1, "int16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_ac_frequency_sf", "SF frequenza AC", 0x9C97, 1, "int16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_ac_va_sf", "SF VA AC", 0x9C99, 1, "int16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_ac_var_sf", "SF var AC", 0x9C9B, 1, "int16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_ac_pf_sf", "SF fattore di potenza", 0x9C9D, 1, "int16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_energy_sf", "SF energia", 0x9CA0, 1, "uint16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_dc_current_sf", "SF corrente DC", 0x9CA2, 1, "int16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_temperature_sf", "SF temperatura", 0x9CAB, 1, "int16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_mppt_dc_current_sf", "SF corrente MPPT", 0x9CBC, 1, "int16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_mppt_dc_voltage_sf", "SF tensione MPPT", 0x9CBD, 1, "int16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_mppt_dc_power_sf", "SF potenza MPPT", 0x9CBE, 1, "int16", section="SunSpec", visible=False),
        schneider_telemetry_point("sunspec_manufacturer", "SunSpec produttore", 0x9C44, 16, "ascii_string", section="SunSpec"),
        schneider_telemetry_point("sunspec_model", "SunSpec modello", 0x9C54, 16, "ascii_string", section="SunSpec"),
        schneider_telemetry_point("sunspec_options", "SunSpec opzioni", 0x9C64, 8, "ascii_string", section="SunSpec"),
        schneider_telemetry_point("sunspec_version", "SunSpec versione", 0x9C6C, 8, "ascii_string", section="SunSpec"),
        schneider_telemetry_point("sunspec_serial_number", "SunSpec seriale", 0x9C74, 16, "ascii_string", section="SunSpec"),
        schneider_telemetry_point("sunspec_device_address", "SunSpec device address", 0x9C84, 1, "uint16", section="SunSpec"),
        schneider_telemetry_point("sunspec_ac_current_a", "SunSpec corrente AC totale", 0x9C88, 1, "uint16", unit="A", section="SunSpec", scale_factor_key="sunspec_ac_current_sf"),
        schneider_telemetry_point("sunspec_ac_voltage_ab_v", "SunSpec tensione AC AB", 0x9C8D, 1, "uint16", unit="V", section="SunSpec", scale_factor_key="sunspec_ac_voltage_sf"),
        schneider_telemetry_point("sunspec_active_power_w", "SunSpec potenza attiva", 0x9C94, 1, "int16", unit="W", section="SunSpec", scale_factor_key="sunspec_ac_power_sf"),
        schneider_telemetry_point("sunspec_frequency_hz", "SunSpec frequenza", 0x9C96, 1, "uint16", unit="Hz", section="SunSpec", scale_factor_key="sunspec_ac_frequency_sf"),
        schneider_telemetry_point("sunspec_apparent_power_va", "SunSpec potenza apparente", 0x9C98, 1, "int16", unit="VA", section="SunSpec", scale_factor_key="sunspec_ac_va_sf"),
        schneider_telemetry_point("sunspec_reactive_power_var", "SunSpec potenza reattiva", 0x9C9A, 1, "int16", unit="VAr", section="SunSpec", scale_factor_key="sunspec_ac_var_sf"),
        schneider_telemetry_point("sunspec_power_factor", "SunSpec fattore di potenza", 0x9C9C, 1, "int16", section="SunSpec", scale_factor_key="sunspec_ac_pf_sf"),
        schneider_telemetry_point("sunspec_energy_wh", "SunSpec energia AC", 0x9C9E, 2, "uint32", unit="Wh", section="SunSpec", scale_factor_key="sunspec_energy_sf"),
        schneider_telemetry_point("sunspec_dc_current_a", "SunSpec corrente DC", 0x9CA1, 1, "uint16", unit="A", section="SunSpec", scale_factor_key="sunspec_dc_current_sf"),
        schneider_telemetry_point("sunspec_cabinet_temperature_c", "SunSpec temperatura ambiente", 0x9CA7, 1, "int16", unit="C", section="SunSpec", scale_factor_key="sunspec_temperature_sf"),
        schneider_telemetry_point("sunspec_status", "SunSpec stato", 0x9CAC, 1, "uint16", section="SunSpec", enum_map=SCHNEIDER_SUNSPEC_STATUS_MAP),
        schneider_telemetry_point("sunspec_status_vendor", "SunSpec stato vendor", 0x9CAD, 1, "uint16", section="SunSpec", enum_map=SCHNEIDER_OPERATIONAL_MODE_MAP),
        schneider_telemetry_point("sunspec_mppt_modules_count", "Numero moduli MPPT", 0x9CC2, 1, "uint16", section="SunSpec"),
        schneider_telemetry_point("sunspec_mppt_1_label", "MPPT 1 label", 0x9CC5, 8, "ascii_string", section="SunSpec"),
        schneider_telemetry_point("sunspec_mppt_1_current_a", "MPPT 1 corrente", 0x9CCD, 1, "uint16", unit="A", section="SunSpec", scale_factor_key="sunspec_mppt_dc_current_sf"),
        schneider_telemetry_point("sunspec_mppt_1_voltage_v", "MPPT 1 tensione", 0x9CCE, 1, "uint16", unit="V", section="SunSpec", scale_factor_key="sunspec_mppt_dc_voltage_sf"),
        schneider_telemetry_point("sunspec_mppt_1_power_w", "MPPT 1 potenza", 0x9CCF, 1, "int16", unit="W", section="SunSpec", scale_factor_key="sunspec_mppt_dc_power_sf"),
        schneider_telemetry_point("sunspec_mppt_1_temperature_c", "MPPT 1 temperatura modulo", 0x9CD4, 1, "int16", unit="C", section="SunSpec"),
        schneider_telemetry_point("sunspec_mppt_1_state", "MPPT 1 stato", 0x9CD5, 1, "uint16", section="SunSpec", enum_map=SCHNEIDER_SUNSPEC_STATUS_MAP),
        schneider_telemetry_point("sunspec_mppt_2_label", "MPPT 2 label", 0x9CD9, 8, "ascii_string", section="SunSpec"),
        schneider_telemetry_point("sunspec_mppt_2_current_a", "MPPT 2 corrente", 0x9CE1, 1, "uint16", unit="A", section="SunSpec", scale_factor_key="sunspec_mppt_dc_current_sf"),
        schneider_telemetry_point("sunspec_mppt_2_voltage_v", "MPPT 2 tensione", 0x9CE2, 1, "uint16", unit="V", section="SunSpec", scale_factor_key="sunspec_mppt_dc_voltage_sf"),
        schneider_telemetry_point("sunspec_mppt_2_power_w", "MPPT 2 potenza", 0x9CE3, 1, "int16", unit="W", section="SunSpec", scale_factor_key="sunspec_mppt_dc_power_sf"),
        schneider_telemetry_point("sunspec_mppt_2_temperature_c", "MPPT 2 temperatura modulo", 0x9CE8, 1, "int16", unit="C", section="SunSpec"),
        schneider_telemetry_point("sunspec_mppt_2_state", "MPPT 2 stato", 0x9CE9, 1, "uint16", section="SunSpec", enum_map=SCHNEIDER_SUNSPEC_STATUS_MAP),
    ]


def build_schneider_conext_cl_commands() -> list[InverterPoint]:
    return [
        schneider_command_point("global_utc_time_write", "Imposta timestamp UTC", 0x1920, "uint32", section="Configurazione"),
        schneider_command_point("modbus_address_write", "Scrivi indirizzo Modbus", 0x8003, "uint16", section="Configurazione", min_value=1, max_value=247),
        schneider_command_point("modbus_baud_rate_write", "Scrivi baud rate Modbus", 0x8010, "uint16", section="Configurazione", min_value=0, max_value=4, enum_map=SCHNEIDER_BAUD_RATE_MAP),
        schneider_command_point("remote_operation", "Comando remoto", 0xEFFE, "uint16", section="Controllo potenza", enum_map=SCHNEIDER_REMOTE_OPERATION_MAP),
        schneider_command_point("active_power_limit_kw", "Limite potenza attiva", 0xFA19, "uint16", scale=0.1, unit="kW", section="Controllo potenza", min_value=0, max_value=25.0),
        schneider_command_point("active_power_limit_pct", "Limite potenza attiva percentuale", 0xFAF1, "uint16", unit="%", section="Controllo potenza", min_value=0, max_value=100),
        schneider_command_point("reactive_power_mode", "Modalita potenza reattiva", 0xFA60, "uint16", section="Controllo reattivo", min_value=0, max_value=4, enum_map=SCHNEIDER_REACTIVE_MODE_MAP),
        schneider_command_point("fixed_cosphi", "Cosphi fisso", 0xFA61, "int16", scale=0.001, section="Controllo reattivo"),
        schneider_command_point("cosphi_p_upper_limit", "Cosphi(P) limite superiore", 0xFA62, "int16", scale=0.0001, section="Controllo reattivo"),
        schneider_command_point("cosphi_p_lower_limit", "Cosphi(P) limite inferiore", 0xFA63, "int16", scale=0.0001, section="Controllo reattivo"),
        schneider_command_point("cosphi_p_power_low_pct", "Cosphi(P) potenza bassa", 0xFA64, "uint16", unit="%", section="Controllo reattivo", min_value=10, max_value=30),
        schneider_command_point("cosphi_p_power_mid_pct", "Cosphi(P) potenza media", 0xFA80, "uint16", unit="%", section="Controllo reattivo", min_value=30, max_value=70),
        schneider_command_point("cosphi_p_power_high_pct", "Cosphi(P) potenza alta", 0xFA65, "uint16", unit="%", section="Controllo reattivo", min_value=70, max_value=100),
        schneider_command_point("cosphi_p_lock_in_voltage_pct", "Cosphi(P) lock-in tensione", 0xF9EE, "uint16", unit="%", section="Controllo reattivo", min_value=100, max_value=110),
        schneider_command_point("cosphi_p_lock_out_voltage_pct", "Cosphi(P) lock-out tensione", 0xF9EF, "uint16", unit="%", section="Controllo reattivo", min_value=90, max_value=100),
        schneider_command_point("cosphi_p_time_delay_s", "Cosphi(P) ritardo", 0xFA81, "uint16", unit="s", section="Controllo reattivo", min_value=0, max_value=100),
        schneider_command_point("cosphi_p_response_delay_s", "Cosphi(P) ritardo risposta", 0xFA82, "uint16", unit="s", section="Controllo reattivo", min_value=0, max_value=100),
        schneider_command_point("fixed_kvar_pct", "kVAr fisso", 0xFA66, "int16", scale=0.01, unit="%", section="Controllo reattivo", min_value=-60, max_value=60),
        schneider_command_point("fixed_kvar_lock_in_power_pct", "kVAr fisso lock-in potenza", 0xFA83, "uint16", unit="%", section="Controllo reattivo", min_value=5, max_value=80),
        schneider_command_point("fixed_kvar_time_delay_s", "kVAr fisso ritardo", 0xFA84, "uint16", unit="s", section="Controllo reattivo", min_value=0, max_value=100),
        schneider_command_point("kvar_u_upper_limit_pct", "kVAr(U) limite superiore", 0xFA67, "uint16", unit="%", section="Controllo reattivo", min_value=0, max_value=60),
        schneider_command_point("kvar_u_lower_limit_pct", "kVAr(U) limite inferiore", 0xFA68, "uint16", unit="%", section="Controllo reattivo", min_value=0, max_value=60),
        schneider_command_point("kvar_u_vlow_set_v", "kVAr(U) VLowSet", 0xFA69, "uint16", scale=0.1, unit="V", section="Controllo reattivo"),
        schneider_command_point("kvar_u_vhigh_set_v", "kVAr(U) VHighSet", 0xFA6A, "uint16", scale=0.1, unit="V", section="Controllo reattivo"),
        schneider_command_point("kvar_u_vmin_v", "kVAr(U) VMin", 0xFA6B, "uint16", scale=0.1, unit="V", section="Controllo reattivo"),
        schneider_command_point("kvar_u_vmax_v", "kVAr(U) VMax", 0xFA6C, "uint16", scale=0.1, unit="V", section="Controllo reattivo"),
        schneider_command_point("kvar_u_hysteresis_v", "kVAr(U) isteresi", 0xFA6D, "uint16", scale=0.1, unit="V", section="Controllo reattivo"),
        schneider_command_point("kvar_u_response_time_s", "kVAr(U) tempo risposta", 0xFA6E, "uint16", unit="s", section="Controllo reattivo", min_value=0, max_value=100),
        schneider_command_point("kvar_u_lock_in_power_pct", "kVAr(U) lock-in potenza", 0xF9F0, "uint16", unit="%", section="Controllo reattivo", min_value=0, max_value=30),
        schneider_command_point("kvar_u_lock_out_power_pct", "kVAr(U) lock-out potenza", 0xF9F1, "uint16", unit="%", section="Controllo reattivo", min_value=0, max_value=30),
        schneider_command_point("inverter_mode", "Modalita inverter", 0xFA90, "uint16", section="Controllo potenza", enum_map=SCHNEIDER_INVERTER_MODE_MAP),
        schneider_command_point("multifunction_relay_mode", "Modalita relay multifunzione", 0xFAF5, "uint16", section="Relay multifunzione", min_value=0, max_value=5, enum_map=SCHNEIDER_RELAY_MODE_MAP),
        schneider_command_point("multifunction_fault_code_1", "Relay fault code 1", 0xFAF6, "uint16", section="Relay multifunzione"),
        schneider_command_point("multifunction_fault_code_2", "Relay fault code 2", 0xFAF7, "uint16", section="Relay multifunzione"),
        schneider_command_point("multifunction_fault_code_3", "Relay fault code 3", 0xFAF8, "uint16", section="Relay multifunzione"),
        schneider_command_point("multifunction_power_production_mode", "Relay power production", 0xFAF9, "uint16", section="Relay multifunzione", min_value=0, max_value=2),
        schneider_command_point("multifunction_output_power_upper_limit_kw", "Relay soglia potenza", 0xFAFA, "uint16", scale=0.1, unit="kW", section="Relay multifunzione", min_value=0, max_value=25.0),
        schneider_command_point("multifunction_trip_count_min", "Relay trip count", 0xFAFB, "uint16", unit="min", section="Relay multifunzione", min_value=0, max_value=999),
        schneider_command_point("multifunction_min_duration_min", "Relay durata minima", 0xFAFC, "uint16", unit="min", section="Relay multifunzione", min_value=0, max_value=10),
        schneider_command_point("multifunction_on_temperature_c", "Relay temperatura ON", 0xFAFD, "uint16", scale=0.1, unit="C", section="Relay multifunzione", min_value=0, max_value=90),
        schneider_command_point("multifunction_off_temperature_c", "Relay temperatura OFF", 0xFAFE, "uint16", scale=0.1, unit="C", section="Relay multifunzione", min_value=0, max_value=89.9),
    ]


def build_schneider_conext_cl_models(protocol: str, transport: str) -> list[InverterModel]:
    if protocol == "modbus_rtu":
        defaults = {
            "port": "COM1",
            "slave_id": 10,
            "baud_rate": 9600,
            "parity": "N",
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
            "unit_id": 10,
            "timeout_seconds": 2,
            "retries": 1,
            "poll_interval_seconds": 15,
            "max_registers_per_request": 100,
            "test_register": 0x1700,
            "test_count": 1,
            "test_function": "holding",
        }

    telemetry = build_schneider_conext_cl_telemetry()
    commands = build_schneider_conext_cl_commands()

    return [
        InverterModel(
            brand="Schneider",
            model=model,
            protocol=protocol,
            transport=transport,
            defaults=defaults,
            features=[
                "telemetria trifase conext cl",
                "doppio ingresso mppt",
                "blocchi sunspec",
                "controllo potenza attiva",
                "controllo potenza reattiva IEC",
                "relay multifunzione",
            ],
            telemetry_points=telemetry,
            command_points=commands,
        )
        for model in SCHNEIDER_CONEXT_CL_MODELS
    ]
