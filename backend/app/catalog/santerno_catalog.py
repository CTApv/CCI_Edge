from app.models.inverter_model import InverterModel, InverterPoint


SANTERNO_BRAND = "Santerno"
SANTERNO_MODELS = (
    "SUNWAY TG",
    "SUNWAY TG TE",
)

SANTERNO_STATUS_MAP = {
    0: "Precarica",
    1: "STOP - attesa enable",
    2: "Inverter in stop",
    3: "STOP - run OK",
    4: "Standby rete KO",
    5: "Transizione a stop",
    6: "Transizione a standby",
    7: "Standby insolazione",
    8: "Standby controllo rete",
    9: "Standby timeout",
    10: "Standby ripristino rete",
    11: "Sincronizzazione",
    12: "Chiusura TLP/KM1",
    13: "Apertura TLP/KM1",
    14: "Run",
    15: "Spegnimento",
    16: "Allarme 1",
    17: "Allarme 2",
    18: "Resetting",
    19: "Standby insolazione",
    21: "Standby tensione minima rete",
    22: "Standby tensione massima rete",
    23: "Standby frequenza rete KO",
    24: "Standby PLL KO",
    25: "Tuning synchro",
    26: "Raffreddamento",
    30: "Standby rete ausiliaria KO",
    31: "Spegnimento per insolazione KO",
}

SANTERNO_GPC_MODE_MAP = {
    0: "Disattivo",
    1: "Attivo - entry table da Modbus",
    2: "Attivo - setpoint P/Cosphi da Modbus",
    3: "Attivo - setpoint P/Q da Modbus",
    4: "Attivo - ingresso analogico",
    5: "Attivo - interfaccia digitale 4 fili",
    6: "Attivo - curva Cosphi(P)",
    7: "Attivo - curva Q(U)",
}


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
    section: str,
    summary_metric: str | None = None,
    enum_map: dict[int, str] | None = None,
    command: str | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {"section": section}
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map
    if command is not None:
        protocol_meta["command"] = command

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
    step: float | None = None,
    enum_map: dict[int, str] | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {
        "section": section,
        "force_multi_write": True,
        "modbus_write_function": "0x10",
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


def build_santerno_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("product_id", "Identificativo prodotto", 476, 1, "ascii_string", visible=False, section="Identita"),
        telemetry_point("cst_remote_control_state", "Stato controlli", 1494, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("total_energy_kwh", "Energia attiva erogata", 1663, 2, "int32_swapped", scale=0.1, unit="kWh", section="Energia", summary_metric="total_energy_kwh"),
        telemetry_point("pv_energy_kwh", "Energia da campo FV", 1667, 2, "uint32_swapped", scale=0.1, unit="kWh", section="Energia"),
        telemetry_point("mains_frequency_hz", "Frequenza rete", 1651, 1, "int16", scale=0.01, unit="Hz", section="Rete AC"),
        telemetry_point("power_factor", "Fattore di potenza", 1652, 1, "uint16", scale=0.01, section="Potenza"),
        telemetry_point("active_power_kw", "Potenza attiva erogata", 1653, 1, "int16", scale=0.1, unit="kW", section="Potenza", summary_metric="power_kw"),
        telemetry_point("reactive_power_kvar", "Potenza reattiva erogata", 1654, 1, "int16", scale=0.1, unit="kVAr", section="Potenza"),
        telemetry_point("apparent_power_kva", "Potenza apparente", 1655, 1, "int16", scale=0.1, unit="kVA", section="Potenza"),
        telemetry_point("inverter_voltage_v", "Tensione inverter", 1656, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("mains_voltage_v", "Tensione rete", 1657, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("inverter_current_a", "Corrente inverter", 1658, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("ac_current_a", "Corrente rete", 1659, 1, "uint16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("dc_voltage_v", "Tensione campo FV", 1660, 1, "uint16", scale=0.1, unit="V", section="Ingresso FV"),
        telemetry_point("dc_current_a", "Corrente campo FV", 1661, 1, "uint16", scale=0.1, unit="A", section="Ingresso FV"),
        telemetry_point("dc_power_kw", "Potenza campo FV", 1662, 1, "int16", scale=0.1, unit="kW", section="Ingresso FV"),
        telemetry_point("system_warning", "System warning", 1671, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("grid_voltage_rs_v", "Tensione R-S", 1687, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_st_v", "Tensione S-T", 1688, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_voltage_tr_v", "Tensione T-R", 1689, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_current_r_a", "Corrente rete fase R", 1690, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_current_s_a", "Corrente rete fase S", 1691, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("grid_current_t_a", "Corrente rete fase T", 1692, 1, "int16", scale=0.1, unit="A", section="Rete AC"),
        telemetry_point("pll_status", "Stato PLL", 1693, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("grid_fault_status_2", "Stato rete 2", 1694, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("grid_fault_status_1", "Stato rete 1", 1695, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("grid_phase_r_voltage_v", "Tensione fase R", 1715, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_phase_s_voltage_v", "Tensione fase S", 1716, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("grid_phase_t_voltage_v", "Tensione fase T", 1717, 1, "uint16", scale=0.1, unit="V", section="Rete AC"),
        telemetry_point("active_power_phase_r_kw", "Potenza attiva fase R", 1721, 1, "int16", scale=0.1, unit="kW", section="Potenza"),
        telemetry_point("active_power_phase_s_kw", "Potenza attiva fase S", 1722, 1, "int16", scale=0.1, unit="kW", section="Potenza"),
        telemetry_point("active_power_phase_t_kw", "Potenza attiva fase T", 1723, 1, "int16", scale=0.1, unit="kW", section="Potenza"),
        telemetry_point("status", "Stato inverter", 1739, 1, "uint16", section="Stato e allarmi", summary_metric="status", enum_map=SANTERNO_STATUS_MAP),
        telemetry_point("active_alarm", "Allarme attivo", 1740, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("isolation_alarm", "Allarme isolamento", 1825, 1, "uint16", section="Stato e allarmi"),
        telemetry_point("ppc_interface_status", "Stato interfaccia PPC", 3226, 1, "uint16", section="Controllo potenza"),
        telemetry_point("grid_power_control_mode", "Grid Power Control attuato", 3227, 1, "uint16", section="Controllo potenza", enum_map=SANTERNO_GPC_MODE_MAP),
        telemetry_point("active_power_limit_pct", "Active Power Limit attuato", 3228, 1, "uint16", scale=0.01, unit="%", section="Controllo potenza", command="active_power_limit"),
        telemetry_point("cosphi_setpoint_actual", "Cosphi setpoint attuato", 3229, 1, "uint16", scale=0.001, section="Controllo reattivo"),
        telemetry_point("reactive_power_setpoint_pct_actual", "Reactive Power Setpoint attuato", 3230, 1, "int16", scale=0.01, unit="%", section="Controllo reattivo"),
        telemetry_point("temperature_cpu_c", "Temperatura CPU", 1712, 1, "int16", scale=0.1, unit="C", section="Termico", summary_metric="temperature_c"),
        telemetry_point("temperature_igbt_c", "Temperatura IGBT", 1714, 1, "int16", scale=0.1, unit="C", section="Termico"),
    ]


def build_santerno_commands() -> list[InverterPoint]:
    return [
        command_point("grid_power_control_mode", "Abilitazione Grid Power Control", 900, "uint16", section="Controllo potenza", min_value=0, max_value=7, step=1, enum_map=SANTERNO_GPC_MODE_MAP),
        command_point("active_power_limit", "Active Power Limit", 918, "uint16", scale=0.01, unit="%", section="Controllo potenza", min_value=0, max_value=100.0, step=0.01),
        command_point("cosphi_setpoint", "Cosphi Setpoint", 919, "uint16", scale=0.001, section="Controllo reattivo", min_value=0.9, max_value=1.1, step=0.001),
        command_point("reactive_power_setpoint_pct", "Reactive Power Setpoint", 920, "int16", scale=0.01, unit="%", section="Controllo reattivo", min_value=-100.0, max_value=100.0, step=0.01),
    ]


def build_santerno_models(protocol: str, transport: str) -> list[InverterModel]:
    if protocol != "modbus_rtu" or transport != "serial":
        return []

    return [
        InverterModel(
            brand=SANTERNO_BRAND,
            model=model,
            protocol=protocol,
            transport=transport,
            defaults={
                "port": "COM1",
                "slave_id": 1,
                "baud_rate": 38400,
                "parity": "N",
                "stop_bits": 2,
                "byte_size": 8,
                "timeout_seconds": 1.0,
                "retries": 1,
                "poll_interval_seconds": 15,
                "heartbeat_interval_seconds": 2,
                "test_register": 476,
                "test_function": "holding",
                "test_count": 1,
                "max_registers_per_request": 32,
            },
            features=[
                "modbus rtu",
                "telemetry",
                "active power control",
                "grid power control",
            ],
            telemetry_points=build_santerno_telemetry(),
            command_points=build_santerno_commands(),
        )
        for model in SANTERNO_MODELS
    ]
