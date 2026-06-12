from app.models.inverter_model import InverterModel, InverterPoint


SOLAX_BRAND = "SOLAX POWER"
SOLAX_MIC_PRO_MODEL = "X3-MIC-G2 / X3-PRO-G2"
SOLAX_MEGA_FORTH_MODEL = "X3-MEGA-G2 / X3-FORTH"
SOLAX_GRAND_MODEL = "X3-GRAND HV 320K"
SOLAX_ULTRA_MODEL = "X3-ULTRA"
SOLAX_AELIO_MODEL = "X3-AELIO"
SOLAX_DATAHUB_MODEL = "DataHub1000 TCP"
SOLAX_EMS1000_MODEL = "EMS1000 TCP"

SOLAX_DIRECT_MODELS = (
    SOLAX_MIC_PRO_MODEL,
    SOLAX_MEGA_FORTH_MODEL,
    SOLAX_GRAND_MODEL,
    SOLAX_ULTRA_MODEL,
    SOLAX_AELIO_MODEL,
)

SOLAX_RUN_MODE_MAP = {
    0: "Attesa",
    1: "Controllo",
    2: "Normale",
    3: "Guasto",
    4: "Guasto permanente",
    5: "Aggiornamento",
}

SOLAX_LARGE_INVERTER_STATUS_MAP = {
    0: "Inizializzazione",
    1: "Idle",
    2: "Avvio",
    3: "Marcia",
    4: "Arresto / guasto",
    5: "Aggiornamento",
}

SOLAX_HYBRID_STATUS_MAP = {
    0: "Attesa",
    1: "Controllo",
    2: "Normale",
    3: "Guasto",
    4: "Guasto permanente",
    5: "Aggiornamento",
    6: "EPS",
    7: "Self test",
    8: "Idle",
    9: "Standby",
}

SOLAX_EMS_STATUS_MAP = {
    1: "On-grid",
    2: "Off-grid",
    3: "Standby",
    4: "Guasto",
}

SOLAX_START_STOP_MAP = {
    0xAF: "Avvio",
    0xAE: "Arresto",
    0xFE: "Arresto rapido",
}

SOLAX_VPP_CONTROL_MAP = {
    0: "Disabilitato",
    1: "Controllo potenza",
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
    protocol_meta: dict[str, object] = {"section": section}
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
    length: int = 1,
    scale: float = 1.0,
    unit: str = "",
    section: str,
    min_value: float | None = None,
    max_value: float | None = None,
    step: float | None = None,
    enum_map: dict[int, str] | None = None,
    force_multi_write: bool = False,
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
    if force_multi_write:
        protocol_meta["force_multi_write"] = True
        protocol_meta["modbus_write_function"] = "0x10"

    return InverterPoint(
        key=key,
        label=label,
        kind="command",
        register_type="holding",
        address=address,
        length=length,
        datatype=datatype,
        scale=scale,
        unit=unit,
        writable=True,
        protocol_meta=protocol_meta,
    )


def build_mic_pro_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("pv1_voltage_v", "Tensione FV 1", "input", 0x400, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV"),
        telemetry_point("pv2_voltage_v", "Tensione FV 2", "input", 0x401, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV"),
        telemetry_point("pv1_current_a", "Corrente FV 1", "input", 0x402, 1, "uint16", scale=0.1, unit="A", section="Ingresso FV"),
        telemetry_point("pv2_current_a", "Corrente FV 2", "input", 0x403, 1, "uint16", scale=0.1, unit="A", section="Ingresso FV"),
        telemetry_point("mains_voltage_v", "Tensione rete fase R", "input", 0x404, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_s_v", "Tensione rete fase S", "input", 0x405, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_t_v", "Tensione rete fase T", "input", 0x406, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("mains_frequency_hz", "Frequenza rete", "input", 0x407, 1, "uint16", scale=0.01, unit="Hz", section="Rete AC"),
        telemetry_point("ac_current_a", "Corrente uscita fase R", "input", 0x40A, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_current_s_a", "Corrente uscita fase S", "input", 0x40B, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_current_t_a", "Corrente uscita fase T", "input", 0x40C, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("temperature_c", "Temperatura dissipatore", "input", 0x40D, 1, "uint16", unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("active_power_kw", "Potenza attiva", "input", 0x40E, 1, "uint16", scale=0.001, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("status", "Modalita inverter", "input", 0x40F, 1, "uint16", section="Stato", summary_metric="status", enum_map=SOLAX_RUN_MODE_MAP, heartbeat=True),
        telemetry_point("dc_power_kw", "Potenza DC totale", "input", 0x413, 1, "uint16", scale=0.001, unit="kW", section="Ingresso FV"),
        telemetry_point("total_energy_kwh", "Energia totale", "input", 0x423, 2, "uint32_swapped", scale=0.1, unit="kWh", section="Energia", summary_metric="total_energy_kwh"),
        telemetry_point("daily_energy_kwh", "Energia giornaliera", "input", 0x425, 2, "uint32_swapped", scale=0.1, unit="kWh", section="Energia", summary_metric="daily_energy_kwh"),
        telemetry_point("pv3_voltage_v", "Tensione FV 3", "input", 0x429, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV", optional_block=True),
        telemetry_point("pv3_current_a", "Corrente FV 3", "input", 0x42A, 1, "uint16", scale=0.1, unit="A", section="Ingresso FV", optional_block=True),
        telemetry_point("pv3_power_kw", "Potenza FV 3", "input", 0x42B, 1, "uint16", scale=0.001, unit="kW", section="Ingresso FV", optional_block=True),
    ]


def build_mic_pro_commands() -> list[InverterPoint]:
    return [
        command_point("active_power_limit", "Limite potenza attiva", 0x60F, "uint16", unit="%", section="Controllo potenza", min_value=0, max_value=100, step=1),
        command_point("remote_start_stop", "Avvio/arresto remoto", 0x610, "uint16", section="Controllo potenza", min_value=0, max_value=1, step=1),
    ]


def build_mega_forth_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("model_name", "Modello", "input", 0x12, 16, "ascii_string", section="Identificazione", visible=False),
        telemetry_point("serial_number", "Seriale", "input", 0x32, 16, "ascii_string", section="Identificazione", visible=False),
        telemetry_point("rated_active_power_kw", "Potenza attiva nominale", "input", 0x43, 1, "uint16", scale=0.1, unit="kW", section="Dati nominali"),
        telemetry_point("grid_voltage_ab_v", "Tensione rete AB", "input", 0x100, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_bc_v", "Tensione rete BC", "input", 0x101, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_ca_v", "Tensione rete CA", "input", 0x102, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("mains_frequency_hz", "Frequenza rete", "input", 0x106, 1, "uint16", scale=0.01, unit="Hz", section="Rete AC"),
        telemetry_point("ac_current_a", "Corrente fase A", "input", 0x180, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_current_b_a", "Corrente fase B", "input", 0x181, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_current_c_a", "Corrente fase C", "input", 0x182, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("active_power_kw", "Potenza attiva", "input", 0x183, 2, "int32", scale=0.001, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("reactive_power_kvar", "Potenza reattiva", "input", 0x185, 2, "int32", scale=0.001, unit="kVAr", section="Potenza"),
        telemetry_point("apparent_power_kva", "Potenza apparente", "input", 0x187, 2, "uint32", scale=0.001, unit="kVA", section="Potenza"),
        telemetry_point("daily_energy_kwh", "Energia giornaliera", "input", 0x189, 1, "uint16", scale=0.1, unit="kWh", section="Energia", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_kwh", "Energia totale", "input", 0x18A, 2, "uint32", scale=0.1, unit="kWh", section="Energia", summary_metric="total_energy_kwh"),
        telemetry_point("power_factor", "Fattore di potenza", "input", 0x18F, 1, "int16", scale=0.001, section="Potenza"),
        telemetry_point("status", "Stato operativo", "input", 0x200, 1, "uint16", section="Stato", summary_metric="status", enum_map=SOLAX_LARGE_INVERTER_STATUS_MAP, heartbeat=True),
        telemetry_point("temperature_c", "Temperatura interna", "input", 0x202, 1, "int16", scale=0.1, unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("insulation_resistance_kohm", "Resistenza isolamento", "input", 0x210, 1, "int16", scale=0.1, unit="kOhm", section="Stato"),
        telemetry_point("mppt_count", "Numero MPPT", "input", 0x280, 1, "uint16", section="Ingresso FV"),
        telemetry_point("pv1_voltage_v", "Tensione MPPT 1", "input", 0x28B, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV"),
        telemetry_point("pv1_current_a", "Corrente MPPT 1", "input", 0x28C, 1, "uint16", scale=0.1, unit="A", section="Ingresso FV"),
        telemetry_point("pv1_power_kw", "Potenza MPPT 1", "input", 0x28D, 2, "int32", scale=0.001, unit="kW", section="Ingresso FV"),
        telemetry_point("active_power_limit_pct", "Limite potenza attiva", "holding", 0x2303, 1, "uint16", scale=0.1, unit="%", section="Controllo potenza", command="active_power_limit"),
    ]


def build_large_inverter_commands(include_fast_stop: bool = False) -> list[InverterPoint]:
    start_stop_map = SOLAX_START_STOP_MAP if include_fast_stop else {
        0xAF: "Avvio",
        0xAE: "Arresto",
    }
    return [
        command_point("start_stop", "Avvio/arresto", 0x2287, "uint16", section="Controllo", enum_map=start_stop_map),
        command_point("active_power_limit", "Limite potenza attiva", 0x2303, "uint16", scale=0.1, unit="%", section="Controllo potenza", min_value=0, max_value=110, step=0.1),
        command_point("power_factor_setting", "Setpoint fattore di potenza", 0x2308, "int16", scale=0.001, section="Controllo reattivo", min_value=-1, max_value=1, step=0.001),
    ]


def build_grand_telemetry() -> list[InverterPoint]:
    points = [
        telemetry_point("model_name", "Modello", "input", 0x0012, 16, "ascii_string", section="Identificazione", visible=False),
        telemetry_point("serial_number", "Seriale", "input", 0x0032, 16, "ascii_string", section="Identificazione", visible=False),
        telemetry_point("rated_voltage_v", "Tensione nominale", "input", 0x0042, 1, "uint16", unit="V", section="Dati nominali"),
        telemetry_point("rated_active_power_kw", "Potenza attiva nominale", "input", 0x0043, 1, "uint16", unit="kW", section="Dati nominali"),
        telemetry_point("grid_voltage_ab_v", "Tensione rete AB", "input", 0x0080, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_bc_v", "Tensione rete BC", "input", 0x0081, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_ca_v", "Tensione rete CA", "input", 0x0082, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("mains_frequency_hz", "Frequenza rete", "input", 0x0086, 1, "uint16", scale=0.01, unit="Hz", section="Rete AC"),
        telemetry_point("ac_current_a", "Corrente fase A", "input", 0x00B0, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_current_b_a", "Corrente fase B", "input", 0x00B1, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_current_c_a", "Corrente fase C", "input", 0x00B2, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("power_factor", "Fattore di potenza", "input", 0x00B3, 1, "int16", scale=0.001, section="Potenza"),
        telemetry_point("active_power_kw", "Potenza attiva", "input", 0x00B4, 2, "int32", scale=0.1, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("reactive_power_kvar", "Potenza reattiva", "input", 0x00B6, 2, "int32", scale=0.1, unit="kVAr", section="Potenza"),
        telemetry_point("apparent_power_kva", "Potenza apparente", "input", 0x00B8, 2, "uint32", scale=0.1, unit="kVA", section="Potenza"),
        telemetry_point("daily_energy_kwh", "Energia giornaliera", "input", 0x00BA, 2, "uint32", scale=0.1, unit="kWh", section="Energia", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_kwh", "Energia totale", "input", 0x00BC, 2, "uint32", scale=0.1, unit="kWh", section="Energia", summary_metric="total_energy_kwh"),
        telemetry_point("status", "Stato operativo", "input", 0x0200, 1, "uint16", section="Stato", summary_metric="status", enum_map=SOLAX_LARGE_INVERTER_STATUS_MAP, heartbeat=True),
        telemetry_point("insulation_resistance_kohm", "Resistenza isolamento", "input", 0x0203, 1, "uint16", scale=0.1, unit="kOhm", section="Stato"),
        telemetry_point("temperature_c", "Temperatura ambiente", "input", 0x0204, 1, "int16", scale=0.1, unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("active_power_limit_pct", "Limite potenza attiva", "holding", 0x2303, 1, "uint16", scale=0.1, unit="%", section="Controllo potenza", command="active_power_limit"),
    ]
    for index in range(6):
        base_address = 0x0106 + (index * 4)
        points.extend([
            telemetry_point(f"pv{index + 1}_voltage_v", f"Tensione MPPT {index + 1}", "input", base_address, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV"),
            telemetry_point(f"pv{index + 1}_current_a", f"Corrente MPPT {index + 1}", "input", base_address + 1, 1, "uint16", scale=0.1, unit="A", section="Ingresso FV"),
            telemetry_point(f"pv{index + 1}_power_kw", f"Potenza MPPT {index + 1}", "input", base_address + 2, 2, "int32", scale=0.0001, unit="kW", section="Ingresso FV"),
        ])
    return points


def build_grand_commands() -> list[InverterPoint]:
    return build_large_inverter_commands(include_fast_stop=True) + [
        command_point("active_power_rising_slope_pct", "Pendenza salita potenza attiva", 0x2306, "uint16", scale=0.1, unit="%", section="Controllo potenza"),
        command_point("reactive_power_mode", "Modalita potenza reattiva", 0x2307, "uint16", section="Controllo reattivo"),
        command_point("reactive_power_pct", "Setpoint potenza reattiva", 0x2309, "int16", scale=0.1, unit="%", section="Controllo reattivo", min_value=-100, max_value=100, step=0.1),
    ]


def build_hybrid_common_telemetry(include_third_pv: bool, include_three_phase: bool, include_second_battery: bool) -> list[InverterPoint]:
    points = [
        telemetry_point("status", "Stato operativo", "input", 0x0009, 1, "uint16", section="Stato", summary_metric="status", enum_map=SOLAX_HYBRID_STATUS_MAP, heartbeat=True),
        telemetry_point("pv1_voltage_v", "Tensione FV 1", "input", 0x0003, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV"),
        telemetry_point("pv2_voltage_v", "Tensione FV 2", "input", 0x0004, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV"),
        telemetry_point("pv1_current_a", "Corrente FV 1", "input", 0x0005, 1, "uint16", scale=0.1, unit="A", section="Ingresso FV"),
        telemetry_point("pv2_current_a", "Corrente FV 2", "input", 0x0006, 1, "uint16", scale=0.1, unit="A", section="Ingresso FV"),
        telemetry_point("pv1_power_kw", "Potenza FV 1", "input", 0x000A, 1, "uint16", scale=0.001, unit="kW", section="Ingresso FV"),
        telemetry_point("pv2_power_kw", "Potenza FV 2", "input", 0x000B, 1, "uint16", scale=0.001, unit="kW", section="Ingresso FV"),
        telemetry_point("battery_voltage_v", "Tensione batteria 1", "input", 0x0014, 1, "uint16", scale=0.1, unit="V", section="Batteria"),
        telemetry_point("battery_current_a", "Corrente batteria 1", "input", 0x0015, 1, "int16", scale=0.1, unit="A", section="Batteria"),
        telemetry_point("battery_power_kw", "Potenza batteria 1", "input", 0x0016, 1, "int16", scale=0.001, unit="kW", section="Batteria"),
        telemetry_point("battery_connected", "Connessione batteria 1", "input", 0x0017, 1, "uint16", section="Batteria"),
        telemetry_point("battery_temperature_c", "Temperatura batteria 1", "input", 0x0018, 1, "int16", unit="C", section="Batteria"),
        telemetry_point("soc_percent", "SOC batteria 1", "input", 0x001C, 1, "uint16", unit="%", section="Batteria"),
        telemetry_point("daily_energy_kwh", "Energia giornaliera", "input", 0x0050, 1, "uint16", scale=0.1, unit="kWh", section="Energia", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_kwh", "Energia totale", "input", 0x0052, 2, "uint32_swapped", scale=0.1, unit="kWh", section="Energia", summary_metric="total_energy_kwh"),
    ]
    if include_three_phase:
        for phase, base_address in (("r", 0x006A), ("s", 0x006E), ("t", 0x0072)):
            points.extend([
                telemetry_point(f"grid_voltage_{phase}_v", f"Tensione rete fase {phase.upper()}", "input", base_address, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
                telemetry_point(f"grid_current_{phase}_a", f"Corrente rete fase {phase.upper()}", "input", base_address + 1, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
                telemetry_point(f"grid_power_{phase}_kw", f"Potenza rete fase {phase.upper()}", "input", base_address + 2, 1, "int16", scale=0.001, unit="kW", section="Rete AC"),
                telemetry_point(f"grid_frequency_{phase}_hz", f"Frequenza rete fase {phase.upper()}", "input", base_address + 3, 1, "uint16", scale=0.01, unit="Hz", section="Rete AC"),
            ])
    else:
        points.extend([
            telemetry_point("mains_voltage_v", "Tensione rete fase R", "input", 0x0000, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
            telemetry_point("ac_current_a", "Corrente rete fase R", "input", 0x0001, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
            telemetry_point("grid_power_r_kw", "Potenza rete fase R", "input", 0x0002, 1, "int16", scale=0.001, unit="kW", section="Rete AC"),
            telemetry_point("mains_frequency_hz", "Frequenza rete fase R", "input", 0x0007, 1, "uint16", scale=0.01, unit="Hz", section="Rete AC"),
            telemetry_point("grid_status", "Stato rete", "input", 0x001A, 1, "uint16", section="Stato"),
        ])
    if include_third_pv:
        points.extend([
            telemetry_point("pv3_voltage_v", "Tensione FV 3", "input", 0x0122, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV"),
            telemetry_point("pv3_current_a", "Corrente FV 3", "input", 0x0123, 1, "uint16", scale=0.1, unit="A", section="Ingresso FV"),
            telemetry_point("pv3_power_kw", "Potenza FV 3", "input", 0x0124, 1, "uint16", scale=0.001, unit="kW", section="Ingresso FV"),
        ])
    if include_second_battery:
        points.extend([
            telemetry_point("battery_2_connected", "Connessione batteria 2", "input", 0x001F, 1, "uint16", section="Batteria"),
            telemetry_point("battery_2_voltage_v", "Tensione batteria 2", "input", 0x0127, 1, "uint16", scale=0.1, unit="V", section="Batteria"),
            telemetry_point("battery_2_current_a", "Corrente batteria 2", "input", 0x0128, 1, "int16", scale=0.1, unit="A", section="Batteria"),
            telemetry_point("battery_2_power_kw", "Potenza batteria 2", "input", 0x0129, 1, "int16", scale=0.001, unit="kW", section="Batteria"),
            telemetry_point("battery_2_soc_percent", "SOC batteria 2", "input", 0x012D, 1, "uint16", unit="%", section="Batteria"),
            telemetry_point("battery_2_temperature_c", "Temperatura batteria 2", "input", 0x0131, 1, "int16", unit="C", section="Batteria"),
        ])
    return points


def build_hybrid_vpp_commands() -> list[InverterPoint]:
    return [
        command_point("vpp_power_control", "Controllo potenza VPP", 0x007C, "uint16", section="VPP", enum_map=SOLAX_VPP_CONTROL_MAP, force_multi_write=True),
        command_point("vpp_target_set_type", "Tipo target VPP", 0x007D, "uint16", section="VPP", force_multi_write=True),
        command_point("remote_active_power_w", "Target potenza attiva VPP", 0x007E, "int32_swapped", length=2, unit="W", section="VPP", force_multi_write=True),
        command_point("remote_reactive_power_var", "Target potenza reattiva VPP", 0x0080, "int32_swapped", length=2, unit="Var", section="VPP", force_multi_write=True),
        command_point("vpp_duration_s", "Durata target VPP", 0x0082, "uint16", unit="s", section="VPP", force_multi_write=True),
        command_point("vpp_timeout_s", "Timeout VPP", 0x0088, "uint16", unit="s", section="VPP", force_multi_write=True),
    ]


def build_datahub_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("meter_voltage_ab_v", "Tensione meter AB", "input", 40440, 1, "uint16", scale=0.1, unit="V", section="Meter"),
        telemetry_point("meter_voltage_bc_v", "Tensione meter BC", "input", 40441, 1, "uint16", scale=0.1, unit="V", section="Meter"),
        telemetry_point("meter_voltage_ca_v", "Tensione meter CA", "input", 40442, 1, "uint16", scale=0.1, unit="V", section="Meter"),
        telemetry_point("meter_current_a_a", "Corrente meter fase A", "input", 40443, 1, "int16", scale=0.1, unit="A", section="Meter"),
        telemetry_point("meter_current_b_a", "Corrente meter fase B", "input", 40444, 1, "int16", scale=0.1, unit="A", section="Meter"),
        telemetry_point("meter_current_c_a", "Corrente meter fase C", "input", 40445, 1, "int16", scale=0.1, unit="A", section="Meter"),
        telemetry_point("meter_active_power_kw", "Potenza attiva meter", "input", 40446, 2, "int32", scale=0.001, unit="kW", section="Meter"),
        telemetry_point("meter_reactive_power_kvar", "Potenza reattiva meter", "input", 40448, 2, "int32", scale=0.001, unit="kVAr", section="Meter"),
        telemetry_point("power_factor", "Fattore di potenza meter", "input", 40450, 1, "int16", scale=0.001, section="Meter"),
        telemetry_point("mains_frequency_hz", "Frequenza meter", "input", 40451, 1, "uint16", scale=0.01, unit="Hz", section="Meter"),
        telemetry_point("active_power_kw", "Potenza attiva inverter complessiva", "input", 40520, 2, "int32", scale=0.001, unit="kW", section="Impianto", summary_metric="power_kw", heartbeat=True),
        telemetry_point("reactive_power_kvar", "Potenza reattiva complessiva", "input", 40522, 2, "int32", scale=0.001, unit="kVAr", section="Impianto"),
        telemetry_point("daily_energy_kwh", "Energia giornaliera complessiva", "input", 40524, 1, "uint16", scale=0.01, unit="kWh", section="Impianto", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_kwh", "Energia totale complessiva", "input", 40526, 2, "uint32", unit="kWh", section="Impianto", summary_metric="total_energy_kwh"),
        telemetry_point("installed_capacity_kw", "Potenza installata", "input", 40528, 2, "uint32", scale=0.01, unit="kW", section="Impianto"),
        telemetry_point("output_power_kw", "Potenza di uscita", "input", 40530, 1, "int16", scale=0.01, unit="kW", section="Impianto"),
        telemetry_point("grid_power_kw", "Potenza rete", "input", 40536, 2, "int32", scale=0.01, unit="kW", section="Impianto"),
        telemetry_point("soc_percent", "SOC complessivo", "input", 40538, 1, "uint16", unit="%", section="Impianto"),
        telemetry_point("active_power_limit_pct", "Limite potenza attiva applicato", "input", 45600, 1, "uint16", scale=0.1, unit="%", section="Controllo potenza", command="active_power_limit"),
        telemetry_point("active_power_limit_error_port", "Porta errore limite potenza attiva", "input", 45601, 1, "uint16", section="Controllo potenza"),
        telemetry_point("realtime_active_power_limit_pct", "Limite potenza attiva realtime applicato", "input", 45604, 1, "uint16", scale=0.1, unit="%", section="Controllo potenza"),
        telemetry_point("realtime_active_power_limit_error_port", "Porta errore limite realtime", "input", 45605, 1, "uint16", section="Controllo potenza"),
    ]


def build_datahub_commands() -> list[InverterPoint]:
    return [
        command_point("active_power_limit", "Limite potenza attiva impianto", 40600, "uint16", scale=0.1, unit="%", section="Controllo potenza", min_value=0, max_value=100, step=0.1),
        command_point("reactive_power_cosphi_pct", "Setpoint cosphi", 40601, "int16", scale=0.1, unit="%", section="Controllo reattivo", min_value=-100, max_value=100, step=0.1),
        command_point("realtime_active_power_limit_set_pct", "Limite potenza attiva realtime", 40602, "uint16", scale=0.1, unit="%", section="Controllo potenza", min_value=0, max_value=100, step=0.1),
    ]


def build_ems1000_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("serial_number", "Seriale EMS", "input", 0x0000, 15, "ascii_string", section="Identificazione", visible=False),
        telemetry_point("firmware_version", "Versione EMS", "input", 0x000F, 5, "ascii_string", section="Identificazione", visible=False),
        telemetry_point("daily_energy_kwh", "Energia FV giornaliera", "input", 0x0049, 2, "uint32", scale=0.1, unit="kWh", section="Energia", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_kwh", "Energia FV totale", "input", 0x004B, 2, "uint32", scale=0.1, unit="kWh", section="Energia", summary_metric="total_energy_kwh"),
        telemetry_point("dc_power_kw", "Potenza FV", "input", 0x005B, 2, "int32", scale=0.01, unit="kW", section="Potenza"),
        telemetry_point("grid_power_kw", "Potenza rete", "input", 0x005D, 2, "int32", scale=0.01, unit="kW", section="Potenza"),
        telemetry_point("battery_power_kw", "Potenza batteria", "input", 0x005F, 2, "int32", scale=0.01, unit="kW", section="Potenza"),
        telemetry_point("load_power_kw", "Potenza carico", "input", 0x0061, 2, "int32", scale=0.01, unit="kW", section="Potenza"),
        telemetry_point("soc_percent", "SOC batteria", "input", 0x0063, 1, "uint16", scale=0.1, unit="%", section="Batteria"),
        telemetry_point("active_power_kw", "Potenza attiva totale sistema", "input", 0x006A, 2, "int32", scale=0.01, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("status", "Stato operativo EMS", "input", 0x006C, 1, "uint16", section="Stato", summary_metric="status", enum_map=SOLAX_EMS_STATUS_MAP, heartbeat=True),
        telemetry_point("reactive_power_kvar", "Potenza reattiva totale sistema", "input", 0x006E, 2, "int32", scale=0.01, unit="kVAr", section="Potenza"),
        telemetry_point("meter_active_power_kw", "Potenza attiva meter", "input", 0x00CE, 2, "int32", scale=0.01, unit="kW", section="Meter"),
        telemetry_point("meter_reactive_power_kvar", "Potenza reattiva meter", "input", 0x00D0, 2, "int32", scale=0.01, unit="kVAr", section="Meter"),
        telemetry_point("power_factor", "Fattore di potenza meter", "input", 0x00D2, 1, "int16", scale=0.001, section="Meter"),
        telemetry_point("meter_voltage_a_v", "Tensione meter fase A", "input", 0x00D9, 1, "uint16", scale=0.1, unit="V", section="Meter"),
        telemetry_point("meter_voltage_b_v", "Tensione meter fase B", "input", 0x00DB, 1, "uint16", scale=0.1, unit="V", section="Meter"),
        telemetry_point("meter_voltage_c_v", "Tensione meter fase C", "input", 0x00DC, 1, "uint16", scale=0.1, unit="V", section="Meter"),
        telemetry_point("meter_current_a_a", "Corrente meter fase A", "input", 0x00DD, 1, "int16", scale=0.1, unit="A", section="Meter"),
        telemetry_point("meter_current_b_a", "Corrente meter fase B", "input", 0x00DE, 1, "int16", scale=0.1, unit="A", section="Meter"),
        telemetry_point("meter_current_c_a", "Corrente meter fase C", "input", 0x00DF, 1, "int16", scale=0.1, unit="A", section="Meter"),
        telemetry_point("mains_frequency_hz", "Frequenza meter", "input", 0x00E0, 1, "uint16", scale=0.01, unit="Hz", section="Meter"),
    ]


def build_ems1000_commands() -> list[InverterPoint]:
    return [
        command_point("system_control_source", "Origine controllo sistema", 0x0004, "uint16", section="Controllo EMS"),
        command_point("system_power_on_off", "Accensione/spegnimento sistema", 0x0005, "uint16", section="Controllo EMS"),
        command_point("system_work_mode", "Modalita lavoro sistema", 0x0006, "uint16", section="Controllo EMS"),
        command_point("vpp_active_power_target_w", "Target potenza attiva VPP", 0x0033, "int32", length=2, unit="W", section="VPP", force_multi_write=True),
        command_point("vpp_timeout_s", "Timeout VPP", 0x0038, "uint16", unit="s", section="VPP"),
        command_point("vpp_target_set", "Applica target VPP", 0x0039, "uint16", section="VPP"),
    ]


def build_direct_defaults(protocol: str, test_register: int) -> dict[str, str | int | float | bool]:
    common: dict[str, str | int | float | bool] = {
        "timeout_seconds": 1,
        "retries": 1,
        "poll_interval_seconds": 15,
        "inter_request_delay_ms": 1000,
        "test_register": test_register,
        "test_count": 1,
        "test_function": "input",
        "max_registers_per_request": 60,
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


def build_tcp_controller_defaults(test_register: int) -> dict[str, str | int | float | bool]:
    return {
        "host": "192.168.1.100",
        "port": 502,
        "unit_id": 1,
        "timeout_seconds": 1,
        "retries": 1,
        "poll_interval_seconds": 15,
        "test_register": test_register,
        "test_count": 1,
        "test_function": "input",
        "max_registers_per_request": 100,
    }


def build_solax_models(protocol: str, transport: str) -> list[InverterModel]:
    if (protocol, transport) not in {
        ("modbus_rtu", "serial"),
        ("modbus_tcp", "tcp"),
    }:
        return []

    direct_profiles = [
        (
            SOLAX_MIC_PRO_MODEL,
            0x40F,
            build_mic_pro_telemetry(),
            build_mic_pro_commands(),
            ["telemetria trifase", "controllo potenza attiva", "energia e stato inverter"],
        ),
        (
            SOLAX_MEGA_FORTH_MODEL,
            0x200,
            build_mega_forth_telemetry(),
            build_large_inverter_commands(),
            ["telemetria inverter utility scale", "controllo potenza attiva", "readback setpoint"],
        ),
        (
            SOLAX_GRAND_MODEL,
            0x0200,
            build_grand_telemetry(),
            build_grand_commands(),
            ["telemetria inverter utility scale", "sei mppt", "controllo potenza attiva e reattiva"],
        ),
        (
            SOLAX_ULTRA_MODEL,
            0x0009,
            build_hybrid_common_telemetry(True, True, True),
            build_hybrid_vpp_commands(),
            ["telemetria ibrida trifase", "tre ingressi fv", "due batterie", "controllo vpp assoluto"],
        ),
        (
            SOLAX_AELIO_MODEL,
            0x0009,
            build_hybrid_common_telemetry(False, False, False),
            build_hybrid_vpp_commands(),
            ["telemetria ibrida", "batteria", "controllo vpp assoluto"],
        ),
    ]
    models = [
        InverterModel(
            brand=SOLAX_BRAND,
            model=model,
            protocol=protocol,
            transport=transport,
            defaults=build_direct_defaults(protocol, test_register),
            features=["manuale SOLAX POWER verificato", *features],
            telemetry_points=telemetry,
            command_points=commands,
        )
        for model, test_register, telemetry, commands, features in direct_profiles
    ]

    if protocol == "modbus_tcp":
        models.extend([
            InverterModel(
                brand=SOLAX_BRAND,
                model=SOLAX_DATAHUB_MODEL,
                protocol=protocol,
                transport=transport,
                defaults=build_tcp_controller_defaults(40520),
                features=[
                    "data logger tcp",
                    "telemetria aggregata impianto",
                    "controllo potenza attiva impianto",
                    "readback setpoint",
                ],
                telemetry_points=build_datahub_telemetry(),
                command_points=build_datahub_commands(),
            ),
            InverterModel(
                brand=SOLAX_BRAND,
                model=SOLAX_EMS1000_MODEL,
                protocol=protocol,
                transport=transport,
                defaults=build_tcp_controller_defaults(0x006C),
                features=[
                    "ems tcp",
                    "telemetria aggregata impianto",
                    "meter e batteria",
                    "controllo vpp assoluto",
                ],
                telemetry_points=build_ems1000_telemetry(),
                command_points=build_ems1000_commands(),
            ),
        ])
    return models
