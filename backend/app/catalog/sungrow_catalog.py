from app.models.inverter_model import InverterModel, InverterPoint


SUNGROW_BRAND = "SUNGROW"
SUNGROW_MODELS = (
    "PV Grid-Connected String Inverter V1.1",
    "SG KTL/KTL-M/HV String Inverter",
    "SG CX/RT/HX String Inverter",
)

SUNGROW_WORK_STATE_MAP = {
    0x0000: "Run",
    0x8000: "Stop",
    0x1300: "Key stop",
    0x1500: "Emergency stop",
    0x1400: "Standby",
    0x1200: "Initial standby",
    0x1600: "Starting",
    0x9100: "Alarm run",
    0x8100: "Derating run",
    0x8200: "Dispatch run",
    0x5500: "Fault run",
    0x2500: "Communication fault",
}

SUNGROW_DEVICE_TYPE_MAP = {
    0x010F: "SG60KTL",
    0x0136: "SG60KU",
    0x0134: "SG33KTL-M",
    0x0074: "SG36KTL-M",
    0x0135: "SG40KTL-M",
    0x011B: "SG50KTL-M",
    0x0131: "SG60KTL-M",
    0x0132: "SG60KU-M",
    0x0137: "SG49K5J",
    0x013F: "SG8KTL-M",
    0x013E: "SG10KTL-M",
    0x013C: "SG12KTL-M",
    0x0138: "SG80KTL",
    0x0139: "SG80KTL-M",
    0x013A: "SG80HV",
    0x013B: "SG125HV",
}

SUNGROW_POWER_LIMIT_SWITCH_MAP = {
    0xAA: "Enable",
    0x55: "Disable",
}

SUNGROW_START_STOP_MAP = {
    0xCF: "Start",
    0xCE: "Stop",
    0xBB: "Emergency stop",
}


def input_addr(register: int) -> int:
    return register - 1


def holding_addr(register: int) -> int:
    return register - 1


def telemetry_point(
    key: str,
    label: str,
    register: int,
    length: int,
    datatype: str,
    *,
    register_type: str = "input",
    scale: float = 1.0,
    unit: str = "",
    visible: bool = True,
    section: str,
    summary_metric: str | None = None,
    enum_map: dict[int, str] | None = None,
    command: str | None = None,
    heartbeat: bool = False,
    optional_block: bool = False,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {
        "section": section,
        "manual_register": register,
    }
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
        address=input_addr(register) if register_type == "input" else holding_addr(register),
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
    register: int,
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
        "manual_register": register,
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
        address=holding_addr(register),
        length=1,
        datatype=datatype,
        scale=scale,
        unit=unit,
        writable=True,
        protocol_meta=protocol_meta,
    )


def build_sungrow_telemetry() -> list[InverterPoint]:
    points = [
        telemetry_point("protocol_number", "Protocol number", 4950, 2, "uint32", visible=False, section="Identity"),
        telemetry_point("protocol_version", "Protocol version", 4952, 2, "uint32", visible=False, section="Identity"),
        telemetry_point("arm_software_version", "ARM software version", 4954, 15, "ascii_string", visible=False, section="Identity"),
        telemetry_point("dsp_software_version", "DSP software version", 4969, 15, "ascii_string", visible=False, section="Identity"),
        telemetry_point("serial_number", "Serial number", 4990, 10, "ascii_string", visible=False, section="Identity"),
        telemetry_point("device_type_code", "Device type code", 5000, 1, "uint16", visible=False, section="Identity", enum_map=SUNGROW_DEVICE_TYPE_MAP),
        telemetry_point("nominal_active_power_kw", "Nominal active power", 5001, 1, "uint16", scale=0.1, unit="kW", section="Rating"),
        telemetry_point("output_type", "Output type", 5002, 1, "uint16", section="Grid"),
        telemetry_point("daily_energy_kwh", "Daily power yields", 5003, 1, "uint16", scale=0.1, unit="kWh", section="Energy", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_kwh", "Total power yields", 5004, 2, "uint32", unit="kWh", section="Energy", summary_metric="total_energy_kwh"),
        telemetry_point("total_running_time_h", "Total running time", 5006, 2, "uint32", unit="h", section="Energy"),
        telemetry_point("temperature_c", "Internal temperature", 5008, 1, "int16", scale=0.1, unit="C", section="Thermal", summary_metric="temperature_c"),
        telemetry_point("dc_voltage_v", "DC voltage 1", 5011, 1, "uint16", scale=0.1, unit="V", section="PV input"),
        telemetry_point("dc_current_a", "DC current 1", 5012, 1, "uint16", scale=0.1, unit="A", section="PV input"),
        telemetry_point("pv2_voltage_v", "DC voltage 2", 5013, 1, "uint16", scale=0.1, unit="V", section="PV input"),
        telemetry_point("pv2_current_a", "DC current 2", 5014, 1, "uint16", scale=0.1, unit="A", section="PV input"),
        telemetry_point("pv3_voltage_v", "DC voltage 3", 5015, 1, "uint16", scale=0.1, unit="V", section="PV input"),
        telemetry_point("pv3_current_a", "DC current 3", 5016, 1, "uint16", scale=0.1, unit="A", section="PV input"),
        telemetry_point("dc_power_kw", "Total DC power", 5017, 2, "uint32", scale=0.001, unit="kW", section="PV input"),
        telemetry_point("mains_voltage_v", "A-B line voltage / phase A voltage", 5019, 1, "uint16", scale=0.1, unit="V", section="Grid"),
        telemetry_point("grid_voltage_bc_v", "B-C line voltage / phase B voltage", 5020, 1, "uint16", scale=0.1, unit="V", section="Grid"),
        telemetry_point("grid_voltage_ca_v", "C-A line voltage / phase C voltage", 5021, 1, "uint16", scale=0.1, unit="V", section="Grid"),
        telemetry_point("ac_current_a", "Phase A current", 5022, 1, "uint16", scale=0.1, unit="A", section="Grid"),
        telemetry_point("grid_current_b_a", "Phase B current", 5023, 1, "uint16", scale=0.1, unit="A", section="Grid"),
        telemetry_point("grid_current_c_a", "Phase C current", 5024, 1, "uint16", scale=0.1, unit="A", section="Grid"),
        telemetry_point("active_power_kw", "Total active power", 5031, 2, "uint32", scale=0.001, unit="kW", section="Power", summary_metric="power_kw"),
        telemetry_point("reactive_power_kvar", "Reactive power", 5033, 2, "int32", scale=0.001, unit="kVAr", section="Power"),
        telemetry_point("power_factor", "Power factor", 5035, 1, "int16", scale=0.001, section="Power"),
        telemetry_point("mains_frequency_hz", "Grid frequency", 5036, 1, "uint16", scale=0.1, unit="Hz", section="Grid"),
        telemetry_point("status", "Work state", 5038, 1, "uint16", section="Status and alarms", summary_metric="status", enum_map=SUNGROW_WORK_STATE_MAP, heartbeat=True),
        telemetry_point("fault_alarm_code", "Fault/Alarm code", 5045, 1, "uint16", section="Status and alarms"),
        telemetry_point("nominal_reactive_power_kvar", "Nominal reactive output power", 5049, 1, "uint16", scale=0.1, unit="kVAr", section="Rating"),
        telemetry_point("insulation_resistance_kohm", "Array insulation resistance", 5071, 1, "uint16", unit="kOhm", section="Status and alarms"),
        telemetry_point("work_state_bits", "Work state bits", 5081, 2, "uint32", section="Status and alarms"),
        telemetry_point("daily_running_time_min", "Daily running time", 5113, 1, "uint16", unit="min", section="Energy"),
        telemetry_point("country_code", "Present country", 5114, 1, "uint16", section="Grid"),
        telemetry_point("pv4_voltage_v", "DC voltage 4", 5115, 1, "uint16", scale=0.1, unit="V", section="PV input", optional_block=True),
        telemetry_point("pv4_current_a", "DC current 4", 5116, 1, "uint16", scale=0.1, unit="A", section="PV input", optional_block=True),
        telemetry_point("negative_voltage_to_ground_v", "Negative voltage to ground", 5146, 1, "int16", scale=0.1, unit="V", section="PV input", optional_block=True),
        telemetry_point("bus_voltage_v", "Bus voltage", 5147, 1, "uint16", scale=0.1, unit="V", section="PV input", optional_block=True),
        telemetry_point("grid_frequency_precise_hz", "Grid frequency precise", 5148, 1, "uint16", scale=0.01, unit="Hz", section="Grid", optional_block=True),
        telemetry_point("active_power_limit_switch", "Power limitation switch", 5007, 1, "uint16", register_type="holding", section="Power control", enum_map=SUNGROW_POWER_LIMIT_SWITCH_MAP),
        telemetry_point("active_power_limit_pct", "Power limitation setting", 5008, 1, "uint16", register_type="holding", scale=0.1, unit="%", section="Power control", command="active_power_limit"),
    ]

    points.extend(
        telemetry_point(
            f"string_{index:02d}_current_a",
            f"Current of input {index}",
            7012 + index,
            1,
            "uint16",
            scale=0.01,
            unit="A",
            section="Combiner board",
            optional_block=True,
        )
        for index in range(1, 19)
    )
    return points


def build_sungrow_commands() -> list[InverterPoint]:
    return [
        command_point("start_stop", "Start/Stop", 5006, "uint16", section="Operation", enum_map=SUNGROW_START_STOP_MAP),
        command_point("active_power_limit_enable", "Power limitation switch", 5007, "uint16", section="Power control", enum_map=SUNGROW_POWER_LIMIT_SWITCH_MAP),
        command_point("active_power_limit", "Power limitation setting", 5008, "uint16", scale=0.1, unit="%", section="Power control", min_value=0.0, max_value=110.0, step=0.1),
        command_point("power_factor_setting", "Power factor setting", 5019, "int16", scale=0.001, section="Reactive power control", min_value=-1.0, max_value=1.0, step=0.001),
    ]


def build_sungrow_models(protocol: str, transport: str) -> list[InverterModel]:
    if protocol == "modbus_tcp" and transport == "tcp":
        defaults: dict[str, str | int | float | bool] = {
            "host": "192.168.1.100",
            "port": 502,
            "unit_id": 1,
            "timeout_seconds": 1.0,
            "retries": 1,
            "poll_interval_seconds": 15,
            "heartbeat_interval_seconds": 2,
            "test_register": input_addr(5000),
            "test_function": "input",
            "test_count": 1,
            "max_registers_per_request": 48,
        }
        return [
            InverterModel(
                brand=SUNGROW_BRAND,
                model=model,
                protocol=protocol,
                transport=transport,
                defaults=defaults,
                features=[
                    "modbus tcp",
                    "grid-tied telemetry",
                    "active power control",
                    "broadcast write",
                    "string current monitoring",
                ],
                telemetry_points=build_sungrow_telemetry(),
                command_points=build_sungrow_commands(),
            )
            for model in SUNGROW_MODELS
        ]

    if protocol != "modbus_rtu" or transport != "serial":
        return []

    return [
        InverterModel(
            brand=SUNGROW_BRAND,
            model=model,
            protocol=protocol,
            transport=transport,
            defaults={
                "port": "COM1",
                "slave_id": 1,
                "baud_rate": 9600,
                "parity": "N",
                "stop_bits": 1,
                "byte_size": 8,
                "timeout_seconds": 1.0,
                "retries": 1,
                "poll_interval_seconds": 15,
                "heartbeat_interval_seconds": 2,
                "test_register": input_addr(5000),
                "test_function": "input",
                "test_count": 1,
                "max_registers_per_request": 48,
            },
            features=[
                "modbus rtu",
                "grid-tied telemetry",
                "active power control",
                "broadcast write",
                "string current monitoring",
            ],
            telemetry_points=build_sungrow_telemetry(),
            command_points=build_sungrow_commands(),
        )
        for model in SUNGROW_MODELS
    ]
