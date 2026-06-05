from app.models.inverter_model import InverterModel, InverterPoint
from app.services.bonfiglioli_modbus_service import BONFIGLIOLI_DRIVER

BONFIGLIOLI_PARAMETER_OFFSET = 1


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
    protocol_meta: dict[str, str | int | float | bool] | None = None,
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
    protocol_meta: dict[str, str | int | float | bool] | None = None,
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


def bonfiglioli_telemetry_point(
    key: str,
    label: str,
    parameter: int,
    datatype: str,
    *,
    scale: float = 1.0,
    unit: str = "",
    section: str,
    visible: bool = True,
    summary_metric: str | None = None,
    display_format: str | None = None,
    display_prefix: str | None = None,
    display_width: int | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, str | int | float | bool] = {
        "driver": BONFIGLIOLI_DRIVER,
        "dataset": 0,
        "section": section,
        "manual_parameter": parameter,
        "address_offset": BONFIGLIOLI_PARAMETER_OFFSET,
    }
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if display_format is not None:
        protocol_meta["display_format"] = display_format
    if display_prefix is not None:
        protocol_meta["display_prefix"] = display_prefix
    if display_width is not None:
        protocol_meta["display_width"] = display_width

    return telemetry_point(
        key=key,
        label=label,
        register_type="holding",
        address=parameter,
        length=2 if datatype in {"int32", "uint32"} else 1,
        datatype=datatype,
        scale=scale,
        unit=unit,
        visible=visible,
        protocol_meta=protocol_meta,
    )


def bonfiglioli_command_point(
    key: str,
    label: str,
    parameter: int,
    datatype: str,
    *,
    scale: float = 1.0,
    unit: str = "",
    section: str = "Control",
    min_value: float | None = None,
    max_value: float | None = None,
    step: float | None = None,
    field_verified_parameter: int | None = None,
    dataset: int = 0,
) -> InverterPoint:
    protocol_meta: dict[str, str | int | float | bool] = {
        "driver": BONFIGLIOLI_DRIVER,
        "dataset": dataset,
        "section": section,
        "manual_parameter": parameter,
        "address_offset": BONFIGLIOLI_PARAMETER_OFFSET,
    }
    if min_value is not None:
        protocol_meta["min_value"] = min_value
    if max_value is not None:
        protocol_meta["max_value"] = max_value
    if step is not None:
        protocol_meta["step"] = step
    if field_verified_parameter is not None:
        protocol_meta["field_verified_parameter"] = field_verified_parameter

    return command_point(
        key=key,
        label=label,
        register_type="holding",
        address=parameter,
        length=2 if datatype in {"int32", "uint32"} else 1,
        datatype=datatype,
        scale=scale,
        unit=unit,
        protocol_meta=protocol_meta,
    )


def build_bonfiglioli_telemetry() -> list[InverterPoint]:
    return [
        bonfiglioli_telemetry_point(
            "active_power_kw",
            "Active power",
            212,
            "int16",
            scale=0.1,
            unit="kW",
            section="Power and current",
            summary_metric="power_kw",
        ),
        bonfiglioli_telemetry_point(
            "dc_link_voltage_v",
            "DC-link voltage",
            221,
            "uint16",
            scale=0.1,
            unit="V",
            section="DC bus",
        ),
        bonfiglioli_telemetry_point(
            "digital_inputs",
            "Digital inputs",
            249,
            "uint16",
            section="Digital I/O",
            display_format="hex",
            display_width=4,
        ),
        bonfiglioli_telemetry_point(
            "temperature_c",
            "Heat sink temperature",
            254,
            "uint16",
            scale=0.1,
            unit="C",
            section="Thermal",
            summary_metric="temperature_c",
        ),
        bonfiglioli_telemetry_point(
            "inside_temperature_c",
            "Inside temperature",
            255,
            "uint16",
            scale=0.1,
            unit="C",
            section="Thermal",
        ),
        bonfiglioli_telemetry_point(
            "current_error_code",
            "Current error",
            259,
            "uint16",
            section="Status and alarms",
            display_format="hex",
            display_prefix="F",
            display_width=4,
        ),
        bonfiglioli_telemetry_point(
            "total_energy_kwh",
            "Active energy",
            300,
            "uint32",
            unit="kWh",
            section="Counters",
            summary_metric="total_energy_kwh",
        ),
        bonfiglioli_telemetry_point(
            "mains_frequency_hz",
            "Frequency",
            849,
            "uint16",
            scale=0.01,
            unit="Hz",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "power_supply_current_a",
            "Power supply current",
            852,
            "uint16",
            scale=0.1,
            unit="A",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "mains_voltage_v",
            "Mains voltage",
            853,
            "uint16",
            scale=0.1,
            unit="V",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "dc_link_power_kw",
            "DC power",
            855,
            "uint16",
            scale=0.1,
            unit="kW",
            section="DC bus",
        ),
        bonfiglioli_telemetry_point(
            "dc_current_a",
            "DC current",
            860,
            "uint16",
            scale=0.1,
            unit="A",
            section="DC bus",
        ),
        bonfiglioli_telemetry_point(
            "current_a_a",
            "Current a",
            862,
            "uint16",
            scale=0.1,
            unit="A",
            section="Phase currents",
        ),
        bonfiglioli_telemetry_point(
            "current_b_a",
            "Current b",
            863,
            "uint16",
            scale=0.1,
            unit="A",
            section="Phase currents",
        ),
        bonfiglioli_telemetry_point(
            "current_c_a",
            "Current c",
            864,
            "uint16",
            scale=0.1,
            unit="A",
            section="Phase currents",
        ),
        bonfiglioli_telemetry_point(
            "mains_voltage_a_v",
            "Mains voltage a",
            865,
            "uint16",
            scale=0.1,
            unit="V",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "mains_voltage_b_v",
            "Mains voltage b",
            866,
            "uint16",
            scale=0.1,
            unit="V",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "mains_voltage_c_v",
            "Mains voltage c",
            867,
            "uint16",
            scale=0.1,
            unit="V",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "active_power_a_kw",
            "Active power a",
            868,
            "int16",
            scale=0.1,
            unit="kW",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "active_power_b_kw",
            "Active power b",
            869,
            "int16",
            scale=0.1,
            unit="kW",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "active_power_c_kw",
            "Active power c",
            870,
            "int16",
            scale=0.1,
            unit="kW",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "reactive_power_a_kvar",
            "Reactive power a",
            871,
            "int16",
            scale=0.1,
            unit="kVAr",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "reactive_power_b_kvar",
            "Reactive power b",
            872,
            "int16",
            scale=0.1,
            unit="kVAr",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "reactive_power_c_kvar",
            "Reactive power c",
            873,
            "int16",
            scale=0.1,
            unit="kVAr",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "apparent_power_a_kva",
            "Apparent power a",
            874,
            "uint16",
            scale=0.1,
            unit="kVA",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "apparent_power_b_kva",
            "Apparent power b",
            875,
            "uint16",
            scale=0.1,
            unit="kVA",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "apparent_power_c_kva",
            "Apparent power c",
            876,
            "uint16",
            scale=0.1,
            unit="kVA",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "reactive_power_kvar",
            "Reactive power",
            877,
            "int16",
            scale=0.1,
            unit="kVAr",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "apparent_power_kva",
            "Apparent power",
            878,
            "uint16",
            scale=0.1,
            unit="kVA",
            section="Mains",
        ),
        bonfiglioli_telemetry_point(
            "status",
            "Solar status",
            1090,
            "uint16",
            section="Status and alarms",
            summary_metric="status",
            display_format="hex",
            display_prefix="S",
            display_width=4,
        ),
        bonfiglioli_telemetry_point(
            "reactive_power_reference_kvar",
            "Reference value reactive power",
            1161,
            "int16",
            scale=0.1,
            unit="kVAr",
            section="Control",
        ),
    ]


def build_bonfiglioli_commands() -> list[InverterPoint]:
    return [
        bonfiglioli_command_point(
            "active_power_limit",
            "Active power setpoint",
            1019,
            "uint16",
            scale=1.0,
            unit="%",
            section="Power control",
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            field_verified_parameter=1021,
        ),
        bonfiglioli_command_point(
            "fixed_percentage_1_pct",
            "Fixed percentage 1",
            520,
            "int16",
            scale=0.01,
            unit="%",
            min_value=-300.0,
            max_value=300.0,
            step=0.01,
        ),
        bonfiglioli_command_point(
            "reference_dc_link_voltage_v",
            "Reference DC-link voltage",
            801,
            "uint16",
            scale=0.1,
            unit="V",
            min_value=0.0,
            step=0.1,
        ),
        bonfiglioli_command_point(
            "max_dc_link_voltage_deviation_v",
            "Max. DC-link voltage deviation",
            802,
            "uint16",
            scale=0.1,
            unit="V",
            min_value=0.0,
            step=0.1,
        ),
        bonfiglioli_command_point(
            "max_output_current_a",
            "Max. output current",
            803,
            "uint16",
            scale=0.1,
            unit="A",
            min_value=0.0,
            step=0.1,
        ),
        bonfiglioli_command_point(
            "max_feed_current_a",
            "Max. feed current",
            804,
            "uint16",
            scale=0.1,
            unit="A",
            min_value=0.0,
            step=0.1,
        ),
        bonfiglioli_command_point(
            "max_feedback_current_a",
            "Max. feedback current",
            805,
            "uint16",
            scale=0.1,
            unit="A",
            min_value=0.0,
            step=0.1,
        ),
    ]


BONFIGLIOLI_RPS_MODELS = [
    "RPS 280 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 340 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 510 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 680 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 850 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 310 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 380 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 470 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 570 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 760 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 940 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 1110 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 420 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 620 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 830 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 1040 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 1220 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
    "RPS 1460 TL Inverter Module AEC 500 - 50 A (PN 605 551 650 RAL)",
]


def build_bonfiglioli_models(protocol: str, transport: str) -> list[InverterModel]:
    if protocol == "modbus_rtu":
        defaults = {
            "port": "COM1",
            "slave_id": 1,
            "baud_rate": 19200,
            "parity": "E",
            "stop_bits": 2,
            "byte_size": 8,
            "timeout_seconds": 5,
            "retries": 1,
            "poll_interval_seconds": 15,
            "parameter_offset": BONFIGLIOLI_PARAMETER_OFFSET,
            "test_register": 223,
            "test_register_manual": 222,
            "test_count": 1,
            "test_function": "holding",
        }
    else:
        defaults = {
            "host": "192.168.1.120",
            "port": 502,
            "unit_id": 1,
            "timeout_seconds": 5,
            "retries": 1,
            "poll_interval_seconds": 15,
            "parameter_offset": BONFIGLIOLI_PARAMETER_OFFSET,
            "test_register": 223,
            "test_register_manual": 222,
            "test_count": 1,
            "test_function": "holding",
        }

    return [
        InverterModel(
            brand="Bonfiglioli",
            model=model,
            protocol=protocol,
            transport=transport,
            defaults=defaults,
            features=[
                "bonfiglioli aec profile",
                "parameter-based modbus access",
                "field offset +1",
                "dynamic telemetry",
                "numeric parameter writes",
            ],
            telemetry_points=build_bonfiglioli_telemetry(),
            command_points=build_bonfiglioli_commands(),
        )
        for model in BONFIGLIOLI_RPS_MODELS
    ]
