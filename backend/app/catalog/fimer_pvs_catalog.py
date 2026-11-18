"""ABB/FIMER PVS profiles, with runtime SunSpec block discovery."""
import json
from pathlib import Path
from app.models.inverter_model import InverterModel, InverterPoint

PVS_DRIVER = "fimer_pvs_sunspec"
PVS_MAP = json.loads(Path(__file__).with_name("fimer_pvs_sunspec_map.json").read_text())
PVS_MODELS = {
    "PVS-100-TL": ("3P80", 100), "PVS-100-TL B": ("3Q15", 100), "PVS-100-TL B2": ("3Q42", 100),
    "PVS-120-TL": ("3P20", 120), "PVS-120-TL B": ("3Q14", 120), "PVS-120-TL B2": ("3Q41", 120),
}

# Exact Common.Md observed on the PVS-100-TL B2 fleet on 2026-11-18.
# Do not accept arbitrary suffixes or infer another hardware revision.
PVS_MODEL_IDENTITY_ALIASES = {"PVS-100-TL B2": ("3Q4200",)}


def telemetry_points():
    points = []
    def add(key, label, did, field, *, unit="", scale=1., summary=None, channel=None):
        definition = PVS_MAP["models"][str(did)]["fields"][field]
        meta = {"driver": PVS_DRIVER, "did": did, "field": field, "section": "SunSpec PVS"}
        if summary:
            meta["summary_metric"] = summary
        if channel:
            meta["channel"] = channel
        if key == "active_power_limit_pct":
            meta.update(command="active_power_limit", readback_enabled_key="active_power_limit_enabled",
                readback_required_values={"power_limit_revert_s": 120, "power_limit_ramp_s": 0, "power_limit_window_s": 0})
        points.append(InverterPoint(key=key, label=label, kind="telemetry", register_type="holding",
            address=definition["offset"], length=definition["length"], datatype=definition["datatype"],
            unit=unit, scale=scale, protocol_meta=meta))
    for key, field, label in [("manufacturer", "Mn", "Costruttore"), ("model_code", "Md", "Codice modello"),
            ("firmware", "Vr", "Firmware"), ("serial_number", "Number", "Numero di serie")]:
        add(key, label, 1, field)
    add("active_power_kw", "Potenza attiva", 103, "W", unit="kW", scale=.001, summary="power_kw")
    add("total_energy_kwh", "Energia totale esportata", 122, "ActWh", unit="kWh", scale=.001, summary="total_energy_kwh")
    for key, field, label, unit, scale in [
        ("ac_current_a", "A", "Corrente AC", "A", 1), ("ac_frequency_hz", "Hz", "Frequenza rete", "Hz", 1),
        ("apparent_power_kva", "VA", "Potenza apparente", "kVA", .001),
        ("reactive_power_kvar", "Var", "Potenza reattiva", "kvar", .001),
        ("power_factor", "PF", "Fattore di potenza", "", .01),
        ("dc_power_kw", "DCW", "Potenza DC", "kW", .001), ("dc_current_a", "DCA", "Corrente DC", "A", 1)]:
        add(key, label, 103, field, unit=unit, scale=scale)
    add("temperature_c", "Temperatura wiring box", 103, "TmpCab", unit="C", summary="temperature_c")
    add("heatsink_temperature_c", "Temperatura dissipatore", 103, "TmpSnk", unit="C")
    add("operating_state", "Stato SunSpec", 103, "St", summary="status")
    for field in ["StVnd", "Evt1", "Evt2", "EvtVnd1", "EvtVnd2", "EvtVnd3", "EvtVnd4"]:
        add(field.lower(), field, 103, field)
    for phase in "ABC":
        add(f"ac_current_{phase.lower()}_a", f"Corrente fase {phase}", 103, f"Aph{phase}", unit="A")
        add(f"ac_voltage_{phase.lower()}_v", f"Tensione fase {phase}", 103, f"PhVph{phase}", unit="V")
    for pair in ["AB", "BC", "CA"]:
        add(f"ac_voltage_{pair.lower()}_v", f"Tensione {pair}", 103, f"PPVph{pair}", unit="V")
    add("rated_power_kw", "Potenza nominale", 120, "WRtg", unit="kW", scale=.001)
    add("maximum_power_kw", "Base limite WMax", 121, "WMax", unit="kW", scale=.001)
    for key, field, unit in [("active_power_limit_pct", "WMaxLimPct", "%"),
        ("active_power_limit_enabled", "WMaxLim_Ena", ""), ("power_limit_revert_s", "WMaxLimPct_RvrtTms", "s"),
        ("power_limit_ramp_s", "WMaxLimPct_RmpTms", "s"), ("power_limit_window_s", "WMaxLimPct_WinTms", "s")]:
        add(key, field, 123, field, unit=unit)
    add("mppt_count", "Numero canali MPPT", 160, "N")
    for index in range(1, 7):
        for field, suffix, unit, scale in [("DCA", "current_a", "A", 1), ("DCV", "voltage_v", "V", 1),
                ("DCW", "power_kw", "kW", .001), ("DCSt", "state", "", 1)]:
            add(f"mppt_{index}_{suffix}", f"MPPT {index} {field}", 160, f"module/{index}/{field}",
                unit=unit, scale=scale, channel=index)
    return points


def commands():
    return [InverterPoint(key="active_power_limit", label="Limite potenza temporaneo (120 s)", kind="command",
        register_type="holding", address=5, length=1, datatype="uint16", unit="%", writable=True,
        protocol_meta={"driver": PVS_DRIVER, "min_value": 0., "max_value": 100., "step": .1,
            "refresh_interval_seconds": 45, "section": "Controllo potenza", "revert_seconds": 120}),
        InverterPoint(key="disable_power_limit", label="Disabilita limite potenza", kind="command",
        register_type="holding", address=9, length=1, datatype="uint16", writable=True,
        protocol_meta={"driver": PVS_DRIVER, "min_value": 0., "max_value": 0., "step": 1., "section": "Controllo potenza"})]


def build_fimer_pvs_models(protocol, transport):
    if (protocol, transport) not in {("modbus_tcp", "tcp"), ("modbus_rtu", "serial")}:
        return []
    result = []
    for model in PVS_MODELS:
        defaults = {"timeout_seconds": 2., "retries": 0, "poll_interval_seconds": 15,
            "test_register": 40000, "test_function": "holding", "test_count": 2}
        defaults.update({"host": "", "port": 502, "unit_id": 1} if transport == "tcp" else
            {"port": "", "slave_id": 1, "baud_rate": 19200, "byte_size": 8, "parity": "N", "stop_bits": 1})
        result.append(InverterModel(brand="ABB/FIMER", model=model, protocol=protocol, transport=transport,
            defaults=defaults, telemetry_points=telemetry_points(), command_points=commands(),
            features=["SunSpec con identificazione modello", "MPPT rilevati dal dispositivo (fino a 6)",
                "Limite temporaneo 120 s; rinnovo flotta ogni 45 s", "Rilettura abilitazione e riferimento", "Collaudo hardware da completare"],
            catalog_meta={"series": "PVS-100/120-TL", "verification_status": "documented_not_field_tested", "field_tested": False,
                "source_document": "FIMER PVS-100/120-TL SunSpec PICS", "source_version": PVS_MAP["source_version"],
                "source_url": PVS_MAP["source_url"], "last_reviewed_at": "2026-11-17", "discovery_enabled": False,
                "notes": "Confermare firmware e parametri Modbus. Controllo SunSpec da abilitare sull'inverter. Limite riferito al WMax effettivo. Comando manuale valido 120 s, poi ripristino dei default inverter; flotta attiva rinnova il limite. Nessun comando reattivo o on/off implementato. Nessun collaudo fisico."}))
    return result
