"""STP60 via Inverter Manager; SMA SunSpec TI en-15, sections 3–7.

Addresses are zero-based (manual register number minus one).
Only the gateway exposes IC123 controls. Individual units are read-only.
"""
from app.models.inverter_model import InverterModel, InverterPoint

SMA_DRIVER = "sma_stp60_manager"
MANAGER_MODEL = "Inverter Manager — STP 60 (gruppo)"
INVERTER_MODEL = "STP 60-10 — via Inverter Manager (lettura)"
SOURCE = "https://files.sma.de/downloads/STP60_SHP75_STPS60-SunSpec_Modbus-TI-en-15.pdf"


def telemetry(manager):
    points = []
    def add(key, label, register, datatype="uint16", length=1, sf=None,
            unit="", scale=1.0, section="Inverter", **meta):
        points.append(InverterPoint(key=key, label=label, kind="telemetry",
            register_type="holding", address=register-1, length=length,
            datatype=datatype, scale=scale, unit=unit,
            protocol_meta={"driver": SMA_DRIVER, "manager": manager, "section": section,
                           "sf_address": None if sf is None else sf-1, **meta}))
    for key, label, reg, size in [("manufacturer", "Costruttore", 40005, 16),
            ("device_model", "Modello rilevato", 40021, 16),
            ("firmware_version", "Firmware", 40045, 8),
            ("serial_number", "Numero di serie", 40053, 16)]:
        add(key, label, reg, "string", size, section="Identità")
    add("active_power_kw", "Potenza attiva", 40200, "int16", sf=40201, unit="kW", scale=.001, summary_metric="power_kw")
    add("total_energy_kwh", "Energia totale", 40210, "acc32", 2, sf=40212, unit="kWh", scale=.001, summary_metric="total_energy_kwh")
    add("ac_frequency_hz", "Frequenza", 40202, sf=40203, unit="Hz")
    add("ac_current_a", "Corrente AC totale", 40188, sf=40192, unit="A")
    for phase, reg in zip("abc", (40189, 40190, 40191)):
        add(f"ac_current_{phase}_a", f"Corrente fase {phase.upper()}", reg, sf=40192, unit="A")
    for phase, reg in zip("abc", (40196, 40197, 40198)):
        add(f"ac_voltage_{phase}_v", f"Tensione fase {phase.upper()}", reg, sf=40199, unit="V")
    add("apparent_power_kva", "Potenza apparente", 40204, "int16", sf=40205, unit="kVA", scale=.001)
    add("reactive_power_kvar", "Potenza reattiva", 40206, "int16", sf=40207, unit="kvar", scale=.001)
    add("power_factor", "Fattore di potenza", 40208, "int16", sf=40209, scale=.01)
    add("dc_current_a", "Corrente DC", 40213, sf=40214, unit="A")
    add("dc_voltage_v", "Tensione DC", 40215, sf=40216, unit="V")
    add("dc_power_kw", "Potenza DC", 40217, "int16", sf=40218, unit="kW", scale=.001)
    add("temperature_c", "Temperatura interna", 40219, "int16", sf=40223, unit="C", summary_metric="temperature_c")
    add("operating_state", "Stato SMA", 40225, section="Diagnostica", summary_metric="status")
    for index, reg in enumerate((40230, 40232, 40234, 40236), 1):
        add(f"vendor_events_{index}", f"Eventi SMA {index}", reg, "bitfield32", 2, section="Diagnostica")
    if manager:
        add("rated_power_kw", "Potenza nominale del gruppo", 40241, sf=40242, unit="kW", scale=.001)
        add("maximum_power_kw", "Base potenza del gruppo WMax", 40268, sf=40288, unit="kW", scale=.001)
        add("power_limit_pct", "Riferimento potenza del gruppo", 40349, "int16", sf=40367, unit="%",
            section="Controllo gruppo", command="active_power_limit", readback_enabled_key="power_limit_enabled")
        add("power_limit_enabled", "Limitazione attiva", 40353, section="Controllo gruppo")
        add("connection_request", "Consenso avviamento del gruppo", 40348, section="Controllo gruppo")
    return points


def build_sma_stp60_models():
    models = []
    for manager, name, uid in [(True, MANAGER_MODEL, 125), (False, INVERTER_MODEL, 126)]:
        commands = []
        if manager:
            for key, label, reg, low, high, unit in [
                ("active_power_limit", "Limite potenza intero gruppo (% di WMax)", 40349, 0, 100, "%"),
                ("start_inverter", "ON — consenso avviamento intero gruppo", 40348, 1, 1, ""),
                ("stop_inverter", "OFF — arresto intero gruppo", 40348, 0, 0, "")]:
                commands.append(InverterPoint(key=key, label=label, kind="command", register_type="holding",
                    address=reg-1, length=1, datatype="int16" if unit else "uint16", unit=unit, writable=True,
                    protocol_meta={"driver": SMA_DRIVER, "manager": True, "min_value": low,
                        "max_value": high, "step": .01 if unit else 1, "default_value": high,
                        "section": "Controllo intero gruppo"}))
        models.append(InverterModel(brand="SMA", model=name, protocol="modbus_tcp", transport="tcp",
            defaults={"host": "192.168.1.100", "port": 502, "unit_id": uid,
                "timeout_seconds": 3, "retries": 0, "poll_interval_seconds": 30,
                "test_register": 40000, "test_count": 2, "test_function": "holding"},
            features=["SMA Inverter Manager obbligatorio", "SunSpec Modbus TCP", "Massimo 1 richiesta/s per Manager",
                "Comandi su intero gruppo" if manager else "Singolo STP 60-10 in sola lettura"],
            telemetry_points=telemetry(manager), command_points=commands,
            catalog_meta={"series": "Sunny Tripower 60", "verification_status": "documented_not_field_tested",
                "source_document": SOURCE, "source_version": "1.5", "last_reviewed_at": "2026-11-20",
                "field_tested": False, "notes": "Manager: ID 125, inverter: 126–167. Firmware <1.45: ID 1 e 2–43. "
                    "Non sommare il gruppo ai singoli inverter nel totale impianto. Comandi solo al Manager; collaudo fisico da eseguire."}))
    return models
