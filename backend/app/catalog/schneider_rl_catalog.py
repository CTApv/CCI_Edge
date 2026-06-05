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
) -> InverterPoint:
    protocol_meta: dict[str, object] = {"section": section}
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map

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
        length=1,
        datatype=datatype,
        scale=scale,
        unit=unit,
        writable=True,
        protocol_meta=protocol_meta,
    )


RL_MODEL_SPECS = [
    ("Conext RL 3000", 30.0, 17.0, 3.15),
    ("Conext RL 3000 E-S", 30.0, 17.0, 3.15),
    ("Conext RL 4000", 40.0, 23.0, 4.20),
    ("Conext RL 4000 E-S", 40.0, 23.0, 4.20),
    ("Conext RL 5000", 50.0, 28.0, 5.25),
    ("Conext RL 5000 E-S", 50.0, 28.0, 5.25),
]

SCHNEIDER_RL_OPERATIONAL_MODE_MAP = {
    0x0002: "Riconnessione",
    0x0003: "Online",
    0x0014: "Standby",
    0x0015: "Nessun DC",
    0x0016: "Allarme",
}

SCHNEIDER_RL_REACTIVE_POWER_MODE_MAP = {
    0: "Disabilitato",
    1: "Cosphi fisso",
    2: "Cosphi in funzione di P",
    3: "kVAr fisso",
    4: "kVAr in funzione di U",
}

SCHNEIDER_RL_POWER_REFERENCE_MODE_MAP = {
    0: "Potenza nominale inverter",
    1: "Potenza attuale inverter",
}

SCHNEIDER_RL_MULTIFUNCTION_RELAY_MODE_MAP = {
    0: "Disabilitato",
    1: "Fault o error o warning",
    2: "Produzione potenza",
    3: "Controllo carico esterno",
    4: "Controllo ventole esterne",
}

SCHNEIDER_RL_POWER_PRODUCTION_RELAY_MAP = {
    0: "Disabilitato",
    1: "Abilitato",
}

SCHNEIDER_RL_MODE_REGISTERS_MAP = {
    0: "Off",
    1: "Graph-A",
    2: "Graph-B",
}

SCHNEIDER_RL_ACTUAL_RATED_POWER_MAP = {
    0: "Potenza attuale",
    1: "Potenza nominale",
}

SCHNEIDER_RL_ACTIVE_POWER_FREQUENCY_MODE_MAP = {
    0: "Off",
    1: "Abilitato",
}

SCHNEIDER_RL_FAULT_CODE_MAP = {
    0: "No alarm",
    2402: "AC frequency high",
    2401: "AC frequency low",
    2440: "Grid quality",
    2110: "HW connect fail",
    2450: "No grid",
    2406: "AC voltage low",
    2407: "AC voltage high",
    2606: "PV voltage high",
    2403: "Slow over frequency",
    2404: "Slow under frequency",
    2408: "Slow under voltage",
    2616: "Isolation impedance error",
    6627: "PV OC voltage low",
    701: "DC injection",
    84: "Thermal condition OTP",
    32: "Thermal sensor 1",
    80: "Thermal condition LTP",
    103: "Thermal sensor 2",
    104: "Thermal sensor 3",
    105: "Thermal sensor 4",
    10: "AC switch response",
    120: "Analog input bias 1",
    121: "Analog input bias 2",
    122: "Analog input bias 3",
    123: "Analog input bias 4",
    124: "Analog input bias 5",
    130: "HW efficiency",
    95: "HW COMM2",
    195: "HW COMM1",
    702: "Ground current high",
    140: "RCMU fault",
    150: "Relay test short",
    151: "Relay test open",
    601: "DC overvoltage",
    460: "AC current high",
    31: "Current sensor",
    461: "AC overcurrent",
    160: "HW ZC fail",
    620: "DC overcurrent PV1",
    621: "DC overcurrent PV2",
}


def build_schneider_rl_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("product_model_designation", "Modello prodotto", 0x0001, 9, "ascii_string", section="Identificazione"),
        telemetry_point("serial_number", "Seriale", 0x0014, 10, "ascii_string", section="Identificazione"),
        telemetry_point("software_part_number_a", "Part number software A", 0x0082, 10, "ascii_string", section="Identificazione"),
        telemetry_point("software_part_number_b", "Part number software B", 0x0096, 10, "ascii_string", section="Identificazione"),
        telemetry_point("software_part_number_c", "Part number software C", 0x00AA, 10, "ascii_string", section="Identificazione"),
        telemetry_point("total_energy_kwh", "Energia totale", 0x0802, 2, "uint32", scale=0.1, unit="kWh", section="Contatori", summary_metric="total_energy_kwh"),
        telemetry_point("daily_energy_kwh", "Energia oggi", 0x0804, 2, "uint32", scale=0.1, unit="kWh", section="Contatori", summary_metric="daily_energy_kwh"),
        telemetry_point("energy_day_minus_1_kwh", "Energia ieri", 0x0806, 2, "uint32", scale=0.1, unit="kWh", section="Contatori"),
        telemetry_point("energy_day_minus_2_kwh", "Energia giorno -2", 0x0808, 2, "uint32", scale=0.1, unit="kWh", section="Contatori"),
        telemetry_point("energy_day_minus_3_kwh", "Energia giorno -3", 0x080A, 2, "uint32", scale=0.1, unit="kWh", section="Contatori"),
        telemetry_point("energy_day_minus_4_kwh", "Energia giorno -4", 0x080C, 2, "uint32", scale=0.1, unit="kWh", section="Contatori"),
        telemetry_point("energy_day_minus_5_kwh", "Energia giorno -5", 0x080E, 2, "uint32", scale=0.1, unit="kWh", section="Contatori"),
        telemetry_point("energy_day_minus_6_kwh", "Energia giorno -6", 0x0810, 2, "uint32", scale=0.1, unit="kWh", section="Contatori"),
        telemetry_point("operating_hours_h", "Ore operative", 0x081E, 2, "uint32", unit="h", section="Contatori"),
        telemetry_point("status", "Stato operativo", 0x1700, 1, "uint16", section="Stato e allarmi", summary_metric="status", enum_map=SCHNEIDER_RL_OPERATIONAL_MODE_MAP),
        telemetry_point("temperature_control_board_c", "Temperatura control board", 0x1701, 1, "int16", scale=0.1, unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("temperature_boost_module_1_c", "Temperatura boost module 1", 0x1702, 1, "int16", scale=0.1, unit="C", section="Termico"),
        telemetry_point("temperature_boost_module_2_c", "Temperatura boost module 2", 0x1703, 1, "int16", scale=0.1, unit="C", section="Termico"),
        telemetry_point("temperature_inverter_module_c", "Temperatura inverter module", 0x1704, 1, "int16", scale=0.1, unit="C", section="Termico"),
        telemetry_point("grid_current_a", "Corrente rete", 0x1705, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("apparent_power_kva", "Potenza apparente", 0x17F1, 1, "int16", scale=0.1, unit="kVA", section="Potenza"),
        telemetry_point("reactive_power_kvar", "Potenza reattiva", 0x17F4, 1, "int16", scale=0.1, unit="kVAr", section="Potenza"),
        telemetry_point("grid_voltage_v", "Tensione rete", 0x17F8, 1, "int16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("phase_a_current_a", "Corrente fase A", 0x17FB, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("active_power_kw", "Potenza attiva", 0x181B, 1, "int16", scale=0.1, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("pv1_voltage_v", "Tensione FV 1", 0x17FF, 1, "int16", scale=0.1, unit="V", section="Ingresso FV"),
        telemetry_point("pv1_current_a", "Corrente FV 1", 0x1800, 1, "int16", scale=0.1, unit="A", section="Ingresso FV"),
        telemetry_point("pv1_power_kw", "Potenza FV 1", 0x1801, 1, "int16", scale=0.1, unit="kW", section="Ingresso FV"),
        telemetry_point("grid_frequency_hz", "Frequenza rete", 0x1802, 1, "uint16", scale=0.1, unit="Hz", section="Rete AC"),
        telemetry_point("dc_voltage_v", "Tensione DC", 0x180D, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV"),
        telemetry_point("pv2_voltage_v", "Tensione FV 2", 0x1829, 1, "int16", scale=0.1, unit="V", section="Ingresso FV"),
        telemetry_point("pv2_current_a", "Corrente FV 2", 0x182A, 1, "int16", scale=0.1, unit="A", section="Ingresso FV"),
        telemetry_point("pv2_power_kw", "Potenza FV 2", 0x182F, 1, "int16", scale=0.1, unit="kW", section="Ingresso FV"),
        telemetry_point("fault_code", "Codice allarme", 0x1828, 1, "uint16", section="Stato e allarmi", enum_map=SCHNEIDER_RL_FAULT_CODE_MAP),
        telemetry_point("power_ramp_up_recover_time_s", "Tempo recupero power ramp", 0xF9ED, 1, "uint16", scale=0.01, unit="s", section="Controllo potenza"),
        telemetry_point("reactive_power_mode", "Modalita potenza reattiva", 0xFA60, 1, "uint16", section="Controllo reattivo", enum_map=SCHNEIDER_RL_REACTIVE_POWER_MODE_MAP),
        telemetry_point("active_power_management_mode", "Modalita gestione potenza attiva", 0xFAF0, 1, "uint16", section="Controllo potenza", enum_map=SCHNEIDER_RL_POWER_REFERENCE_MODE_MAP),
        telemetry_point("active_power_management_percentage", "Percentuale gestione potenza attiva", 0xFAF1, 1, "uint16", unit="%", section="Controllo potenza"),
        telemetry_point("multifunction_relay_mode", "Modalita relay multifunzione", 0xFAF5, 1, "uint16", section="Relay multifunzione", enum_map=SCHNEIDER_RL_MULTIFUNCTION_RELAY_MODE_MAP),
        telemetry_point("multifunction_fault_code_1", "Relay fault code 1", 0xFAF6, 1, "uint16", section="Relay multifunzione"),
        telemetry_point("multifunction_fault_code_2", "Relay fault code 2", 0xFAF7, 1, "uint16", section="Relay multifunzione"),
        telemetry_point("multifunction_fault_code_3", "Relay fault code 3", 0xFAF8, 1, "uint16", section="Relay multifunzione"),
        telemetry_point("multifunction_power_production", "Relay power production", 0xFAF9, 1, "uint16", section="Relay multifunzione", enum_map=SCHNEIDER_RL_POWER_PRODUCTION_RELAY_MAP),
        telemetry_point("multifunction_output_power_kw", "Relay soglia potenza", 0xFAFA, 1, "uint16", scale=0.01, unit="kW", section="Relay multifunzione"),
        telemetry_point("multifunction_duration_min", "Relay durata", 0xFAFB, 1, "uint16", unit="min", section="Relay multifunzione"),
        telemetry_point("multifunction_min_duration_min", "Relay durata minima", 0xFAFC, 1, "uint16", unit="min", section="Relay multifunzione"),
        telemetry_point("multifunction_temperature_1_c", "Relay temperatura 1", 0xFAFD, 1, "int16", scale=0.1, unit="C", section="Relay multifunzione"),
        telemetry_point("multifunction_temperature_2_c", "Relay temperatura 2", 0xFAFE, 1, "int16", scale=0.1, unit="C", section="Relay multifunzione"),
    ]


def build_schneider_rl_commands(
    *,
    max_active_power_kw: float,
    max_reactive_power_kvar: float,
    max_relay_output_power_kw: float,
) -> list[InverterPoint]:
    return [
        command_point("power_ramp_up_recover_time_write_s", "Tempo recupero power ramp", 0xF9ED, "uint16", scale=0.01, unit="s", section="Controllo potenza", min_value=0, max_value=600),
        command_point("cosphi_lock_in_voltage_v", "Cosphi lock-in tensione", 0xF9EE, "uint16", scale=0.1, unit="V", section="Controllo reattivo", min_value=230.0, max_value=253.0),
        command_point("cosphi_lock_out_voltage_v", "Cosphi lock-out tensione", 0xF9EF, "uint16", scale=0.1, unit="V", section="Controllo reattivo", min_value=225.4, max_value=230.0),
        command_point("kvar_u_lock_in_power_pct", "kVAr(U) lock-in potenza", 0xF9F0, "uint16", unit="%", section="Controllo reattivo", min_value=10, max_value=100),
        command_point("kvar_u_lock_out_power_pct", "kVAr(U) lock-out potenza", 0xF9F1, "uint16", unit="%", section="Controllo reattivo", min_value=5, max_value=95),
        command_point("user_phase_angle_deg", "Angolo di fase utente", 0xF9FB, "int16", unit="deg", section="Controllo reattivo", min_value=-37, max_value=37),
        command_point("user_active_power_reference_kw", "Riferimento potenza attiva", 0xFA19, "uint16", scale=0.1, unit="kW", section="Controllo potenza", min_value=0, max_value=max_active_power_kw),
        command_point("user_reactive_power_reference_kvar", "Riferimento potenza reattiva", 0xFA1B, "int16", scale=0.1, unit="kVAr", section="Controllo reattivo", min_value=-max_reactive_power_kvar, max_value=max_reactive_power_kvar),
        command_point("lvrt_low_voltage_threshold_h_pct", "LVRT soglia alta", 0xFA25, "uint16", unit="%", section="Protezioni rete"),
        command_point("lvrt_fast_low_voltage_threshold_l_pct", "LVRT soglia bassa", 0xFA26, "uint16", unit="%", section="Protezioni rete"),
        command_point("reactive_power_mode_select", "Modalita potenza reattiva", 0xFA60, "uint16", section="Controllo reattivo", min_value=0, max_value=4, enum_map=SCHNEIDER_RL_REACTIVE_POWER_MODE_MAP),
        command_point("fixed_cosphi", "Cosphi fisso", 0xFA61, "int16", scale=0.01, section="Controllo reattivo", min_value=-1.0, max_value=1.0),
        command_point("cosphi_power_upper_limit", "Cosphi potenza limite alto", 0xFA62, "int16", scale=0.01, section="Controllo reattivo", min_value=-1.0, max_value=1.0),
        command_point("cosphi_power_lower_limit", "Cosphi potenza limite basso", 0xFA63, "int16", scale=0.01, section="Controllo reattivo", min_value=-1.0, max_value=1.0),
        command_point("cosphi_power_lower_pct", "Cosphi potenza bassa", 0xFA64, "uint16", unit="%", section="Controllo reattivo", min_value=0, max_value=100),
        command_point("cosphi_power_upper_pct", "Cosphi potenza alta", 0xFA65, "uint16", unit="%", section="Controllo reattivo", min_value=0, max_value=100),
        command_point("fixed_kvar_pct", "kVAr fisso", 0xFA66, "int16", unit="%", section="Controllo reattivo", min_value=-53, max_value=53),
        command_point("kvar_u_upper_limit_pct", "kVAr(U) limite alto", 0xFA67, "int16", unit="%", section="Controllo reattivo", min_value=-53, max_value=53),
        command_point("kvar_u_lower_limit_pct", "kVAr(U) limite basso", 0xFA68, "int16", unit="%", section="Controllo reattivo", min_value=-53, max_value=53),
        command_point("kvar_u_vmin_v", "kVAr(U) Vmin", 0xFA69, "uint16", scale=0.1, unit="V", section="Controllo reattivo", min_value=100.0, max_value=264.0),
        command_point("kvar_u_vmax_v", "kVAr(U) Vmax", 0xFA6A, "uint16", scale=0.1, unit="V", section="Controllo reattivo", min_value=100.0, max_value=264.0),
        command_point("kvar_u_uac_lower_limit_v", "kVAr(U) limite basso Uac", 0xFA6B, "uint16", scale=0.1, unit="V", section="Controllo reattivo", min_value=100.0, max_value=264.0),
        command_point("kvar_u_uac_upper_limit_v", "kVAr(U) limite alto Uac", 0xFA6C, "uint16", scale=0.1, unit="V", section="Controllo reattivo", min_value=100.0, max_value=264.0),
        command_point("kvar_u_hysteresis_v", "kVAr(U) isteresi", 0xFA6D, "uint16", scale=0.1, unit="V", section="Controllo reattivo", min_value=0, max_value=30.0),
        command_point("response_time_s", "Tempo risposta", 0xFA6E, "uint16", scale=0.01, unit="s", section="Controllo reattivo", min_value=0.01, max_value=60.0),
        command_point("active_power_frequency_mode_register", "Registro modalita P(f)", 0xFA6F, "uint16", section="Controllo potenza", min_value=0, max_value=2, enum_map=SCHNEIDER_RL_MODE_REGISTERS_MAP),
        command_point("actual_rated_power_mode", "Modalita potenza attuale o nominale", 0xFA70, "uint16", section="Controllo potenza", min_value=0, max_value=1, enum_map=SCHNEIDER_RL_ACTUAL_RATED_POWER_MAP),
        command_point("start_frequency_hz", "Frequenza avvio", 0xFA71, "uint16", scale=0.01, unit="Hz", section="Controllo potenza", min_value=47.0, max_value=63.0),
        command_point("stop_frequency_hz", "Frequenza stop", 0xFA72, "uint16", scale=0.01, unit="Hz", section="Controllo potenza", min_value=47.0, max_value=63.0),
        command_point("recover_frequency_hz", "Frequenza recovery", 0xFA73, "uint16", scale=0.01, unit="Hz", section="Controllo potenza", min_value=47.0, max_value=63.0),
        command_point("gradient_pct", "Gradiente", 0xFA74, "uint16", scale=0.1, unit="%", section="Controllo potenza", min_value=40.0, max_value=100.0),
        command_point("recovery_time_s", "Tempo recovery", 0xFA75, "uint16", unit="s", section="Controllo potenza", min_value=0, max_value=300),
        command_point("active_power_vs_frequency_mode", "Modalita potenza vs frequenza", 0xFA76, "uint16", section="Controllo potenza", min_value=0, max_value=1, enum_map=SCHNEIDER_RL_ACTIVE_POWER_FREQUENCY_MODE_MAP),
        command_point("k_factor", "K factor", 0xFA77, "uint16", section="Protezioni rete", min_value=0, max_value=10),
        command_point("dead_band_vh_pct", "Dead band Vh", 0xFA78, "uint16", unit="%", section="Protezioni rete", min_value=0, max_value=10),
        command_point("dead_band_vl_pct", "Dead band Vl", 0xFA79, "int16", unit="%", section="Protezioni rete", min_value=-10, max_value=0),
        command_point("time_1_s", "Time 1", 0xFA7A, "uint16", scale=0.01, unit="s", section="Protezioni rete", min_value=0, max_value=5.0),
        command_point("time_2_s", "Time 2", 0xFA7B, "uint16", scale=0.01, unit="s", section="Protezioni rete", min_value=0, max_value=5.0),
        command_point("time_3_s", "Time 3", 0xFA7C, "uint16", scale=0.01, unit="s", section="Protezioni rete", min_value=0, max_value=5.0),
        command_point("statism_pct", "Statism", 0xFA7D, "uint16", scale=0.1, unit="%", section="Controllo potenza", min_value=2.0, max_value=5.0),
        command_point("user_active_power_management_mode", "Modalita gestione potenza attiva", 0xFAF0, "uint16", section="Controllo potenza", min_value=0, max_value=1, enum_map=SCHNEIDER_RL_POWER_REFERENCE_MODE_MAP),
        command_point("user_active_power_management_percentage", "Percentuale gestione potenza attiva", 0xFAF1, "uint16", unit="%", section="Controllo potenza", min_value=0, max_value=100),
        command_point("multifunction_relay_mode", "Modalita relay multifunzione", 0xFAF5, "uint16", section="Relay multifunzione", min_value=0, max_value=4, enum_map=SCHNEIDER_RL_MULTIFUNCTION_RELAY_MODE_MAP),
        command_point("multifunction_fault_code_1", "Relay fault code 1", 0xFAF6, "uint16", section="Relay multifunzione"),
        command_point("multifunction_fault_code_2", "Relay fault code 2", 0xFAF7, "uint16", section="Relay multifunzione"),
        command_point("multifunction_fault_code_3", "Relay fault code 3", 0xFAF8, "uint16", section="Relay multifunzione"),
        command_point("multifunction_power_production", "Relay power production", 0xFAF9, "uint16", section="Relay multifunzione", min_value=0, max_value=1, enum_map=SCHNEIDER_RL_POWER_PRODUCTION_RELAY_MAP),
        command_point("multifunction_output_power_kw", "Relay soglia potenza", 0xFAFA, "uint16", scale=0.01, unit="kW", section="Relay multifunzione", min_value=0, max_value=max_relay_output_power_kw),
        command_point("multifunction_duration_min", "Relay durata", 0xFAFB, "uint16", unit="min", section="Relay multifunzione"),
        command_point("multifunction_min_duration_min", "Relay durata minima", 0xFAFC, "uint16", unit="min", section="Relay multifunzione"),
        command_point("multifunction_temperature_1_c", "Relay temperatura 1", 0xFAFD, "int16", scale=0.1, unit="C", section="Relay multifunzione"),
        command_point("multifunction_temperature_2_c", "Relay temperatura 2", 0xFAFE, "int16", scale=0.1, unit="C", section="Relay multifunzione"),
    ]


def build_schneider_rl_models(protocol: str, transport: str) -> list[InverterModel]:
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
            "max_registers_per_request": 60,
            "test_register": 0x1700,
            "test_count": 1,
            "test_function": "holding",
        }
    else:
        defaults = {
            "host": "192.168.1.170",
            "port": 502,
            "unit_id": 1,
            "timeout_seconds": 2,
            "retries": 1,
            "poll_interval_seconds": 15,
            "max_registers_per_request": 60,
            "test_register": 0x1700,
            "test_count": 1,
            "test_function": "holding",
        }

    telemetry = build_schneider_rl_telemetry()

    models: list[InverterModel] = []
    for model_name, max_active_power_kw, max_reactive_power_kvar, max_relay_output_power_kw in RL_MODEL_SPECS:
        models.append(
            InverterModel(
                brand="Schneider",
                model=model_name,
                protocol=protocol,
                transport=transport,
                defaults=defaults,
                features=[
                    "telemetria conext rl",
                    "rtu nativo",
                    "tcp tramite gateway rs485 ethernet",
                    "controllo potenza attiva e reattiva",
                    "fc16 per scritture",
                    "relay multifunzione",
                ],
                telemetry_points=telemetry,
                command_points=build_schneider_rl_commands(
                    max_active_power_kw=max_active_power_kw,
                    max_reactive_power_kvar=max_reactive_power_kvar,
                    max_relay_output_power_kw=max_relay_output_power_kw,
                ),
            )
        )
    return models
