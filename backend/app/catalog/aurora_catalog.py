from __future__ import annotations

from app.models.inverter_model import InverterModel, InverterPoint
from app.services.aurora_service import AURORA_DRIVER

AURORA_PROTOCOL = "aurora"
AURORA_TRANSPORT = "serial"
AURORA_POWERONE_BRAND = "PowerOne"

_AURORA_DEFAULTS: dict[str, str | int | float | bool] = {
    "port": "COM1",
    "address": 2,
    "baud_rate": 19200,
    "parity": "N",
    "stop_bits": 1,
    "byte_size": 8,
    "timeout_seconds": 0.5,
    "retries": 1,
    "poll_interval_seconds": 15,
    "inter_request_delay_ms": 20,
    "retry_delay_ms": 40,
    "float_endian": ">",
}

_POWER_REDUCTION_MODELS = (
    "Aurora Power One PVI CENTRAL330TL",
    "Aurora Power One PVI CENTRAL275TL",
    "Aurora Power One PVI CENTRAL 400TL",
    "Aurora Power One PVI CENTRAL 165TL",
    "ABB/Aurora PVI-TRIO-27.6-TL-OUTD-S2X-400",
    "ABB/Aurora PVI-TRIO-20.0-TL-OUTD-S2X-400",
    "ABB/Aurora PVI-12.5-TL-OUTD STAGE1",
    "Aurora PVI-10.0-OUTD-IT",
)

_AURORA_MODEL_IDENTIFIERS: dict[str, tuple[str, ...]] = {
    "Aurora Power One PVI CENTRAL330TL": ("3119", "3M04", "3M05", "3L07", "3M67"),
    "ABB/Aurora PVI-TRIO-27.6-TL-OUTD-S2X-400": ("3M22",),
    "ABB/Aurora PVI-TRIO-20.0-TL-OUTD-S2X-400": ("3M44",),
    "ABB/Aurora PVI-12.5-TL-OUTD STAGE1": ("3G83",),
    "Aurora PVI-10.0-OUTD-IT": ("3G82",),
}


def telemetry_point(
    key: str,
    label: str,
    *,
    aurora_method: str,
    field: str | None = None,
    tom: int | None = None,
    datatype: str = "float32",
    scale: float = 1.0,
    unit: str = "",
    section: str,
    summary_metric: str | None = None,
    display_format: str | None = None,
    display_width: int | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {
        "driver": AURORA_DRIVER,
        "section": section,
        "aurora_method": aurora_method,
    }
    if field is not None:
        protocol_meta["field"] = field
    if tom is not None:
        protocol_meta["tom"] = tom
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if display_format is not None:
        protocol_meta["display_format"] = display_format
    if display_width is not None:
        protocol_meta["display_width"] = display_width

    return InverterPoint(
        key=key,
        label=label,
        kind="telemetry",
        register_type="aurora",
        address=0 if tom is None else tom,
        length=1,
        datatype=datatype,
        scale=scale,
        unit=unit,
        protocol_meta=protocol_meta,
    )


def command_point(
    key: str,
    label: str,
    *,
    datatype: str,
    section: str,
    unit: str = "",
    min_value: float | None = None,
    max_value: float | None = None,
    step: float | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {
        "driver": AURORA_DRIVER,
        "section": section,
        "aurora_method": "set_power_limit",
    }
    if min_value is not None:
        protocol_meta["min_value"] = min_value
    if max_value is not None:
        protocol_meta["max_value"] = max_value
    if step is not None:
        protocol_meta["step"] = step

    return InverterPoint(
        key=key,
        label=label,
        kind="command",
        register_type="aurora",
        address=OP_SET_POWER_LIMIT_PLACEHOLDER,
        length=1,
        datatype=datatype,
        unit=unit,
        writable=True,
        protocol_meta=protocol_meta,
    )


OP_SET_POWER_LIMIT_PLACEHOLDER = 151


def build_aurora_telemetry_points() -> list[InverterPoint]:
    return [
        telemetry_point(
            "global_state",
            "Stato globale",
            aurora_method="state",
            field="Global",
            datatype="uint16",
            section="Stato e allarmi",
        ),
        telemetry_point(
            "status",
            "Stato inverter",
            aurora_method="state",
            field="InvState",
            datatype="uint16",
            section="Stato e allarmi",
            summary_metric="status",
        ),
        telemetry_point(
            "dcdc1_state",
            "Stato DC/DC 1",
            aurora_method="state",
            field="DcDc1",
            datatype="uint16",
            section="Stato e allarmi",
        ),
        telemetry_point(
            "dcdc2_state",
            "Stato DC/DC 2",
            aurora_method="state",
            field="DcDc2",
            datatype="uint16",
            section="Stato e allarmi",
        ),
        telemetry_point(
            "alarm_code",
            "Codice allarme",
            aurora_method="state",
            field="Alarm",
            datatype="uint16",
            section="Stato e allarmi",
            display_format="hex",
            display_width=2,
        ),
        telemetry_point(
            "grid_voltage_v",
            "Tensione rete",
            aurora_method="dsp",
            tom=1,
            unit="V",
            section="Rete AC",
        ),
        telemetry_point(
            "grid_current_a",
            "Corrente rete",
            aurora_method="dsp",
            tom=2,
            unit="A",
            section="Rete AC",
        ),
        telemetry_point(
            "active_power_kw",
            "Potenza attiva",
            aurora_method="dsp",
            tom=3,
            scale=0.001,
            unit="kW",
            section="Potenza",
            summary_metric="power_kw",
        ),
        telemetry_point(
            "grid_frequency_hz",
            "Frequenza rete",
            aurora_method="dsp",
            tom=4,
            unit="Hz",
            section="Rete AC",
        ),
        telemetry_point(
            "dc_input1_power_kw",
            "Potenza DC 1",
            aurora_method="dsp",
            tom=8,
            scale=0.001,
            unit="kW",
            section="Ingressi DC",
        ),
        telemetry_point(
            "dc_input2_power_kw",
            "Potenza DC 2",
            aurora_method="dsp",
            tom=9,
            scale=0.001,
            unit="kW",
            section="Ingressi DC",
        ),
        telemetry_point(
            "temperature_c",
            "Temperatura inverter",
            aurora_method="dsp",
            tom=21,
            unit="C",
            section="Termico",
            summary_metric="temperature_c",
        ),
        telemetry_point(
            "temperature_booster_c",
            "Temperatura booster",
            aurora_method="dsp",
            tom=22,
            unit="C",
            section="Termico",
        ),
        telemetry_point(
            "dc_input1_voltage_v",
            "Tensione ingresso 1",
            aurora_method="dsp",
            tom=23,
            unit="V",
            section="Ingressi DC",
        ),
        telemetry_point(
            "dc_input1_current_a",
            "Corrente ingresso 1",
            aurora_method="dsp",
            tom=25,
            unit="A",
            section="Ingressi DC",
        ),
        telemetry_point(
            "dc_input2_voltage_v",
            "Tensione ingresso 2",
            aurora_method="dsp",
            tom=26,
            unit="V",
            section="Ingressi DC",
        ),
        telemetry_point(
            "dc_input2_current_a",
            "Corrente ingresso 2",
            aurora_method="dsp",
            tom=27,
            unit="A",
            section="Ingressi DC",
        ),
        telemetry_point(
            "insulation_resistance_mohm",
            "Resistenza isolamento",
            aurora_method="dsp",
            tom=30,
            unit="Mohm",
            section="Diagnostica",
        ),
        telemetry_point(
            "daily_energy_kwh",
            "Energia giornaliera",
            aurora_method="dsp",
            tom=78,
            unit="kWh",
            section="Energia",
            summary_metric="daily_energy_kwh",
        ),
        telemetry_point(
            "total_energy_kwh",
            "Energia totale",
            aurora_method="dsp",
            tom=79,
            unit="kWh",
            section="Energia",
            summary_metric="total_energy_kwh",
        ),
    ]


def build_aurora_command_points() -> list[InverterPoint]:
    return [
        command_point(
            "active_power_limit",
            "Limite potenza attiva",
            datatype="uint16",
            unit="%",
            section="Controllo potenza",
            min_value=0.0,
            max_value=100.0,
            step=1.0,
        )
    ]


def _build_model(
    *,
    brand: str,
    model: str,
    power_reduction: bool,
) -> InverterModel:
    features = ["telemetry", "fault codes", "serial rs485"]
    if power_reduction:
        features.append("active power limit")
    return InverterModel(
        brand=brand,
        model=model,
        protocol=AURORA_PROTOCOL,
        transport=AURORA_TRANSPORT,
        defaults=dict(_AURORA_DEFAULTS),
        features=features,
        telemetry_points=build_aurora_telemetry_points(),
        command_points=build_aurora_command_points() if power_reduction else [],
    )


def build_aurora_models() -> list[InverterModel]:
    models = [
        _build_model(
            brand="Generic",
            model="Aurora Inverter",
            power_reduction=True,
        )
    ]
    models.extend(
        _build_model(
            brand=AURORA_POWERONE_BRAND,
            model=model_name,
            power_reduction=True,
        )
        for model_name in _POWER_REDUCTION_MODELS
    )
    return models


def _normalize_aurora_identifier(raw_value: str | None) -> str:
    if not raw_value:
        return ""
    return raw_value.strip().strip("-").strip().upper()


def resolve_aurora_candidate_profiles(
    part_number: str | None = None,
    version_signature: str | None = None,
) -> tuple[tuple[str, str, str, str], ...]:
    normalized = _normalize_aurora_identifier(part_number)
    if normalized == "":
        normalized = _normalize_aurora_identifier(version_signature)
    if normalized == "":
        return ()

    profiles: list[tuple[str, str, str, str]] = []
    for model_name, signatures in _AURORA_MODEL_IDENTIFIERS.items():
        if normalized not in signatures:
            continue
        profiles.append(
            (
                AURORA_POWERONE_BRAND,
                model_name,
                AURORA_PROTOCOL,
                AURORA_TRANSPORT,
            )
        )
    return tuple(sorted(set(profiles)))
