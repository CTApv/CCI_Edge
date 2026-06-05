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


PEIMAR_MODELS = [
    "PSI-X3P6000-TP",
    "PSI-X3P8000-TP",
    "PSI-X3P10000-TP",
    "PSI-X3P15000-TPM",
    "PSI-X3P20000-TPM",
    "PSI-X3P30000-TPM",
]

PEIMAR_RUN_MODE_MAP = {
    0: "Attesa",
    1: "Controllo",
    2: "Normale",
    3: "Guasto",
    4: "Guasto permanente",
}

PEIMAR_POWER_FACTOR_MODE_MAP = {
    0: "Disattivato",
    1: "Sovraeccitato",
    2: "Sottoeccitato",
    3: "Curva cosphi",
}

PEIMAR_QCURVE_MODE_MAP = {
    0: "Disattivato",
    1: "Sovraeccitato",
    2: "Sottoeccitato",
    3: "Power factor",
    4: "Q(U)",
    5: "Q fisso",
}

PEIMAR_ENABLE_DISABLE_MAP = {
    0: "Disabilitato",
    1: "Abilitato",
}

PEIMAR_OUTPUT_SWITCH_MAP = {
    0: "Stop",
    1: "Avvio",
}

PEIMAR_UNLOCK_STATE_MAP = {
    0: "Bloccato",
    1: "Sbloccato",
    2: "Sbloccato",
}

PEIMAR_MPPT_SCAN_MODE_MAP = {
    0: "Disattivato",
    1: "Scansione periodica",
    2: "Scansione rapida",
    3: "Scansione estesa",
}

PEIMAR_MACHINE_TYPE_MAP = {
    1: "3 kW TP",
    2: "4 kW TP",
    3: "5 kW TP",
    4: "6 kW TP",
    5: "8 kW TP",
    6: "10 kW TP",
    7: "12 kW TP",
    8: "15 kW TP",
    9: "8 kW TPM",
    10: "10 kW TPM",
    11: "12 kW TPM EU",
    12: "12 kW TPM AU",
    13: "15 kW TPM EU",
    14: "15 kW TPM AU",
    15: "17 kW TPM EU",
    16: "17 kW TPM AU",
    17: "20 kW TPM EU",
    18: "20 kW TPM AU",
    19: "25 kW TPM",
    20: "30 kW TPM",
    21: "PSI-X3P10000-TP",
    22: "PSI-X3P5000-TP",
    23: "PSI-X3P6000-TP",
    24: "PSI-X3P8000-TP",
    25: "PSI-X3P10000-TPM",
    26: "PSI-X3P12000-TPM",
    27: "PSI-X3P15000-TPM",
    28: "PSI-X3P10000-TP standard output",
    29: "PSI-X3P10000-TPM standard output",
}

PEIMAR_SAFETY_TYPE_MAP = {
    0: "VDE0126",
    1: "ARN4105",
    2: "AS4777 AU",
    3: "G98",
    4: "C10/11",
    5: "E8001",
    6: "EN50438 Netherlands",
    7: "EN50438 Denmark 2019 W",
    8: "CEB",
    9: "CEI 0-21",
    10: "NRS097-2-1",
    11: "VDE0126 Greece Island",
    12: "UTE C15-712",
    13: "IEC61727 In",
    14: "G99",
    15: "VDE0126 Greece",
    16: "France Guyana 50Hz",
    17: "France Island 50Hz",
    18: "France Island 60Hz",
    19: "AS4777 NZ",
    20: "RD1699",
    21: "Chile",
    22: "EN50438 Ireland",
    23: "G98 Philippines",
    24: "Czech PPDS",
    25: "EN50438 Czech",
    26: "EN50549-1",
    27: "EN50438 Denmark 2019 E",
    28: "RD1699 Island",
    29: "EN50549 Poland",
    30: "MEA Thailand",
    31: "PEA Thailand",
    32: "CEI 0-21 ACEA",
    33: "AS4777 B",
    34: "AS4777 C",
    35: "User Defined",
    36: "CQC",
    37: "IEC61727 Brazil",
    38: "IEC61727",
    39: "IEC61727 Brazil LV",
    40: "TOR",
    41: "CEI 0-16",
    42: "Chile 2021",
    43: "Chile 2021 MT R",
    44: "Chile 2021 MT U",
    45: "Czech 2021-2",
    46: "EN50549 Sweden",
    47: "EN50549 Romania",
    48: "Slovenia",
    49: "SSDG",
    50: "Cyprus 2019",
    51: "DEWA",
    52: "EN50549 Estonia",
}

PEIMAR_GRID_SERVICES_BITS = {
    0: "Soft Start",
    1: "Vac 10 min",
    2: "Fac Rocof",
    3: "RPBF",
    4: "IPBF",
    5: "Pu",
    6: "Qu",
    7: "Pf",
    8: "DC injection",
    9: "VRT",
    10: "DRM",
    11: "Self test",
}

PEIMAR_INVERTER_FAULT_BITS = {
    0: "Tz protect fault",
    1: "Mains lost fault",
    2: "Grid voltage fault",
    3: "Grid frequency fault",
    4: "PV voltage fault",
    5: "Bus voltage fault",
    7: "Grid voltage 10 min fault",
    8: "DC injection OCP",
    10: "Software OCP",
    11: "Residual OCP",
    12: "Isolation fault",
    13: "Over temperature fault",
    20: "Low temperature fault",
    24: "Internal communications fault",
    25: "Fan fault",
    26: "AC terminal OTP",
    27: "EEPROM fault",
    28: "RC device fault",
    29: "PV connection direction fault",
    30: "Grid relay fault",
    31: "Other device fault",
}

PEIMAR_MANAGER_FAULT_BITS = {
    0: "Power type fault",
    2: "E2prom error",
    3: "ARM DSP communications error",
    4: "Meter error",
    14: "Fan 1 error",
    15: "Fan 2 error",
}


def peimar_telemetry_point(
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

    return telemetry_point(
        key=key,
        label=label,
        register_type=register_type,
        address=address,
        length=length,
        datatype=datatype,
        scale=scale,
        unit=unit,
        visible=visible,
        protocol_meta=protocol_meta,
    )


def peimar_command_point(
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
) -> InverterPoint:
    protocol_meta: dict[str, object] = {"section": section}
    if min_value is not None:
        protocol_meta["min_value"] = min_value
    if max_value is not None:
        protocol_meta["max_value"] = max_value
    if step is not None:
        protocol_meta["step"] = step

    return command_point(
        key=key,
        label=label,
        register_type="holding",
        address=address,
        length=1,
        datatype=datatype,
        scale=scale,
        unit=unit,
        protocol_meta=protocol_meta,
    )


def build_peimar_telemetry() -> list[InverterPoint]:
    return [
        peimar_telemetry_point("series_number", "Seriale", "holding", 0x300, 7, "ascii_string", section="Identificazione"),
        peimar_telemetry_point("factory_name", "Produttore", "holding", 0x307, 7, "ascii_string", section="Identificazione"),
        peimar_telemetry_point("module_name", "Nome modulo", "holding", 0x30E, 7, "ascii_string", section="Identificazione"),
        peimar_telemetry_point("firmware_version", "Firmware", "holding", 0x315, 3, "ascii_string", section="Identificazione"),
        peimar_telemetry_point("dsp_firmware_version", "Firmware DSP", "holding", 0x352, 1, "uint16", section="Identificazione"),
        peimar_telemetry_point("arm_firmware_version", "Firmware ARM", "holding", 0x353, 1, "uint16", section="Identificazione"),
        peimar_telemetry_point("modbus_address", "Indirizzo Modbus", "holding", 0x377, 1, "uint16", section="Identificazione"),
        peimar_telemetry_point("rtc_second", "RTC secondi", "holding", 0x318, 1, "uint16", section="Configurazione"),
        peimar_telemetry_point("rtc_minute", "RTC minuti", "holding", 0x319, 1, "uint16", section="Configurazione"),
        peimar_telemetry_point("rtc_hour", "RTC ore", "holding", 0x31A, 1, "uint16", section="Configurazione"),
        peimar_telemetry_point("rtc_day", "RTC giorno", "holding", 0x31B, 1, "uint16", section="Configurazione"),
        peimar_telemetry_point("rtc_month", "RTC mese", "holding", 0x31C, 1, "uint16", section="Configurazione"),
        peimar_telemetry_point("rtc_year", "RTC anno", "holding", 0x31D, 1, "uint16", section="Configurazione"),
        peimar_telemetry_point("power_factor_mode_profile", "Modalita power factor", "holding", 0x31E, 1, "uint16", section="Controllo reattivo", enum_map=PEIMAR_POWER_FACTOR_MODE_MAP),
        peimar_telemetry_point("power_factor_setpoint", "Setpoint power factor", "holding", 0x31F, 1, "uint16", scale=0.01, section="Controllo reattivo"),
        peimar_telemetry_point("power_factor_limit_up", "Limite superiore power factor", "holding", 0x320, 1, "uint16", scale=0.01, section="Controllo reattivo"),
        peimar_telemetry_point("power_factor_limit_down", "Limite inferiore power factor", "holding", 0x321, 1, "uint16", scale=0.01, section="Controllo reattivo"),
        peimar_telemetry_point("power_ratio_limit_1_pct", "Rapporto potenza 1", "holding", 0x322, 1, "uint16", scale=0.1, unit="%", section="Controllo reattivo"),
        peimar_telemetry_point("power_ratio_limit_2_pct", "Rapporto potenza 2", "holding", 0x323, 1, "uint16", scale=0.1, unit="%", section="Controllo reattivo"),
        peimar_telemetry_point("grid_services", "Servizi di rete attivi", "holding", 0x324, 1, "uint16", section="Configurazione", bitmask_labels=PEIMAR_GRID_SERVICES_BITS),
        peimar_telemetry_point("checking_time_s", "Tempo connessione", "holding", 0x325, 1, "uint16", unit="s", section="Protezioni rete"),
        peimar_telemetry_point("reconnection_time_s", "Tempo riconnessione", "holding", 0x326, 1, "uint16", unit="s", section="Protezioni rete"),
        peimar_telemetry_point("vac_ovp_1_v", "Soglia sovratensione 1", "holding", 0x327, 1, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_telemetry_point("vac_ovp_2_v", "Soglia sovratensione 2", "holding", 0x328, 1, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_telemetry_point("vac_ovp_3_v", "Soglia sovratensione 3", "holding", 0x329, 1, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_telemetry_point("vac_uvp_1_v", "Soglia sottotensione 1", "holding", 0x32A, 1, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_telemetry_point("vac_uvp_2_v", "Soglia sottotensione 2", "holding", 0x32B, 1, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_telemetry_point("vac_uvp_3_v", "Soglia sottotensione 3", "holding", 0x32C, 1, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_telemetry_point("vac_10min_ovp_v", "Sovratensione media 10 min", "holding", 0x32D, 1, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_telemetry_point("vac_startup_high_v", "Tensione avvio alta", "holding", 0x32E, 1, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_telemetry_point("vac_startup_low_v", "Tensione avvio bassa", "holding", 0x32F, 1, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_telemetry_point("vac_ovp_recover_v", "Ripristino sovratensione", "holding", 0x330, 1, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_telemetry_point("vac_uvp_recover_v", "Ripristino sottotensione", "holding", 0x331, 1, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_telemetry_point("vac_ovp_1_time_10ms", "Tempo sovratensione 1", "holding", 0x332, 1, "uint16", unit="10ms", section="Protezioni rete"),
        peimar_telemetry_point("vac_ovp_2_time_10ms", "Tempo sovratensione 2", "holding", 0x333, 1, "uint16", unit="10ms", section="Protezioni rete"),
        peimar_telemetry_point("vac_uvp_1_time_10ms", "Tempo sottotensione 1", "holding", 0x334, 1, "uint16", unit="10ms", section="Protezioni rete"),
        peimar_telemetry_point("vac_uvp_2_time_10ms", "Tempo sottotensione 2", "holding", 0x335, 1, "uint16", unit="10ms", section="Protezioni rete"),
        peimar_telemetry_point("fac_ofp_1_hz", "Soglia sovrafrequenza 1", "holding", 0x336, 1, "uint16", scale=0.01, unit="Hz", section="Protezioni rete"),
        peimar_telemetry_point("fac_ofp_2_hz", "Soglia sovrafrequenza 2", "holding", 0x337, 1, "uint16", scale=0.01, unit="Hz", section="Protezioni rete"),
        peimar_telemetry_point("fac_ufp_1_hz", "Soglia sottofrequenza 1", "holding", 0x338, 1, "uint16", scale=0.01, unit="Hz", section="Protezioni rete"),
        peimar_telemetry_point("fac_ufp_2_hz", "Soglia sottofrequenza 2", "holding", 0x339, 1, "uint16", scale=0.01, unit="Hz", section="Protezioni rete"),
        peimar_telemetry_point("fac_startup_high_hz", "Frequenza avvio alta", "holding", 0x33A, 1, "uint16", scale=0.01, unit="Hz", section="Protezioni rete"),
        peimar_telemetry_point("fac_startup_low_hz", "Frequenza avvio bassa", "holding", 0x33B, 1, "uint16", scale=0.01, unit="Hz", section="Protezioni rete"),
        peimar_telemetry_point("fac_ofp_recover_hz", "Ripristino sovrafrequenza", "holding", 0x33C, 1, "uint16", scale=0.01, unit="Hz", section="Protezioni rete"),
        peimar_telemetry_point("fac_ufp_recover_hz", "Ripristino sottofrequenza", "holding", 0x33D, 1, "uint16", scale=0.01, unit="Hz", section="Protezioni rete"),
        peimar_telemetry_point("qcurve_fix_q_var", "Q fisso", "holding", 0x346, 1, "int16", unit="Var", section="Controllo reattivo"),
        peimar_telemetry_point("qcurve_set_mode", "Modalita controllo reattivo", "holding", 0x347, 1, "uint8_low", section="Controllo reattivo", enum_map=PEIMAR_QCURVE_MODE_MAP),
        peimar_telemetry_point("qcurve_set_pf", "Setpoint power factor QCurve", "holding", 0x347, 1, "uint8_high", scale=0.01, section="Controllo reattivo"),
        peimar_telemetry_point("qcurve_pf1_limit_up", "Limite superiore PF 1", "holding", 0x348, 1, "uint8_low", scale=0.01, section="Controllo reattivo"),
        peimar_telemetry_point("qcurve_pf2_limit_down", "Limite inferiore PF 2", "holding", 0x348, 1, "uint8_high", scale=0.01, section="Controllo reattivo"),
        peimar_telemetry_point("qcurve_pf3_limit_up", "Limite superiore PF 3", "holding", 0x349, 1, "uint8_low", scale=0.01, section="Controllo reattivo"),
        peimar_telemetry_point("qcurve_pf4_limit_down", "Limite inferiore PF 4", "holding", 0x349, 1, "uint8_high", scale=0.01, section="Controllo reattivo"),
        peimar_telemetry_point("qcurve_power_ratio_1_pct", "Rapporto potenza curva 1", "holding", 0x34A, 1, "uint16", scale=0.1, unit="%", section="Controllo reattivo"),
        peimar_telemetry_point("qcurve_power_ratio_2_pct", "Rapporto potenza curva 2", "holding", 0x34B, 1, "uint16", scale=0.1, unit="%", section="Controllo reattivo"),
        peimar_telemetry_point("qcurve_power_ratio_3_pct", "Rapporto potenza curva 3", "holding", 0x34C, 1, "uint16", scale=0.1, unit="%", section="Controllo reattivo"),
        peimar_telemetry_point("qcurve_power_ratio_4_pct", "Rapporto potenza curva 4", "holding", 0x34D, 1, "uint16", scale=0.1, unit="%", section="Controllo reattivo"),
        peimar_telemetry_point("machine_type", "Tipo macchina", "holding", 0x34E, 1, "uint8_low", section="Configurazione", enum_map=PEIMAR_MACHINE_TYPE_MAP),
        peimar_telemetry_point("safety_profile", "Profilo sicurezza", "holding", 0x34E, 1, "uint8_high", section="Configurazione", enum_map=PEIMAR_SAFETY_TYPE_MAP),
        peimar_telemetry_point("mppt_scan_mode", "Modalita scansione MPPT", "holding", 0x34F, 1, "uint8_low", section="Configurazione", enum_map=PEIMAR_MPPT_SCAN_MODE_MAP),
        peimar_telemetry_point("power_limit_ratio_pct", "Limite potenza percentuale", "holding", 0x34F, 1, "uint8_high", scale=0.01, unit="%", section="Configurazione"),
        peimar_telemetry_point("soft_start_slope_pct", "Pendenza soft start", "holding", 0x350, 1, "uint16", scale=0.1, unit="%", section="Configurazione"),
        peimar_telemetry_point("ac_active_power_set_w", "Setpoint potenza attiva AC", "holding", 0x351, 1, "uint16", unit="W", section="Configurazione"),
        peimar_telemetry_point("datalogger_power_ratio_limit_pct", "Limite potenza datalogger", "holding", 0x354, 1, "uint16", unit="%", section="Configurazione"),
        peimar_telemetry_point("meter_enable", "Contatore abilitato", "holding", 0x355, 1, "uint16", section="Configurazione", enum_map=PEIMAR_ENABLE_DISABLE_MAP),
        peimar_telemetry_point("qu_lock_enable", "Blocco Q(U)", "holding", 0x35F, 1, "uint16", section="Controllo reattivo", enum_map=PEIMAR_ENABLE_DISABLE_MAP),
        peimar_telemetry_point("connection_gradient", "Gradiente connessione", "holding", 0x360, 1, "uint16", section="Protezioni rete"),
        peimar_telemetry_point("reconnection_gradient", "Gradiente riconnessione", "holding", 0x361, 1, "uint16", section="Protezioni rete"),
        peimar_telemetry_point("output_switch_state", "Comando uscita", "holding", 0x366, 1, "uint16", section="Configurazione", enum_map=PEIMAR_OUTPUT_SWITCH_MAP),
        peimar_telemetry_point("unlock_state", "Stato sblocco", "holding", 0x367, 1, "uint16", section="Configurazione", enum_map=PEIMAR_UNLOCK_STATE_MAP),
        peimar_telemetry_point("power_manager_enable", "Power manager", "holding", 0x36E, 1, "uint16", section="Configurazione", enum_map=PEIMAR_ENABLE_DISABLE_MAP),
        peimar_telemetry_point("expected_apparent_power_va", "Potenza apparente obiettivo", "holding", 0x36F, 1, "uint16", unit="VA", section="Configurazione"),
        peimar_telemetry_point("expected_apparent_power_hard_va", "Potenza apparente hard", "holding", 0x370, 1, "uint16", unit="VA", section="Configurazione"),
        peimar_telemetry_point("export_power_limit_w", "Limite export", "holding", 0x371, 1, "uint16", unit="W", section="Configurazione"),
        peimar_telemetry_point("export_power_limit_hard_w", "Limite export hard", "holding", 0x372, 1, "uint16", unit="W", section="Configurazione"),
        peimar_telemetry_point("export_check_enable", "Export control", "holding", 0x373, 1, "uint16", section="Configurazione", enum_map=PEIMAR_ENABLE_DISABLE_MAP),
        peimar_telemetry_point("lease_mode", "Lease mode", "holding", 0x374, 1, "uint16", section="Configurazione", enum_map=PEIMAR_ENABLE_DISABLE_MAP),
        peimar_telemetry_point("external_signal", "Segnale esterno", "holding", 0x375, 1, "uint16", section="Configurazione", enum_map=PEIMAR_ENABLE_DISABLE_MAP),
        peimar_telemetry_point("external_failed", "Errore segnale esterno", "holding", 0x376, 1, "uint16", section="Configurazione", enum_map=PEIMAR_ENABLE_DISABLE_MAP),
        peimar_telemetry_point("pv1_voltage_v", "Tensione FV 1", "input", 0x400, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV"),
        peimar_telemetry_point("pv2_voltage_v", "Tensione FV 2", "input", 0x401, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV"),
        peimar_telemetry_point("pv1_current_a", "Corrente FV 1", "input", 0x402, 1, "uint16", scale=0.1, unit="A", section="Ingresso FV"),
        peimar_telemetry_point("pv2_current_a", "Corrente FV 2", "input", 0x403, 1, "uint16", scale=0.1, unit="A", section="Ingresso FV"),
        peimar_telemetry_point("grid_voltage_r_v", "Tensione rete fase R", "input", 0x404, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        peimar_telemetry_point("grid_voltage_s_v", "Tensione rete fase S", "input", 0x405, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        peimar_telemetry_point("grid_voltage_t_v", "Tensione rete fase T", "input", 0x406, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        peimar_telemetry_point("grid_frequency_r_hz", "Frequenza rete fase R", "input", 0x407, 1, "uint16", scale=0.01, unit="Hz", section="Rete AC"),
        peimar_telemetry_point("grid_frequency_s_hz", "Frequenza rete fase S", "input", 0x408, 1, "uint16", scale=0.01, unit="Hz", section="Rete AC"),
        peimar_telemetry_point("grid_frequency_t_hz", "Frequenza rete fase T", "input", 0x409, 1, "uint16", scale=0.01, unit="Hz", section="Rete AC"),
        peimar_telemetry_point("output_current_r_a", "Corrente uscita fase R", "input", 0x40A, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        peimar_telemetry_point("output_current_s_a", "Corrente uscita fase S", "input", 0x40B, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        peimar_telemetry_point("output_current_t_a", "Corrente uscita fase T", "input", 0x40C, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        peimar_telemetry_point("temperature_c", "Temperatura dissipatore", "input", 0x40D, 1, "uint16", unit="C", section="Termico", summary_metric="temperature_c"),
        peimar_telemetry_point("active_power_kw", "Potenza attiva", "input", 0x40E, 1, "uint16", scale=0.001, unit="kW", section="Potenza", summary_metric="power_kw"),
        peimar_telemetry_point("status", "Modalita inverter", "input", 0x40F, 1, "uint16", section="Stato e allarmi", summary_metric="status", enum_map=PEIMAR_RUN_MODE_MAP),
        peimar_telemetry_point("phase_r_power_kw", "Potenza fase R", "input", 0x410, 1, "uint16", scale=0.001, unit="kW", section="Potenza"),
        peimar_telemetry_point("phase_s_power_kw", "Potenza fase S", "input", 0x411, 1, "uint16", scale=0.001, unit="kW", section="Potenza"),
        peimar_telemetry_point("phase_t_power_kw", "Potenza fase T", "input", 0x412, 1, "uint16", scale=0.001, unit="kW", section="Potenza"),
        peimar_telemetry_point("dc_power_total_kw", "Potenza DC totale", "input", 0x413, 1, "uint16", scale=0.001, unit="kW", section="Potenza"),
        peimar_telemetry_point("dc1_power_kw", "Potenza DC 1", "input", 0x414, 1, "uint16", scale=0.001, unit="kW", section="Ingresso FV"),
        peimar_telemetry_point("dc2_power_kw", "Potenza DC 2", "input", 0x415, 1, "uint16", scale=0.001, unit="kW", section="Ingresso FV"),
        peimar_telemetry_point("grid_voltage_fault_r_v", "Guasto tensione fase R", "input", 0x416, 1, "uint16", scale=0.1, unit="V", section="Stato e allarmi"),
        peimar_telemetry_point("grid_voltage_fault_s_v", "Guasto tensione fase S", "input", 0x417, 1, "uint16", scale=0.1, unit="V", section="Stato e allarmi"),
        peimar_telemetry_point("grid_voltage_fault_t_v", "Guasto tensione fase T", "input", 0x418, 1, "uint16", scale=0.1, unit="V", section="Stato e allarmi"),
        peimar_telemetry_point("grid_frequency_fault_r_hz", "Guasto frequenza fase R", "input", 0x419, 1, "uint16", scale=0.01, unit="Hz", section="Stato e allarmi"),
        peimar_telemetry_point("grid_frequency_fault_s_hz", "Guasto frequenza fase S", "input", 0x41A, 1, "uint16", scale=0.01, unit="Hz", section="Stato e allarmi"),
        peimar_telemetry_point("grid_frequency_fault_t_hz", "Guasto frequenza fase T", "input", 0x41B, 1, "uint16", scale=0.01, unit="Hz", section="Stato e allarmi"),
        peimar_telemetry_point("dci_fault_r_ma", "Guasto DCI fase R", "input", 0x41C, 1, "uint16", unit="mA", section="Stato e allarmi"),
        peimar_telemetry_point("dci_fault_s_ma", "Guasto DCI fase S", "input", 0x41D, 1, "uint16", unit="mA", section="Stato e allarmi"),
        peimar_telemetry_point("dci_fault_t_ma", "Guasto DCI fase T", "input", 0x41E, 1, "uint16", unit="mA", section="Stato e allarmi"),
        peimar_telemetry_point("pv1_fault_voltage_v", "Guasto tensione FV 1", "input", 0x41F, 1, "uint16", scale=0.1, unit="V", section="Stato e allarmi"),
        peimar_telemetry_point("pv2_fault_voltage_v", "Guasto tensione FV 2", "input", 0x420, 1, "uint16", scale=0.1, unit="V", section="Stato e allarmi"),
        peimar_telemetry_point("temperature_fault_c", "Guasto temperatura dissipatore", "input", 0x421, 1, "uint16", unit="C", section="Stato e allarmi"),
        peimar_telemetry_point("gfci_fault_ma", "Guasto GFCI", "input", 0x422, 1, "uint16", unit="mA", section="Stato e allarmi"),
        peimar_telemetry_point("total_energy_kwh", "Energia totale", "input", 0x423, 2, "uint32_swapped", scale=0.1, unit="kWh", section="Contatori", summary_metric="total_energy_kwh"),
        peimar_telemetry_point("daily_energy_kwh", "Energia giornaliera", "input", 0x425, 2, "uint32_swapped", scale=0.1, unit="kWh", section="Contatori", summary_metric="daily_energy_kwh"),
        peimar_telemetry_point("inverter_faults", "Fault inverter", "input", 0x427, 2, "uint32_swapped", section="Stato e allarmi", bitmask_labels=PEIMAR_INVERTER_FAULT_BITS),
        peimar_telemetry_point("pv3_voltage_v", "Tensione FV 3", "input", 0x429, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV", optional_block=True),
        peimar_telemetry_point("pv3_current_a", "Corrente FV 3", "input", 0x42A, 1, "uint16", scale=0.1, unit="A", section="Ingresso FV", optional_block=True),
        peimar_telemetry_point("dc3_power_kw", "Potenza DC 3", "input", 0x42B, 1, "uint16", scale=0.001, unit="kW", section="Ingresso FV", optional_block=True),
        peimar_telemetry_point("control_board_temperature_c", "Temperatura scheda controllo", "input", 0x42C, 1, "uint16", unit="C", section="Termico", optional_block=True),
        peimar_telemetry_point("control_board_temperature_fault_c", "Guasto temperatura scheda", "input", 0x42D, 1, "uint16", unit="C", section="Stato e allarmi", optional_block=True),
        peimar_telemetry_point("pv3_fault_voltage_v", "Guasto tensione FV 3", "input", 0x42E, 1, "uint16", scale=0.1, unit="V", section="Stato e allarmi", optional_block=True),
        peimar_telemetry_point("manager_faults", "Fault manager", "input", 0x42F, 1, "uint16", section="Stato e allarmi", optional_block=True, bitmask_labels=PEIMAR_MANAGER_FAULT_BITS),
        peimar_telemetry_point("feed_in_power_kw", "Potenza scambio rete", "input", 0x43B, 2, "int32_swapped", scale=0.001, unit="kW", section="Potenza", optional_block=True),
        peimar_telemetry_point("feed_in_energy_kwh", "Energia immessa", "input", 0x43D, 2, "uint32_swapped", scale=0.01, unit="kWh", section="Contatori", optional_block=True),
        peimar_telemetry_point("consume_energy_kwh", "Energia prelevata", "input", 0x43F, 2, "uint32_swapped", scale=0.01, unit="kWh", section="Contatori", optional_block=True),
    ]


def build_peimar_commands() -> list[InverterPoint]:
    return [
        peimar_command_point("unlock_password", "Password sblocco", 0x600, "uint16", section="Sicurezza"),
        peimar_command_point("checking_time_write_s", "Tempo connessione", 0x602, "uint16", unit="s", section="Protezioni rete", min_value=0, max_value=600),
        peimar_command_point("vac_uvp_2_write_v", "Sottotensione rete 2", 0x603, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_command_point("vac_ovp_2_write_v", "Sovratensione rete 2", 0x604, "uint16", scale=0.1, unit="V", section="Protezioni rete"),
        peimar_command_point("fac_ufp_2_write_hz", "Sottofrequenza 2", 0x605, "uint16", scale=0.01, unit="Hz", section="Protezioni rete"),
        peimar_command_point("fac_ofp_2_write_hz", "Sovrafrequenza 2", 0x606, "uint16", scale=0.01, unit="Hz", section="Protezioni rete"),
        peimar_command_point("safety_profile_write", "Profilo sicurezza", 0x607, "uint16", section="Sicurezza"),
        peimar_command_point("power_limit_pct", "Limite potenza attiva", 0x60F, "uint16", unit="%", section="Controllo potenza", min_value=0, max_value=100),
        peimar_command_point("remote_control", "Comando remoto", 0x610, "uint16", section="Controllo potenza", min_value=0, max_value=1),
        peimar_command_point("fix_q_power_var", "Q fisso", 0x61F, "int16", unit="Var", section="Controllo reattivo"),
        peimar_command_point("qcurve_set_mode_write", "Modalita controllo reattivo", 0x626, "uint16", section="Controllo reattivo", min_value=0, max_value=5),
        peimar_command_point("qcurve_set_pf_write", "Setpoint power factor", 0x627, "uint16", scale=0.01, section="Controllo reattivo"),
        peimar_command_point("set_ac_active_power_w", "Setpoint potenza attiva", 0x638, "uint16", unit="W", section="Controllo potenza"),
        peimar_command_point("grid_services_enable_write", "Servizi di rete", 0x639, "uint16", section="Controllo potenza"),
        peimar_command_point("reconnection_time_write_s", "Tempo riconnessione", 0x63F, "uint16", unit="s", section="Protezioni rete", min_value=10, max_value=1000),
        peimar_command_point("meter_enable_write", "Abilitazione contatore", 0x660, "uint16", section="Controllo impianto", min_value=0, max_value=1),
        peimar_command_point("lease_mode_write", "Lease mode", 0x661, "uint16", section="Controllo impianto", min_value=0, max_value=1),
        peimar_command_point("external_signal_write", "Segnale esterno", 0x662, "uint16", section="Controllo impianto", min_value=0, max_value=1),
        peimar_command_point("external_failed_write", "Errore segnale esterno", 0x663, "uint16", section="Controllo impianto", min_value=0, max_value=1),
        peimar_command_point("rs485_address_write", "Indirizzo RS485", 0x664, "uint16", section="Controllo impianto", min_value=1, max_value=255),
    ]


def build_peimar_models(protocol: str, transport: str) -> list[InverterModel]:
    if protocol == "modbus_rtu":
        defaults = {
            "port": "COM1",
            "slave_id": 1,
            "baud_rate": 9600,
            "parity": "N",
            "stop_bits": 1,
            "byte_size": 8,
            "timeout_seconds": 1,
            "retries": 1,
            "poll_interval_seconds": 15,
            "inter_request_delay_ms": 1000,
            "test_register": 0x40F,
            "test_count": 1,
            "test_function": "input",
        }
    else:
        defaults = {
            "host": "192.168.1.170",
            "port": 502,
            "unit_id": 1,
            "timeout_seconds": 1,
            "retries": 1,
            "poll_interval_seconds": 15,
            "test_register": 0x40F,
            "test_count": 1,
            "test_function": "input",
        }

    telemetry = build_peimar_telemetry()
    commands = build_peimar_commands()

    return [
        InverterModel(
            brand="Peimar",
            model=model,
            protocol=protocol,
            transport=transport,
            defaults=defaults,
            features=[
                "telemetria trifase",
                "ingressi fv multipli",
                "controllo protezioni rete",
                "bitmask fault inverter",
                "misure export opzionali",
            ],
            telemetry_points=telemetry,
            command_points=commands,
        )
        for model in PEIMAR_MODELS
    ]
