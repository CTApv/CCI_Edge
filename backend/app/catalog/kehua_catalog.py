from app.models.inverter_model import InverterModel, InverterPoint


KEHUA_BRAND = "Kehua"

KEHUA_MODELS: list[tuple[str, float]] = [
    ("SPI320K-B-H series", 320.0),
    ("SPI250K-B-H series", 250.0),
    ("SPI125K-B series", 125.0),
    ("SPI33K-B X2 series", 33.0),
    ("SPI23K-B X2 series", 23.0),
    ("SPI12K-B X2 series", 12.0),
    ("SPI8000-B X2 series", 8.0),
]

KEHUA_DEVICE_TYPE_MAP = {
    1: "Three-phase PV inverter",
    2: "Three-phase PV energy-storage inverter",
    10: "Single-phase PV inverter",
}

KEHUA_PROTOCOL_TYPE_MAP = {
    1: "Three-phase protocol",
    2: "Single-phase protocol",
    3: "PID protocol",
}

KEHUA_RUNNING_STATUS_MAP = {
    0x0000: "Standby: no DC input",
    0x0001: "Standby: DC under-voltage",
    0x0002: "Standby: self-check",
    0x0100: "Grid-tied",
    0x0101: "Inverter prestart",
    0x0102: "Unit derating",
    0x0103: "Power-ration derating",
    0x0104: "Night SVG",
    0x0200: "Fault",
    0x0201: "Fault: waiting for recovery",
    0x0300: "Off",
    0x0400: "Off-line",
}

KEHUA_PID_RUNNING_STATUS_MAP = {
    0: "Standby",
    1: "Repairing",
    2: "Off",
    3: "Fault",
}

KEHUA_ENABLE_DISABLE_MAP = {
    0: "Disabled",
    1: "Enabled",
}

KEHUA_ON_OFF_MAP = {
    0: "Off",
    1: "On",
}

KEHUA_RECOVER_GRID_TIED_MAP = {
    0: "No recovery",
    1: "Recover",
}

KEHUA_HLVRT_MODE_MAP = {
    1: "Zero reactive power",
    2: "Reactive power support",
    3: "Zero current",
}

KEHUA_GRID_FREQUENCY_MAP = {
    0: "50 Hz",
    1: "60 Hz",
}

KEHUA_ACTIVE_POWER_MODE_MAP = {
    0: "Disabled",
    1: "Absolute value",
    2: "Per-unit value",
}

KEHUA_REACTIVE_POWER_MODE_MAP = {
    0: "Disabled",
    1: "Absolute value",
    2: "Per-unit value",
    3: "Power factor",
}

KEHUA_PID_REPAIR_FUNCTION_MAP = {
    0: "Disabled",
    1: "Night PID",
    2: "Day PID",
    3: "24h PID",
}

KEHUA_PV_TYPE_MAP = {
    0: "N-type",
    1: "P-type",
}

KEHUA_METER_TYPE_MAP = {
    0: "None",
    1: "CHINT DTSU666",
    2: "YADA DTSD3366D-W1-A",
    6: "CHINT DDSU666",
    7: "YADA DDS3366D-1P",
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
    display_format: str | None = None,
    display_width: int | None = None,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {"section": section}
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map
    if display_format is not None:
        protocol_meta["display_format"] = display_format
    if display_width is not None:
        protocol_meta["display_width"] = display_width

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
    protocol_meta: dict[str, object] = {"section": section}
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
        length=2 if datatype in {"uint32", "int32"} else 1,
        datatype=datatype,
        scale=scale,
        unit=unit,
        writable=True,
        protocol_meta=protocol_meta,
    )


def build_kehua_telemetry() -> list[InverterPoint]:
    points: list[InverterPoint] = [
        telemetry_point("manufacturer_info", "Manufacturer", 10000, 15, "ascii_string", section="Identification"),
        telemetry_point("device_model", "Device model", 10015, 10, "ascii_string", section="Identification"),
        telemetry_point("serial_number", "Serial number", 10025, 10, "ascii_string", section="Identification"),
        telemetry_point("hmi_version", "HMI version", 10035, 5, "ascii_string", section="Identification"),
        telemetry_point("control_software_version_1", "Control software version 1", 10040, 5, "ascii_string", section="Identification"),
        telemetry_point("control_software_version_2", "Control software version 2", 10045, 5, "ascii_string", section="Identification"),
        telemetry_point("control_software_version_3", "Control software version 3", 10050, 5, "ascii_string", section="Identification"),
        telemetry_point("control_software_version_4", "Control software version 4", 10055, 5, "ascii_string", section="Identification"),
        telemetry_point("control_software_version_5", "Control software version 5", 10060, 5, "ascii_string", section="Identification"),
        telemetry_point("control_software_version_6", "Control software version 6", 10065, 5, "ascii_string", section="Identification"),
        telemetry_point("device_type", "Device type", 10070, 1, "uint16", section="Identification", enum_map=KEHUA_DEVICE_TYPE_MAP),
        telemetry_point("protocol_type", "Protocol type", 10071, 1, "uint16", section="Identification", enum_map=KEHUA_PROTOCOL_TYPE_MAP),
        telemetry_point("protocol_version", "Protocol version", 10072, 5, "ascii_string", section="Identification"),
        telemetry_point("pv_array_count", "Total PV array quantity", 10077, 1, "uint16", section="Rating"),
        telemetry_point("mppt_count", "MPPT number", 10078, 1, "uint16", section="Rating"),
        telemetry_point("probation_remaining_hours", "Probation remaining", 10079, 1, "uint16", unit="h", section="Rating"),
        telemetry_point("rated_power_kw", "Rated power", 10080, 1, "uint16", scale=0.1, unit="kW", section="Rating"),
        telemetry_point("max_apparent_power_kva", "Max apparent power", 10081, 1, "uint16", scale=0.1, unit="kVA", section="Rating"),
        telemetry_point("max_active_power_kw", "Max active power", 10082, 1, "uint16", scale=0.1, unit="kW", section="Rating"),
        telemetry_point("max_reactive_power_kvar", "Max reactive power", 10083, 1, "uint16", scale=0.1, unit="kVAr", section="Rating"),
        telemetry_point("min_power_factor", "Min power factor", 10084, 1, "uint16", scale=0.001, section="Rating"),
    ]

    for index in range(16):
        points.append(
            telemetry_point(
                f"alarm_word_{index + 1}",
                f"Alarm {index + 1}",
                11000 + index,
                1,
                "uint16",
                section="Status and alarms",
                display_format="hex",
                display_width=4,
            )
        )

    points.extend(
        [
            telemetry_point("running_status", "Running status", 11016, 1, "uint16", section="Status and alarms", summary_metric="status", enum_map=KEHUA_RUNNING_STATUS_MAP),
            telemetry_point("daily_energy_kwh", "Daily grid-tied energy", 11017, 1, "uint16", scale=0.1, unit="kWh", section="Energy", summary_metric="daily_energy_kwh"),
            telemetry_point("total_energy_kwh", "Total grid-tied energy", 11018, 2, "uint32", scale=0.1, unit="kWh", section="Energy", summary_metric="total_energy_kwh"),
            telemetry_point("grid_frequency_hz", "Grid frequency", 11020, 1, "uint16", scale=0.01, unit="Hz", section="AC grid"),
            telemetry_point("apparent_power_kva", "Apparent power", 11021, 2, "uint32", scale=0.001, unit="kVA", section="Power"),
            telemetry_point("active_power_kw", "Active power", 11023, 2, "uint32", scale=0.001, unit="kW", section="Power", summary_metric="power_kw"),
            telemetry_point("reactive_power_kvar", "Reactive power", 11025, 2, "int32", scale=0.001, unit="kVAr", section="Power"),
            telemetry_point("power_factor", "Power factor", 11027, 1, "int16", scale=0.001, section="Power"),
            telemetry_point("grid_voltage_uv_v", "Grid voltage U/UV", 11028, 1, "uint16", scale=0.1, unit="V", section="AC grid"),
            telemetry_point("grid_voltage_vw_v", "Grid voltage V/VW", 11029, 1, "uint16", scale=0.1, unit="V", section="AC grid"),
            telemetry_point("grid_voltage_wu_v", "Grid voltage W/WU", 11030, 1, "uint16", scale=0.1, unit="V", section="AC grid"),
            telemetry_point("grid_current_u_a", "Grid current U", 11031, 1, "uint16", scale=0.1, unit="A", section="AC grid"),
            telemetry_point("grid_current_v_a", "Grid current V", 11032, 1, "uint16", scale=0.1, unit="A", section="AC grid"),
            telemetry_point("grid_current_w_a", "Grid current W", 11033, 1, "uint16", scale=0.1, unit="A", section="AC grid"),
            telemetry_point("ac_residual_current_ma", "AC residual current", 11034, 1, "uint16", scale=0.1, unit="mA", section="AC grid"),
            telemetry_point("heat_sink_boost_temperature_c", "Heat sink boost temperature", 11035, 1, "int16", scale=0.1, unit="C", section="Thermal"),
            telemetry_point("heat_sink_inverter_temperature_c", "Heat sink inverter temperature", 11036, 1, "int16", scale=0.1, unit="C", section="Thermal"),
            telemetry_point("power_module_boost_temperature_c", "Power module boost temperature", 11037, 1, "int16", scale=0.1, unit="C", section="Thermal"),
            telemetry_point("power_module_inverter_temperature_c", "Power module inverter temperature", 11038, 1, "int16", scale=0.1, unit="C", section="Thermal"),
            telemetry_point("inner_temperature_c", "Inner temperature", 11039, 1, "int16", scale=0.1, unit="C", section="Thermal", summary_metric="temperature_c"),
            telemetry_point("inverter_bus_voltage_v", "Bus voltage inverter", 11040, 1, "uint16", scale=0.1, unit="V", section="DC bus"),
            telemetry_point("insulation_resistance_kohm", "Insulation resistance", 11041, 1, "uint16", scale=0.1, unit="kOhm", section="DC bus"),
            telemetry_point("pv_input_power_kw", "PV input power", 11042, 1, "uint16", scale=0.1, unit="kW", section="PV input"),
            telemetry_point("bus_capacitance_uf", "Bus capacitance", 11043, 1, "uint16", unit="uF", section="DC bus"),
            telemetry_point("pid_running_status", "PID running status", 11044, 1, "uint16", section="PID", enum_map=KEHUA_PID_RUNNING_STATUS_MAP),
            telemetry_point("pid_repair_voltage_v", "PID repair voltage", 11045, 1, "uint16", scale=0.1, unit="V", section="PID"),
        ]
    )

    for index in range(16):
        points.append(
            telemetry_point(
                f"mppt_{index + 1}_voltage_v",
                f"MPPT {index + 1} voltage",
                11064 + index,
                1,
                "uint16",
                scale=0.1,
                unit="V",
                section="MPPT",
            )
        )
    for index in range(16):
        points.append(
            telemetry_point(
                f"mppt_{index + 1}_current_a",
                f"MPPT {index + 1} current",
                11080 + index,
                1,
                "int16",
                scale=0.1,
                unit="A",
                section="MPPT",
            )
        )
    for index in range(32):
        points.append(
            telemetry_point(
                f"pv_{index + 1}_voltage_v",
                f"PV {index + 1} voltage",
                11104 + index,
                1,
                "uint16",
                scale=0.1,
                unit="V",
                section="PV strings",
            )
        )
    for index in range(32):
        points.append(
            telemetry_point(
                f"pv_{index + 1}_current_a",
                f"PV {index + 1} current",
                11136 + index,
                1,
                "int16",
                scale=0.1,
                unit="A",
                section="PV strings",
            )
        )
    for index in range(32):
        points.append(
            telemetry_point(
                f"pv_{index + 1}_power_kw",
                f"PV {index + 1} power",
                11168 + index,
                1,
                "int16",
                scale=0.1,
                unit="kW",
                section="PV strings",
            )
        )

    return points


def build_kehua_commands(max_active_power_kw: float) -> list[InverterPoint]:
    return [
        command_point("on_off", "ON/OFF", 12000, "uint16", section="Control", min_value=0, max_value=1, step=1, enum_map=KEHUA_ON_OFF_MAP),
        command_point("self_start_after_power_on", "Self-start after power on", 12001, "uint16", section="Control", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("recover_grid_tied", "Recover grid-tied", 12002, "uint16", section="Control", min_value=0, max_value=1, step=1, enum_map=KEHUA_RECOVER_GRID_TIED_MAP),
        command_point("self_recover_after_grid_abnormal", "Self-recover once grid abnormal", 12003, "uint16", section="Control", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("hlvrt_mode", "H/LVRT mode", 12004, "uint16", section="Grid support", min_value=1, max_value=3, step=1, enum_map=KEHUA_HLVRT_MODE_MAP),
        command_point("initiative_islanding", "Initiative islanding", 12005, "uint16", section="Grid support", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("insulation_resistance_detection", "Insulation resistance detection", 12006, "uint16", section="Protection", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("phase_self_adapt", "Phase self-adapt", 12007, "uint16", section="Grid support", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("night_svg", "Night SVG", 12008, "uint16", section="Reactive power", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("reactive_first", "Reactive first", 12009, "uint16", section="Reactive power", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("rated_grid_frequency_setting", "Rated grid frequency", 12010, "uint16", section="Grid support", min_value=0, max_value=1, step=1, enum_map=KEHUA_GRID_FREQUENCY_MAP),
        command_point("spd_abnormal_alarm", "SPD abnormal alarm", 12011, "uint16", section="Protection", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("pid_repair_function", "PID repair function", 12012, "uint16", section="PID", min_value=0, max_value=3, step=1, enum_map=KEHUA_PID_REPAIR_FUNCTION_MAP),
        command_point("dc_arc_detection", "DC arc detection", 12013, "uint16", section="Protection", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("clear_dc_arc_alarm", "Clear DC arc alarm", 12014, "uint16", section="Protection", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("active_power_control_mode", "Active power control mode", 12016, "uint16", section="Active power control", min_value=0, max_value=2, step=1, enum_map=KEHUA_ACTIVE_POWER_MODE_MAP),
        command_point("active_power_setpoint_kw", "Active power setpoint absolute", 12017, "uint16", scale=0.1, unit="kW", section="Active power control", min_value=0, max_value=max_active_power_kw),
        command_point("active_power_limit", "Active power setpoint percent", 12018, "uint16", scale=0.1, unit="%", section="Active power control", min_value=0, max_value=100.0),
        command_point("reactive_power_control_mode", "Reactive power control mode", 12019, "uint16", section="Reactive power", min_value=0, max_value=3, step=1, enum_map=KEHUA_REACTIVE_POWER_MODE_MAP),
        command_point("reactive_power_setpoint_kvar", "Reactive power setpoint absolute", 12020, "int16", scale=0.1, unit="kVAr", section="Reactive power"),
        command_point("reactive_power_setpoint_percent", "Reactive power setpoint percent", 12021, "int16", scale=0.1, unit="%", section="Reactive power", min_value=-100.0, max_value=100.0),
        command_point("power_factor_setpoint", "Power factor setpoint", 12022, "int16", scale=0.001, section="Reactive power", min_value=-1.0, max_value=1.0),
        command_point("grid_tied_recover_time_s", "Grid-tied recover time", 12023, "uint16", unit="s", section="Grid support"),
        command_point("power_rate_percent_per_s", "Power rate", 12024, "uint16", scale=0.01, unit="%/s", section="Active power control"),
        command_point("on_off_soft_start_rate_percent_per_s", "ON/OFF soft-start rate", 12025, "uint16", scale=0.01, unit="%/s", section="Active power control"),
        command_point("anti_countercurrent_function", "Anti-countercurrent function", 12029, "uint16", section="Grid support", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("backflow_control_power_percent", "Backflow control power", 12030, "int16", scale=0.1, unit="%", section="Grid support"),
        command_point("backflow_protection_power_percent", "Backflow protection power", 12031, "int16", scale=0.1, unit="%", section="Grid support"),
        command_point("backflow_protection_time_s", "Backflow protection time", 12032, "uint16", scale=0.1, unit="s", section="Grid support"),
        command_point("backflow_recovery_time_s", "Backflow recovery time", 12033, "uint16", scale=0.1, unit="s", section="Grid support"),
        command_point("pv_type", "PV type", 12034, "uint16", section="PID", min_value=0, max_value=1, step=1, enum_map=KEHUA_PV_TYPE_MAP),
        command_point("pid_repair_voltage_setting_v", "PID repair voltage setting", 12035, "uint16", scale=0.1, unit="V", section="PID"),
        command_point("pid_repair_time_min", "PID repair time", 12036, "uint16", unit="min", section="PID"),
        command_point("telecommunication_abnormal_protection", "Telecommunication abnormal protection", 12038, "uint16", section="Protection", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("telecommunication_abnormal_protection_time_s", "Telecommunication abnormal protection time", 12039, "uint16", unit="s", section="Protection"),
        command_point("drm_function", "DRM function", 12040, "uint16", section="Grid support", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("ac_watt_hour_meter_type", "AC watt-hour meter", 12041, "uint16", section="Metering", enum_map=KEHUA_METER_TYPE_MAP),
        command_point("dc_fast_shutdown", "DC fast shutdown", 12042, "uint16", section="Protection", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("detect_switch_offline_grid_tied", "Detection of switch between off-line and grid-tied", 12043, "uint16", section="Grid support", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
        command_point("control_switch_offline_grid_tied", "Control of switch between off-line and grid-tied", 12044, "uint16", section="Grid support", min_value=0, max_value=1, step=1, enum_map=KEHUA_ENABLE_DISABLE_MAP),
    ]


def build_kehua_defaults(protocol: str) -> dict[str, str | int | float | bool]:
    common_defaults: dict[str, str | int | float | bool] = {
        "timeout_seconds": 2,
        "retries": 1,
        "poll_interval_seconds": 15,
        "test_register": 11016,
        "test_count": 1,
        "test_function": "holding",
        "max_registers_per_request": 100,
        "inter_request_delay_ms": 100,
    }
    if protocol == "modbus_rtu":
        return {
            "port": "COM1",
            "slave_id": 1,
            "baud_rate": 9600,
            "parity": "N",
            "stop_bits": 1,
            "byte_size": 8,
            **common_defaults,
        }
    return {
        "host": "192.168.1.10",
        "port": 502,
        "unit_id": 1,
        **common_defaults,
    }


def build_kehua_models(protocol: str, transport: str) -> list[InverterModel]:
    telemetry_points = build_kehua_telemetry()
    defaults = build_kehua_defaults(protocol)
    return [
        InverterModel(
            brand=KEHUA_BRAND,
            model=model_name,
            protocol=protocol,
            transport=transport,
            defaults=defaults,
            features=[
                "protocol v2.0",
                "telemetry ac dc mppt e stringhe pv",
                "allarmi e running status",
                "controllo potenza attiva e reattiva",
                "modbus rtu e tcp",
            ],
            telemetry_points=telemetry_points,
            command_points=build_kehua_commands(max_active_power_kw=max_active_power_kw),
        )
        for model_name, max_active_power_kw in KEHUA_MODELS
    ]
