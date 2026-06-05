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
    section: str,
    visible: bool = True,
    summary_metric: str | None = None,
    enum_map: dict[int, str] | None = None,
    bitmask_labels: dict[int, str] | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {"section": section}
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map
    if bitmask_labels is not None:
        protocol_meta["bitmask_labels"] = bitmask_labels

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
    enum_map: dict[int, str] | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {"section": section}
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


def legacy_addr(document_register: int) -> int:
    return document_register - 1


SIEL_BRAND = "SIAC SIEL"

SIEL_ENABLE_15_170_MAP = {
    15: "Disabilitato",
    170: "Abilitato",
}

SIEL_QP_FUNCTION_MAP = {
    15: "Disabilitato",
    160: "Curva lineare",
    170: "Curva max",
    180: "Cosphi fisso locale",
    190: "Cosphi fisso remoto",
}

SIEL_QVAC_FUNCTION_MAP = {
    15: "Disabilitato",
    160: "Curva con isteresi",
    170: "Curva lineare",
}

SIEL_REACTIVE_Q_ENABLE_MAP = {
    15: "Disabilitato",
    170: "Abilitato",
}

SIEL_DSPX1500_REACTIVE_Q_ENABLE_MAP = {
    15: "Disabilitato",
    170: "Abilitato",
    180: "Abilitato anche per reattivo notturno",
}

SIEL_REMOTE_DISABLE_MAP = {
    15: "Disabilitazione remota non attiva",
    170: "Disabilitazione remota attiva",
}

SIEL_DSP_STATUS_1_BITS = {
    0: "Limitazione potenza AC per sovratemperatura",
    1: "Desaturazione IGBT inverter",
    2: "Sovracorrente inverter",
    3: "Inverter fault",
    4: "Frequenza rete fuori limiti",
    5: "Tensione rete fuori limiti",
    6: "Sovratemperatura interna",
    7: "Problemi comunicazione Signalling-DSP",
    8: "Teleruttore rete chiuso",
    12: "Irraggiamento insufficiente",
    13: "Rete 50 Hz",
    14: "Errore EEPROM",
    15: "Modo manuale",
}

SIEL_DSP_STATUS_2_BITS = {
    0: "Perdita isolamento",
    2: "Intervento fusibile polo a terra",
    4: "Mancanza comunicazione CAN",
    5: "Emergency power off",
    6: "Macchina abilitata",
    7: "Presenza operatore umano",
    8: "Inverter in generazione",
    9: "Inverter abilitato",
    10: "Inverter disabilitato",
    11: "Intervento protezione esterna",
    13: "Sovratensione DC ingresso convertitore",
}

SIEL_DSP_STATUS_3_BITS = {
    0: "Contattore VDE 0126 aperto",
    1: "Limitazione potenza da remoto attiva",
    2: "Anomalia teleruttore",
    3: "Anomalia teleruttore A",
    4: "Anomalia teleruttore B",
    5: "Sbilanciamento correnti inverter rete",
    6: "Regolazione remota smart grid attiva",
}

SIEL_DSPX1500_STATUS_1_BITS = {
    1: "Inverter in generazione",
    2: "Inverter abilitato",
    3: "Inverter disabilitato",
    4: "Contattore AC chiuso",
    5: "Limitazione potenza per temperatura magnetico",
    6: "Limitazione potenza per temperatura moduli",
    7: "Limitazione potenza da remoto",
    8: "Regolazione remota smart grid attiva",
    9: "Rete 60 Hz",
    10: "Controllo manuale",
    11: "Start da esterno non presente",
    12: "Intervento scaricatore DC",
    13: "Intervento scaricatore AC",
    14: "Batteria principale in scarica",
    15: "Batteria principale in avaria",
}

SIEL_DSPX1500_STATUS_2_BITS = {
    0: "Allarme macchina",
    1: "Frequenza rete fuori limiti",
    2: "Tensione rete fuori limiti",
    3: "Irraggiamento insufficiente",
    4: "Errore EEPROM",
    5: "Basso isolamento campo FV",
    6: "Intervento fusibile polo a terra",
    7: "Errore comunicazione IO board",
    8: "Errore comunicazione driver A",
    9: "Errore comunicazione driver B",
    10: "Errore comunicazione bus parallelo",
    11: "Tensione celle elevata",
    12: "Sovratensione DC HW semibanco basso",
    13: "Sovratensione DC HW semibanco alto",
    14: "Sovratensione DC SW semibanco basso",
    15: "Sovratensione DC SW semibanco alto",
}

SIEL_DSPX1500_STATUS_3_BITS = {
    0: "Emergency power off",
    1: "Anomalia teleruttore A",
    2: "Anomalia teleruttore B",
    3: "Anomalia sezionatore DC",
    4: "Anomalia circuito precarica",
    5: "Anomalia alimentazione ausiliaria",
    6: "Sbilanciamento correnti inverter",
    11: "Preallarme perdita isolamento campo FV",
    12: "Riduzione potenza attiva P(VAC) abilitata",
    13: "Corto circuito ingresso DC",
    14: "Piu di un master presente",
}

SIEL_DSPX1500_STATUS_4_BITS = {
    0: "Sovracorrente fase L1 modulo A",
    1: "Sovracorrente fase L2 modulo A",
    2: "Sovracorrente fase L3 modulo A",
    3: "Sovracorrente hardware modulo A",
    4: "Sovracorrente fase L1 modulo B",
    5: "Sovracorrente fase L2 modulo B",
    6: "Sovracorrente fase L3 modulo B",
    7: "Sovracorrente hardware modulo B",
    8: "Sovratemperatura magnetici A",
    9: "Sovratemperatura magnetici B",
    10: "Sensore temperatura moduli A disconnesso",
    11: "Sensore temperatura moduli B disconnesso",
    12: "Sensore temperatura magnetici A disconnesso",
    13: "Sensore temperatura magnetici B disconnesso",
    14: "Sensore temperatura interna disconnesso",
}

SIEL_DSPX1500_STATUS_5_BITS = {
    0: "Allarme R-HI modulo A",
    1: "Allarme R-LO modulo A",
    2: "Allarme S-HI modulo A",
    3: "Allarme S-LO modulo A",
    4: "Allarme T-HI modulo A",
    5: "Allarme T-LO modulo A",
    6: "Sovratemperatura modulo potenza A",
    7: "Allarme driver A",
    8: "Allarme R-HI modulo B",
    9: "Allarme R-LO modulo B",
    10: "Allarme S-HI modulo B",
    11: "Allarme S-LO modulo B",
    12: "Allarme T-HI modulo B",
    13: "Allarme T-LO modulo B",
    14: "Sovratemperatura modulo potenza B",
    15: "Allarme driver B",
}

SIEL_SRT_STATUS_MAP = {
    0x0000: "Standby senza tensione DC",
    0x0001: "Standby con DC sotto soglia",
    0x0002: "Standby self-check",
    0x0100: "On-grid",
    0x0101: "Prestart",
    0x0200: "Fault",
    0x0300: "Off",
}

SIEL_SRT_ALARM_WORD_1_BITS = {
    0: "Tensione rete fuori limiti",
    1: "Frequenza rete fuori limiti",
    3: "Sovracorrente inverter",
    4: "Sovratensione inverter",
}

SIEL_SRT_ALARM_WORD_2_BITS = {
    0: "Anomalia isolamento",
    1: "Sovratensione DC bus",
    2: "DC bus non bilanciato",
    7: "Anomalia comunicazione interna",
    12: "Limitazione potenza per sovratemperatura",
    13: "Sovratemperatura interna",
    14: "Sovratemperatura modulo potenza",
    15: "Sovratemperatura dissipatore",
}

SIEL_SRT_POWER_CONTROL_MODE_MAP = {
    0: "Regolazione disabilitata",
    1: "Valore assoluto",
    2: "Valore percentuale",
    3: "Power factor",
}

SIEL_DSP_GENERIC_MODELS = [
    "Soleil TL 500",
    "Soleil DSPX TRL (10K...250kW)",
]

SIEL_DSPX_HIGH_POWER_MODELS = [
    "Soleil DSPX TLH - 280 (90kW...660kW)",
    "Soleil DSPX TLH - 380 (up to 833kW)",
]

SIEL_SRT_SPX_MODELS = [
    ("Soleil SRT S2 8-25kW", 9600, 25.0),
    ("Soleil SRT S2 30-40kW", 9600, 40.0),
    ("Soleil SRT-3F 100-125kW", 9600, 125.0),
    ("Soleil SPX-3F 200-250kW", 115200, 250.0),
    ("Soleil SPX-B-H X2 & X2P 200-250kW", 115200, 250.0),
    ("Soleil SPX-B-H X2 & X2P 300-350kW", 115200, 350.0),
]


def build_siel_dsp_generic_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("status_alarms_1", "Stati allarmi 1", "holding", legacy_addr(2001), 1, "uint16", section="Stato e allarmi", bitmask_labels=SIEL_DSP_STATUS_1_BITS),
        telemetry_point("status_alarms_2", "Stati allarmi 2", "holding", legacy_addr(2002), 1, "uint16", section="Stato e allarmi", bitmask_labels=SIEL_DSP_STATUS_2_BITS),
        telemetry_point("grid_voltage_rn_v", "Tensione rete fase R-N", "holding", legacy_addr(2003), 1, "uint16", unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_sn_v", "Tensione rete fase S-N", "holding", legacy_addr(2004), 1, "uint16", unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_tn_v", "Tensione rete fase T-N", "holding", legacy_addr(2005), 1, "uint16", unit="V", section="Rete AC"),
        telemetry_point("grid_current_r_a", "Corrente rete fase R", "holding", legacy_addr(2006), 1, "uint16", unit="A", section="Rete AC"),
        telemetry_point("grid_current_s_a", "Corrente rete fase S", "holding", legacy_addr(2007), 1, "uint16", unit="A", section="Rete AC"),
        telemetry_point("grid_current_t_a", "Corrente rete fase T", "holding", legacy_addr(2008), 1, "uint16", unit="A", section="Rete AC"),
        telemetry_point("active_power_kw", "Potenza immessa in rete", "holding", legacy_addr(2009), 1, "int16", unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("internal_temperature_c", "Temperatura interna", "holding", legacy_addr(2010), 1, "int16", unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("cell_temperature_c", "Temperatura celle", "holding", legacy_addr(2011), 1, "int16", unit="C", section="Ingresso DC"),
        telemetry_point("dc_voltage_v", "Tensione celle", "holding", legacy_addr(2012), 1, "uint16", unit="V", section="Ingresso DC"),
        telemetry_point("dc_current_a", "Corrente celle", "holding", legacy_addr(2013), 1, "int16", unit="A", section="Ingresso DC"),
        telemetry_point("irradiance_horizontal_w_m2", "Irraggiamento orizzontale", "holding", legacy_addr(2014), 1, "uint16", unit="W/m2", section="Sensori"),
        telemetry_point("irradiance_tilted_w_m2", "Irraggiamento inclinato", "holding", legacy_addr(2015), 1, "uint16", unit="W/m2", section="Sensori"),
        telemetry_point("total_energy_kwh", "Energia totale", "holding", legacy_addr(2016), 2, "siel_energy_kwh_pair", unit="kWh", section="Contatori", summary_metric="total_energy_kwh"),
        telemetry_point("operating_hours_h", "Ore di funzionamento", "holding", legacy_addr(2018), 2, "uint32", unit="h", section="Contatori"),
        telemetry_point("analog_input_pct", "Input analogico", "holding", legacy_addr(2020), 1, "uint16", unit="%", section="I/O"),
        telemetry_point("analog_output_pct", "Output analogico", "holding", legacy_addr(2021), 1, "uint16", unit="%", section="I/O"),
        telemetry_point("status_alarms_3", "Stati allarmi 3", "holding", legacy_addr(2022), 1, "uint16", section="Stato e allarmi", bitmask_labels=SIEL_DSP_STATUS_3_BITS),
        telemetry_point("reactive_power_kvar", "Potenza reattiva immessa", "holding", legacy_addr(2040), 1, "int16", unit="kVAr", section="Potenza"),
    ]


def build_siel_dsp_generic_commands() -> list[InverterPoint]:
    return [
        command_point("pf_derating_function", "Funzione P(f)", legacy_addr(2031), "uint16", section="Controllo potenza", min_value=15, max_value=170, enum_map=SIEL_ENABLE_15_170_MAP),
        command_point("remote_power_limitation_pct", "Limitazione potenza remota", legacy_addr(2032), "uint16", unit="%", section="Controllo potenza", min_value=0, max_value=100),
        command_point("qp_function", "Funzione Q(P)", legacy_addr(2033), "uint16", section="Controllo reattivo", min_value=15, max_value=190, enum_map=SIEL_QP_FUNCTION_MAP),
        command_point("qvac_function", "Funzione Q(Vac)", legacy_addr(2034), "uint16", section="Controllo reattivo", min_value=15, max_value=170, enum_map=SIEL_QVAC_FUNCTION_MAP),
        command_point("enable_reactive_q_setpoint", "Abilitazione setpoint Q", legacy_addr(2035), "uint16", section="Controllo reattivo", min_value=15, max_value=170, enum_map=SIEL_REACTIVE_Q_ENABLE_MAP),
        command_point("reactive_q_setpoint_pct", "Setpoint potenza reattiva", legacy_addr(2036), "int16", scale=0.01, unit="%", section="Controllo reattivo", min_value=-100.0, max_value=100.0),
        command_point("pdc_voltage_l1_kv", "Tensione L1 al PDC", legacy_addr(2037), "uint16", scale=0.01, unit="kV", section="Punto di consegna"),
        command_point("pdc_voltage_l2_kv", "Tensione L2 al PDC", legacy_addr(2038), "uint16", scale=0.01, unit="kV", section="Punto di consegna"),
        command_point("pdc_voltage_l3_kv", "Tensione L3 al PDC", legacy_addr(2039), "uint16", scale=0.01, unit="kV", section="Punto di consegna"),
        command_point("remote_controller_keep_alive", "Keep alive controllo remoto", legacy_addr(2041), "uint16", section="Controllo remoto", min_value=0, max_value=100),
        command_point("active_power_ramp_up_min", "Rampa potenza attiva", legacy_addr(2042), "uint16", unit="min", section="Controllo potenza", min_value=0, max_value=10),
    ]


def build_siel_dspx_high_power_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("grid_voltage_l1n_v", "Tensione rete L1-N", "holding", legacy_addr(2003), 1, "uint16", unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_l2n_v", "Tensione rete L2-N", "holding", legacy_addr(2004), 1, "uint16", unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_l3n_v", "Tensione rete L3-N", "holding", legacy_addr(2005), 1, "uint16", unit="V", section="Rete AC"),
        telemetry_point("grid_current_l1_a", "Corrente rete L1", "holding", legacy_addr(2006), 1, "uint16", unit="A", section="Rete AC"),
        telemetry_point("grid_current_l2_a", "Corrente rete L2", "holding", legacy_addr(2007), 1, "uint16", unit="A", section="Rete AC"),
        telemetry_point("grid_current_l3_a", "Corrente rete L3", "holding", legacy_addr(2008), 1, "uint16", unit="A", section="Rete AC"),
        telemetry_point("active_power_kw", "Potenza immessa in rete", "holding", legacy_addr(2009), 1, "int16", unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("internal_temperature_c", "Temperatura interna", "holding", legacy_addr(2010), 1, "int16", unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("cell_temperature_c", "Temperatura celle", "holding", legacy_addr(2011), 1, "int16", unit="C", section="Ingresso DC"),
        telemetry_point("dc_voltage_v", "Tensione celle", "holding", legacy_addr(2012), 1, "uint16", unit="V", section="Ingresso DC"),
        telemetry_point("dc_current_a", "Corrente celle", "holding", legacy_addr(2013), 1, "int16", unit="A", section="Ingresso DC"),
        telemetry_point("irradiance_tilted_w_m2", "Irraggiamento inclinato", "holding", legacy_addr(2015), 1, "uint16", unit="W/m2", section="Sensori"),
        telemetry_point("total_energy_kwh", "Energia totale", "holding", legacy_addr(2016), 2, "siel_energy_kwh_pair", unit="kWh", section="Contatori", summary_metric="total_energy_kwh"),
        telemetry_point("operating_hours_h", "Ore di funzionamento", "holding", legacy_addr(2018), 2, "uint32", unit="h", section="Contatori"),
        telemetry_point("status_alarms_1", "Stati allarmi 1", "holding", legacy_addr(2023), 1, "uint16", section="Stato e allarmi", bitmask_labels=SIEL_DSPX1500_STATUS_1_BITS),
        telemetry_point("status_alarms_2", "Stati allarmi 2", "holding", legacy_addr(2024), 1, "uint16", section="Stato e allarmi", bitmask_labels=SIEL_DSPX1500_STATUS_2_BITS),
        telemetry_point("status_alarms_3", "Stati allarmi 3", "holding", legacy_addr(2025), 1, "uint16", section="Stato e allarmi", bitmask_labels=SIEL_DSPX1500_STATUS_3_BITS),
        telemetry_point("status_alarms_4", "Stati allarmi 4", "holding", legacy_addr(2026), 1, "uint16", section="Stato e allarmi", bitmask_labels=SIEL_DSPX1500_STATUS_4_BITS),
        telemetry_point("status_alarms_5", "Stati allarmi 5", "holding", legacy_addr(2027), 1, "uint16", section="Stato e allarmi", bitmask_labels=SIEL_DSPX1500_STATUS_5_BITS),
        telemetry_point("reactive_power_kvar", "Potenza reattiva immessa", "holding", legacy_addr(2040), 1, "int16", unit="kVAr", section="Potenza"),
    ]


def build_siel_dspx_high_power_commands() -> list[InverterPoint]:
    return [
        command_point("pf_derating_function", "Funzione P(f)", legacy_addr(2031), "uint16", section="Controllo potenza", min_value=15, max_value=170, enum_map=SIEL_ENABLE_15_170_MAP),
        command_point("remote_power_limitation_pct", "Limitazione potenza remota", legacy_addr(2032), "uint16", scale=0.01, unit="%", section="Controllo potenza", min_value=0, max_value=100),
        command_point("qp_function", "Funzione Q(P)", legacy_addr(2033), "uint16", section="Controllo reattivo", min_value=15, max_value=190, enum_map=SIEL_QP_FUNCTION_MAP),
        command_point("qvac_function", "Funzione Q(Vac)", legacy_addr(2034), "uint16", section="Controllo reattivo", min_value=15, max_value=170, enum_map=SIEL_QVAC_FUNCTION_MAP),
        command_point("enable_reactive_q_setpoint", "Abilitazione setpoint Q", legacy_addr(2035), "uint16", section="Controllo reattivo", min_value=15, max_value=180, enum_map=SIEL_DSPX1500_REACTIVE_Q_ENABLE_MAP),
        command_point("reactive_q_setpoint_pct", "Setpoint potenza reattiva", legacy_addr(2036), "int16", scale=0.01, unit="%", section="Controllo reattivo", min_value=-100.0, max_value=100.0),
        command_point("pdc_voltage_l1_kv", "Tensione L1 al PDC", legacy_addr(2037), "uint16", scale=0.01, unit="kV", section="Punto di consegna"),
        command_point("pdc_voltage_l2_kv", "Tensione L2 al PDC", legacy_addr(2038), "uint16", scale=0.01, unit="kV", section="Punto di consegna"),
        command_point("pdc_voltage_l3_kv", "Tensione L3 al PDC", legacy_addr(2039), "uint16", scale=0.01, unit="kV", section="Punto di consegna"),
        command_point("remote_controller_keep_alive", "Keep alive controllo remoto", legacy_addr(2041), "uint16", section="Controllo remoto", min_value=0, max_value=100),
        command_point("active_power_ramp_up_min", "Rampa potenza attiva in salita", legacy_addr(2042), "uint16", unit="min", section="Controllo potenza", min_value=0, max_value=10),
        command_point("active_power_ramp_down_s", "Rampa potenza attiva in discesa", legacy_addr(2043), "uint16", scale=0.01, unit="s", section="Controllo potenza"),
        command_point("remote_disable", "Disabilitazione remota", legacy_addr(2044), "uint16", section="Controllo remoto", min_value=15, max_value=170, enum_map=SIEL_REMOTE_DISABLE_MAP),
    ]


def build_siel_srt_spx_telemetry() -> list[InverterPoint]:
    telemetry: list[InverterPoint] = [
        telemetry_point("alarm_word_1", "Allarmi word 1", "holding", 11001, 1, "uint16", section="Stato e allarmi", bitmask_labels=SIEL_SRT_ALARM_WORD_1_BITS),
        telemetry_point("alarm_word_2", "Allarmi word 2", "holding", 11002, 1, "uint16", section="Stato e allarmi", bitmask_labels=SIEL_SRT_ALARM_WORD_2_BITS),
        telemetry_point("status", "Stato inverter", "holding", 11016, 1, "uint16", section="Stato e allarmi", summary_metric="status", enum_map=SIEL_SRT_STATUS_MAP),
        telemetry_point("total_energy_kwh", "Energia totale", "holding", 11018, 2, "uint32", scale=0.1, unit="kWh", section="Contatori", summary_metric="total_energy_kwh"),
        telemetry_point("active_power_kw", "Potenza attiva uscita", "holding", 11023, 2, "int32", scale=0.001, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("reactive_power_kvar", "Potenza reattiva uscita", "holding", 11025, 2, "int32", scale=0.001, unit="kVAr", section="Potenza"),
        telemetry_point("phase_l1n_voltage_v", "Tensione fase L1", "holding", 11028, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("phase_l2n_voltage_v", "Tensione fase L2", "holding", 11029, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("phase_l3n_voltage_v", "Tensione fase L3", "holding", 11030, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("phase_l1_current_a", "Corrente fase L1", "holding", 11031, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("phase_l2_current_a", "Corrente fase L2", "holding", 11032, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("phase_l3_current_a", "Corrente fase L3", "holding", 11033, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("internal_temperature_c", "Temperatura interna", "holding", 11039, 1, "int16", scale=0.1, unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("dc_input_power_kw", "Potenza DC ingresso", "holding", 11042, 1, "uint16", scale=0.1, unit="kW", section="Ingresso DC"),
    ]

    for index in range(16):
        telemetry.append(
            telemetry_point(
                f"mppt_{index + 1}_voltage_v",
                f"Tensione MPPT {index + 1}",
                "holding",
                11064 + index,
                1,
                "uint16",
                scale=0.1,
                unit="V",
                section="MPPT",
            )
        )
    for index in range(16):
        telemetry.append(
            telemetry_point(
                f"mppt_{index + 1}_current_a",
                f"Corrente MPPT {index + 1}",
                "holding",
                11080 + index,
                1,
                "uint16",
                scale=0.1,
                unit="A",
                section="MPPT",
            )
        )

    return telemetry


def build_siel_srt_spx_commands(
    *,
    max_active_power_kw: float,
) -> list[InverterPoint]:
    return [
        command_point("active_power_control_mode", "Modalita regolazione P", 12016, "uint16", section="Controllo potenza", min_value=0, max_value=3, enum_map=SIEL_SRT_POWER_CONTROL_MODE_MAP),
        command_point("active_power_setpoint_kw", "Setpoint potenza attiva assoluta", 12017, "uint16", scale=0.1, unit="kW", section="Controllo potenza", min_value=0, max_value=max_active_power_kw),
        command_point("active_power_setpoint_pct", "Setpoint potenza attiva percentuale", 12018, "uint16", scale=0.1, unit="%", section="Controllo potenza", min_value=0, max_value=100),
        command_point("reactive_power_control_mode", "Modalita regolazione Q", 12019, "uint16", section="Controllo reattivo", min_value=0, max_value=3, enum_map=SIEL_SRT_POWER_CONTROL_MODE_MAP),
        command_point("reactive_power_setpoint_kvar", "Setpoint potenza reattiva assoluta", 12020, "int16", scale=0.1, unit="kVAr", section="Controllo reattivo", min_value=-max_active_power_kw, max_value=max_active_power_kw),
        command_point("reactive_power_setpoint_pct", "Setpoint potenza reattiva percentuale", 12021, "int16", scale=0.1, unit="%", section="Controllo reattivo", min_value=-100, max_value=100),
        command_point("power_factor_setpoint", "Setpoint power factor", 12022, "int16", scale=0.001, section="Controllo reattivo", min_value=-1.0, max_value=1.0),
    ]


def build_siel_defaults(
    *,
    protocol: str,
    baud_rate: int,
    test_register: int,
    max_registers_per_request: int = 64,
) -> dict[str, str | int | float | bool]:
    if protocol == "modbus_rtu":
        return {
            "port": "COM1",
            "slave_id": 1,
            "baud_rate": baud_rate,
            "parity": "N",
            "stop_bits": 1,
            "byte_size": 8,
            "timeout_seconds": 2,
            "retries": 1,
            "poll_interval_seconds": 15,
            "max_registers_per_request": max_registers_per_request,
            "test_register": test_register,
            "test_count": 1,
            "test_function": "holding",
        }

    return {
        "host": "192.168.1.170",
        "port": 502,
        "unit_id": 1,
        "timeout_seconds": 2,
        "retries": 1,
        "poll_interval_seconds": 15,
        "max_registers_per_request": max_registers_per_request,
        "test_register": test_register,
        "test_count": 1,
        "test_function": "holding",
    }


def build_siel_models(protocol: str, transport: str) -> list[InverterModel]:
    models: list[InverterModel] = []

    dsp_generic_telemetry = build_siel_dsp_generic_telemetry()
    dsp_generic_commands = build_siel_dsp_generic_commands()
    for model_name in SIEL_DSP_GENERIC_MODELS:
        models.append(
            InverterModel(
                brand=SIEL_BRAND,
                model=model_name,
                protocol=protocol,
                transport=transport,
                defaults=build_siel_defaults(
                    protocol=protocol,
                    baud_rate=9600,
                    test_register=legacy_addr(2001),
                ),
                features=[
                    "telemetria siel dsp dpsx",
                    "smart grid",
                    "controllo potenza attiva",
                    "controllo potenza reattiva",
                ],
                telemetry_points=dsp_generic_telemetry,
                command_points=dsp_generic_commands,
            )
        )

    dspx_high_power_telemetry = build_siel_dspx_high_power_telemetry()
    dspx_high_power_commands = build_siel_dspx_high_power_commands()
    for model_name in SIEL_DSPX_HIGH_POWER_MODELS:
        models.append(
            InverterModel(
                brand=SIEL_BRAND,
                model=model_name,
                protocol=protocol,
                transport=transport,
                defaults=build_siel_defaults(
                    protocol=protocol,
                    baud_rate=9600,
                    test_register=legacy_addr(2003),
                ),
                features=[
                    "telemetria siel dspx high power",
                    "porta user o ppc",
                    "controllo potenza attiva",
                    "controllo potenza reattiva",
                    "keep alive remoto",
                ],
                telemetry_points=dspx_high_power_telemetry,
                command_points=dspx_high_power_commands,
            )
        )

    srt_spx_telemetry = build_siel_srt_spx_telemetry()
    for model_name, baud_rate, max_active_power_kw in SIEL_SRT_SPX_MODELS:
        models.append(
            InverterModel(
                brand=SIEL_BRAND,
                model=model_name,
                protocol=protocol,
                transport=transport,
                defaults=build_siel_defaults(
                    protocol=protocol,
                    baud_rate=baud_rate,
                    test_register=11016,
                ),
                features=[
                    "telemetria siel srt spx",
                    "mppt multipli",
                    "controllo potenza attiva",
                    "controllo potenza reattiva",
                ],
                telemetry_points=srt_spx_telemetry,
                command_points=build_siel_srt_spx_commands(
                    max_active_power_kw=max_active_power_kw,
                ),
            )
        )

    return models
