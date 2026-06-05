from app.models.inverter_model import InverterModel, InverterPoint


GOODWE_BRAND = "GOODWE"
GOODWE_BMS_MODEL = "BMS Modbus RS485 V1.1"
GOODWE_GRID_TIED_STANDARD_MODEL = "Grid-tied MS/DNS/XS/SDTG2"
GOODWE_GRID_TIED_MT_MODEL = "Grid-tied MT/SMT/MTG2"
GOODWE_HYBRID_ET_MODEL = "Hybrid ET/EH/BT/BH"

GOODWE_GRID_STATUS_MAP = {
    0: "Wait mode",
    1: "Normal mode",
    2: "Fault mode",
}

GOODWE_BMS_WARNING_BITS = {
    0: "Cell overvoltage alarm",
    1: "Cell low voltage alarm",
    2: "Pack overvoltage alarm",
    3: "Pack low voltage alarm",
    4: "Charging overcurrent alarm",
    5: "Discharging overcurrent alarm",
    8: "Charging high temperature alarm",
    9: "Discharging high temperature alarm",
    10: "Charging low temperature alarm",
    11: "Discharging low temperature alarm",
    12: "Environment high temperature alarm",
    13: "Environment low temperature alarm",
    14: "MOSFET high temperature alarm",
    15: "SOC low alarm",
}

GOODWE_BMS_PROTECTION_BITS = {
    0: "Cell overvoltage protection",
    1: "Cell low voltage protection",
    2: "Pack overvoltage protection",
    3: "Pack low voltage protection",
    4: "Charging overcurrent protection",
    5: "Discharging overcurrent protection",
    6: "Short circuit protection",
    7: "Charger overvoltage protection",
    8: "Charging high temperature protection",
    9: "Discharging high temperature protection",
    10: "Charging low temperature protection",
    11: "Discharging low temperature protection",
    12: "MOSFET high temperature protection",
    13: "Environment high temperature protection",
    14: "Environment low temperature protection",
}

GOODWE_BMS_STATUS_FAULT_BITS = {
    0: "Charging MOSFET fault",
    1: "Discharging MOSFET fault",
    2: "Temperature sensor fault",
    4: "Battery cell fault",
    5: "Front-end sampling communication fault",
    8: "Charging",
    9: "Discharging",
    10: "Charging MOSFET ON",
    11: "Discharging MOSFET ON",
    12: "Charging limiter ON",
    14: "Charger reversed",
    15: "Heater ON",
}


def telemetry_point(
    key: str,
    label: str,
    address: int,
    length: int,
    datatype: str,
    *,
    register_type: str = "holding",
    scale: float = 1.0,
    unit: str = "",
    visible: bool = True,
    section: str,
    summary_metric: str | None = None,
    enum_map: dict[int, str] | None = None,
    bitmask_labels: dict[int, str] | None = None,
    command: str | None = None,
    heartbeat: bool = False,
) -> InverterPoint:
    protocol_meta: dict[str, object] = {"section": section}
    if summary_metric is not None:
        protocol_meta["summary_metric"] = summary_metric
    if enum_map is not None:
        protocol_meta["enum_map"] = enum_map
    if bitmask_labels is not None:
        protocol_meta["bitmask_labels"] = bitmask_labels
    if command is not None:
        protocol_meta["command"] = command
    if heartbeat:
        protocol_meta["heartbeat"] = True

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
    step: float | None = None,
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


def build_goodwe_bms_telemetry() -> list[InverterPoint]:
    points = [
        telemetry_point("battery_current_a", "Battery current", 0, 1, "int16", scale=0.01, unit="A", section="Battery", heartbeat=True),
        telemetry_point("battery_voltage_v", "Battery pack voltage", 1, 1, "uint16", scale=0.01, unit="V", section="Battery", heartbeat=True),
        telemetry_point("soc_percent", "SOC", 2, 1, "uint8_low", unit="%", section="Battery", heartbeat=True),
        telemetry_point("soh_percent", "SOH", 3, 1, "uint8_low", unit="%", section="Battery"),
        telemetry_point("remain_capacity_ah", "Remain capacity", 4, 1, "uint16", scale=0.01, unit="Ah", section="Capacity"),
        telemetry_point("full_capacity_ah", "Full capacity", 5, 1, "uint16", scale=0.01, unit="Ah", section="Capacity"),
        telemetry_point("design_capacity_ah", "Design capacity", 6, 1, "uint16", scale=0.01, unit="Ah", section="Capacity"),
        telemetry_point("battery_cycle_count", "Battery cycle count", 7, 1, "uint16", unit="cyc", section="Capacity"),
        telemetry_point("warning_flag", "Warning flag", 9, 1, "uint16", section="Status and alarms", bitmask_labels=GOODWE_BMS_WARNING_BITS),
        telemetry_point("protection_flag", "Protection flag", 10, 1, "uint16", section="Status and alarms", bitmask_labels=GOODWE_BMS_PROTECTION_BITS),
        telemetry_point("status", "Status/Fault flag", 11, 1, "uint16", section="Status and alarms", summary_metric="status", bitmask_labels=GOODWE_BMS_STATUS_FAULT_BITS),
        telemetry_point("balance_status", "Balance status", 12, 1, "uint16", section="Status and alarms"),
    ]

    points.extend(
        telemetry_point(
            f"cell_{index:02d}_voltage_v",
            f"Cell {index} voltage",
            14 + index,
            1,
            "uint16",
            scale=0.001,
            unit="V",
            section="Cells",
        )
        for index in range(1, 17)
    )
    points.extend(
        telemetry_point(
            f"cell_temperature_{index}_c",
            f"Cell temperature {index}",
            30 + index,
            1,
            "int16",
            scale=0.1,
            unit="C",
            section="Thermal",
            summary_metric="temperature_c" if index == 1 else None,
        )
        for index in range(1, 5)
    )
    points.extend(
        [
            telemetry_point("mosfet_temperature_c", "MOSFET temperature", 35, 1, "int16", scale=0.1, unit="C", section="Thermal"),
            telemetry_point("environment_temperature_c", "Environment temperature", 36, 1, "int16", scale=0.1, unit="C", section="Thermal"),
            telemetry_point("cumulative_discharging_ah", "Cumulative discharging Ah", 40, 2, "uint32", scale=0.01, unit="Ah", section="Counters"),
            telemetry_point("cumulative_discharging_kwh", "Cumulative discharging energy", 42, 2, "uint32", scale=0.001, unit="kWh", section="Counters", summary_metric="total_energy_kwh"),
            telemetry_point("bms_version_info", "Version information", 150, 10, "ascii_string", section="Identity"),
            telemetry_point("bms_model_sn", "Model SN", 160, 10, "ascii_string", section="Identity"),
            telemetry_point("pack_sn", "PACK SN", 170, 10, "ascii_string", section="Identity"),
        ]
    )
    return points


def build_goodwe_grid_standard_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("device_serial_number", "Device serial number", 512, 8, "ascii_string", visible=False, section="Identity"),
        telemetry_point("device_type", "Device type", 528, 5, "ascii_string", visible=False, section="Identity"),
        telemetry_point("active_power_limit_pct", "Active power adjust", 256, 1, "uint16", unit="%", section="Power control", command="active_power_limit"),
        telemetry_point("error_message", "Error message", 544, 2, "uint32", section="Status and alarms"),
        telemetry_point("total_energy_kwh", "Total feed power", 546, 2, "uint32", scale=0.1, unit="kWh", section="Energy", summary_metric="total_energy_kwh"),
        telemetry_point("dc_voltage_v", "PV1 voltage", 550, 1, "uint16", scale=0.1, unit="V", section="PV input"),
        telemetry_point("pv2_voltage_v", "PV2 voltage", 551, 1, "uint16", scale=0.1, unit="V", section="PV input"),
        telemetry_point("dc_current_a", "PV1 current", 552, 1, "uint16", scale=0.1, unit="A", section="PV input"),
        telemetry_point("pv2_current_a", "PV2 current", 553, 1, "uint16", scale=0.1, unit="A", section="PV input"),
        telemetry_point("mains_voltage_v", "Grid L1 voltage", 554, 1, "uint16", scale=0.1, unit="V", section="Grid"),
        telemetry_point("grid_l2_voltage_v", "Grid L2 voltage", 555, 1, "uint16", scale=0.1, unit="V", section="Grid"),
        telemetry_point("grid_l3_voltage_v", "Grid L3 voltage", 556, 1, "uint16", scale=0.1, unit="V", section="Grid"),
        telemetry_point("ac_current_a", "Grid L1 current", 557, 1, "uint16", scale=0.1, unit="A", section="Grid"),
        telemetry_point("grid_l2_current_a", "Grid L2 current", 558, 1, "uint16", scale=0.1, unit="A", section="Grid"),
        telemetry_point("grid_l3_current_a", "Grid L3 current", 559, 1, "uint16", scale=0.1, unit="A", section="Grid"),
        telemetry_point("mains_frequency_hz", "Grid L1 frequency", 560, 1, "uint16", scale=0.01, unit="Hz", section="Grid"),
        telemetry_point("grid_l2_frequency_hz", "Grid L2 frequency", 561, 1, "uint16", scale=0.01, unit="Hz", section="Grid"),
        telemetry_point("grid_l3_frequency_hz", "Grid L3 frequency", 562, 1, "uint16", scale=0.01, unit="Hz", section="Grid"),
        telemetry_point("active_power_kw", "Inverter output power", 563, 1, "uint16", scale=0.001, unit="kW", section="Power", summary_metric="power_kw"),
        telemetry_point("status", "Work mode", 564, 1, "uint16", section="Status and alarms", summary_metric="status", enum_map=GOODWE_GRID_STATUS_MAP),
        telemetry_point("temperature_c", "Inverter internal temperature", 565, 1, "uint16", scale=0.1, unit="C", section="Thermal", summary_metric="temperature_c"),
        telemetry_point("daily_energy_kwh", "Daily feed power", 566, 1, "uint16", scale=0.1, unit="kWh", section="Energy", summary_metric="daily_energy_kwh"),
    ]


def build_goodwe_grid_mt_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("device_serial_number", "Device serial number", 512, 8, "ascii_string", visible=False, section="Identity"),
        telemetry_point("device_type", "Device type", 528, 5, "ascii_string", visible=False, section="Identity"),
        telemetry_point("active_power_limit_pct", "Active power adjust", 256, 1, "uint16", unit="%", section="Power control", command="active_power_limit"),
        telemetry_point("dc_voltage_v", "PV1 voltage", 768, 1, "uint16", scale=0.1, unit="V", section="PV input"),
        telemetry_point("pv2_voltage_v", "PV2 voltage", 769, 1, "uint16", scale=0.1, unit="V", section="PV input"),
        telemetry_point("dc_current_a", "PV1 current", 770, 1, "uint16", scale=0.1, unit="A", section="PV input"),
        telemetry_point("pv2_current_a", "PV2 current", 771, 1, "uint16", scale=0.1, unit="A", section="PV input"),
        telemetry_point("mains_voltage_v", "Grid L1 voltage", 772, 1, "uint16", scale=0.1, unit="V", section="Grid"),
        telemetry_point("grid_l2_voltage_v", "Grid L2 voltage", 773, 1, "uint16", scale=0.1, unit="V", section="Grid"),
        telemetry_point("grid_l3_voltage_v", "Grid L3 voltage", 774, 1, "uint16", scale=0.1, unit="V", section="Grid"),
        telemetry_point("ac_current_a", "Grid L1 current", 775, 1, "uint16", scale=0.1, unit="A", section="Grid"),
        telemetry_point("grid_l2_current_a", "Grid L2 current", 776, 1, "uint16", scale=0.1, unit="A", section="Grid"),
        telemetry_point("grid_l3_current_a", "Grid L3 current", 777, 1, "uint16", scale=0.1, unit="A", section="Grid"),
        telemetry_point("mains_frequency_hz", "Grid L1 frequency", 778, 1, "uint16", scale=0.01, unit="Hz", section="Grid"),
        telemetry_point("grid_l2_frequency_hz", "Grid L2 frequency", 779, 1, "uint16", scale=0.01, unit="Hz", section="Grid"),
        telemetry_point("grid_l3_frequency_hz", "Grid L3 frequency", 780, 1, "uint16", scale=0.01, unit="Hz", section="Grid"),
        telemetry_point("status", "Work mode", 782, 1, "uint16", section="Status and alarms", summary_metric="status", enum_map=GOODWE_GRID_STATUS_MAP),
        telemetry_point("temperature_c", "Inverter internal temperature", 783, 1, "uint16", scale=0.1, unit="C", section="Thermal", summary_metric="temperature_c"),
        telemetry_point("error_message_h", "Error message H", 784, 1, "uint16", section="Status and alarms"),
        telemetry_point("error_message_l", "Error message L", 785, 1, "uint16", section="Status and alarms"),
        telemetry_point("total_energy_kwh", "Total feed power", 786, 2, "uint32", scale=0.1, unit="kWh", section="Energy", summary_metric="total_energy_kwh"),
        telemetry_point("daily_energy_kwh", "Daily feed power", 800, 1, "uint16", scale=0.1, unit="kWh", section="Energy", summary_metric="daily_energy_kwh"),
        telemetry_point("active_power_kw", "Feeding power", 850, 2, "uint32", scale=0.001, unit="kW", section="Power", summary_metric="power_kw"),
        telemetry_point("pv3_voltage_v", "PV3 voltage", 855, 1, "uint16", scale=0.1, unit="V", section="PV input"),
        telemetry_point("pv4_voltage_v", "PV4 voltage", 856, 1, "uint16", scale=0.1, unit="V", section="PV input"),
        telemetry_point("pv3_current_a", "PV3 current", 857, 1, "uint16", scale=0.1, unit="A", section="PV input"),
        telemetry_point("pv4_current_a", "PV4 current", 858, 1, "uint16", scale=0.1, unit="A", section="PV input"),
    ]


def build_goodwe_grid_commands() -> list[InverterPoint]:
    return [
        command_point(
            "active_power_limit",
            "Active power adjust",
            256,
            "uint16",
            unit="%",
            section="Power control",
            min_value=0.0,
            max_value=100.0,
            step=1.0,
        )
    ]


def build_goodwe_hybrid_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("modbus_protocol_version", "Modbus protocol version", 35000, 1, "uint16", visible=False, section="Identity"),
        telemetry_point("rated_power_raw", "Rated power", 35001, 1, "uint16", visible=False, section="Identity"),
        telemetry_point("device_serial_number", "Serial number", 35003, 8, "ascii_string", visible=False, section="Identity"),
        telemetry_point("device_type", "Device type", 35011, 5, "ascii_string", visible=False, section="Identity"),
        telemetry_point("dc_voltage_v", "PV1 voltage", 35103, 1, "uint16", scale=0.1, unit="V", section="PV input"),
        telemetry_point("dc_current_a", "PV1 current", 35104, 1, "uint16", scale=0.1, unit="A", section="PV input"),
        telemetry_point("pv1_power_kw", "PV1 power", 35105, 2, "uint32", scale=0.0001, unit="kW", section="PV input"),
        telemetry_point("pv2_voltage_v", "PV2 voltage", 35107, 1, "uint16", scale=0.1, unit="V", section="PV input"),
        telemetry_point("pv2_current_a", "PV2 current", 35108, 1, "uint16", scale=0.1, unit="A", section="PV input"),
        telemetry_point("pv2_power_kw", "PV2 power", 35109, 2, "uint32", scale=0.0001, unit="kW", section="PV input"),
        telemetry_point("mains_voltage_v", "Grid R voltage", 35121, 1, "uint16", scale=0.1, unit="V", section="Grid"),
        telemetry_point("ac_current_a", "Grid R current", 35122, 1, "uint16", scale=0.1, unit="A", section="Grid"),
        telemetry_point("mains_frequency_hz", "Grid R frequency", 35123, 1, "uint16", scale=0.01, unit="Hz", section="Grid"),
        telemetry_point("grid_power_r_kw", "Grid R power", 35125, 1, "int16", scale=0.001, unit="kW", section="Grid"),
        telemetry_point("grid_s_voltage_v", "Grid S voltage", 35126, 1, "uint16", scale=0.1, unit="V", section="Grid"),
        telemetry_point("grid_s_current_a", "Grid S current", 35127, 1, "uint16", scale=0.1, unit="A", section="Grid"),
        telemetry_point("grid_s_frequency_hz", "Grid S frequency", 35128, 1, "uint16", scale=0.01, unit="Hz", section="Grid"),
        telemetry_point("grid_power_s_kw", "Grid S power", 35130, 1, "int16", scale=0.001, unit="kW", section="Grid"),
        telemetry_point("grid_t_voltage_v", "Grid T voltage", 35131, 1, "uint16", scale=0.1, unit="V", section="Grid"),
        telemetry_point("grid_t_current_a", "Grid T current", 35132, 1, "uint16", scale=0.1, unit="A", section="Grid"),
        telemetry_point("grid_t_frequency_hz", "Grid T frequency", 35133, 1, "uint16", scale=0.01, unit="Hz", section="Grid"),
        telemetry_point("grid_power_t_kw", "Grid T power", 35135, 1, "int16", scale=0.001, unit="kW", section="Grid"),
        telemetry_point("grid_mode", "Grid mode", 35136, 1, "uint16", section="Status and alarms"),
        telemetry_point("active_power_kw", "Total INV power", 35138, 1, "int16", scale=0.001, unit="kW", section="Power", summary_metric="power_kw"),
        telemetry_point("load_power_kw", "Load power", 35139, 1, "uint16", scale=0.001, unit="kW", section="Load"),
        telemetry_point("work_mode", "Work mode", 35140, 1, "uint16", section="Status and alarms", summary_metric="status"),
        telemetry_point("status", "Error code", 35141, 2, "uint32", section="Status and alarms"),
        telemetry_point("daily_energy_kwh", "E-Day", 35165, 2, "float32", scale=0.1, unit="kWh", section="Energy", summary_metric="daily_energy_kwh"),
        telemetry_point("total_energy_kwh", "E-Total", 35167, 2, "float32", scale=0.1, unit="kWh", section="Energy", summary_metric="total_energy_kwh"),
        telemetry_point("temperature_c", "Air temperature", 35174, 1, "uint16", scale=0.1, unit="C", section="Thermal", summary_metric="temperature_c"),
        telemetry_point("battery_voltage_v", "Battery voltage", 35180, 1, "uint16", scale=0.1, unit="V", section="Battery"),
        telemetry_point("battery_current_a", "Battery current", 35181, 1, "int16", scale=0.1, unit="A", section="Battery"),
        telemetry_point("battery_power_kw", "Battery power", 35183, 1, "int16", scale=0.001, unit="kW", section="Battery"),
        telemetry_point("meter_total_active_power_kw", "Meter total active power", 36025, 2, "int32", scale=0.001, unit="kW", section="Meter"),
        telemetry_point("bms_status", "BMS status", 37002, 1, "uint16", section="BMS"),
        telemetry_point("bms_pack_temperature_c", "BMS pack temperature", 37003, 1, "uint16", scale=0.1, unit="C", section="BMS"),
        telemetry_point("soc_percent", "SOC", 37007, 1, "uint16", unit="%", section="BMS"),
        telemetry_point("soh_percent", "SOH", 37008, 1, "uint16", unit="%", section="BMS"),
        telemetry_point("bms_warning_code_l", "BMS warning code L", 37010, 1, "uint16", section="BMS"),
        telemetry_point("max_cell_temperature_c", "Maximum cell temperature", 37020, 1, "uint16", scale=0.1, unit="C", section="BMS"),
        telemetry_point("min_cell_temperature_c", "Minimum cell temperature", 37021, 1, "uint16", scale=0.1, unit="C", section="BMS"),
        telemetry_point("max_cell_voltage_v", "Maximum cell voltage", 37022, 1, "uint16", scale=0.001, unit="V", section="BMS"),
        telemetry_point("min_cell_voltage_v", "Minimum cell voltage", 37023, 1, "uint16", scale=0.001, unit="V", section="BMS"),
    ]


def _base_serial_defaults() -> dict[str, str | int | float | bool]:
    return {
        "port": "COM1",
        "slave_id": 247,
        "baud_rate": 9600,
        "parity": "N",
        "stop_bits": 1,
        "byte_size": 8,
        "timeout_seconds": 1.0,
        "retries": 1,
        "poll_interval_seconds": 15,
        "heartbeat_interval_seconds": 2,
        "max_registers_per_request": 64,
    }


def _base_tcp_defaults() -> dict[str, str | int | float | bool]:
    return {
        "host": "192.168.1.100",
        "port": 502,
        "unit_id": 247,
        "timeout_seconds": 1.0,
        "retries": 1,
        "poll_interval_seconds": 15,
        "heartbeat_interval_seconds": 2,
        "max_registers_per_request": 64,
    }


def build_goodwe_models(protocol: str, transport: str) -> list[InverterModel]:
    if protocol == "modbus_rtu" and transport == "serial":
        grid_defaults = {
            **_base_serial_defaults(),
            "test_register": 512,
            "test_function": "holding",
            "test_count": 8,
        }
        hybrid_defaults = {
            **_base_serial_defaults(),
            "test_register": 35000,
            "test_function": "holding",
            "test_count": 1,
        }
        bms_defaults = {
            "port": "COM1",
            "slave_id": 1,
            "baud_rate": 9600,
            "parity": "N",
            "stop_bits": 1,
            "byte_size": 8,
            "timeout_seconds": 0.5,
            "retries": 1,
            "poll_interval_seconds": 15,
            "heartbeat_interval_seconds": 2,
            "inter_request_delay_ms": 100,
            "test_register": 0,
            "test_function": "holding",
            "test_count": 3,
            "max_registers_per_request": 64,
        }
        return [
            InverterModel(
                brand=GOODWE_BRAND,
                model=GOODWE_BMS_MODEL,
                protocol=protocol,
                transport=transport,
                defaults=bms_defaults,
                features=["modbus rtu", "bms telemetry", "soc soh", "cell voltages", "thermal monitoring"],
                telemetry_points=build_goodwe_bms_telemetry(),
                command_points=[],
            ),
            InverterModel(
                brand=GOODWE_BRAND,
                model=GOODWE_GRID_TIED_STANDARD_MODEL,
                protocol=protocol,
                transport=transport,
                defaults=grid_defaults,
                features=["modbus rtu", "grid-tied telemetry", "active power control"],
                telemetry_points=build_goodwe_grid_standard_telemetry(),
                command_points=build_goodwe_grid_commands(),
            ),
            InverterModel(
                brand=GOODWE_BRAND,
                model=GOODWE_GRID_TIED_MT_MODEL,
                protocol=protocol,
                transport=transport,
                defaults=grid_defaults,
                features=["modbus rtu", "grid-tied telemetry", "active power control", "multi-mppt"],
                telemetry_points=build_goodwe_grid_mt_telemetry(),
                command_points=build_goodwe_grid_commands(),
            ),
            InverterModel(
                brand=GOODWE_BRAND,
                model=GOODWE_HYBRID_ET_MODEL,
                protocol=protocol,
                transport=transport,
                defaults=hybrid_defaults,
                features=["modbus rtu", "hybrid telemetry", "battery telemetry", "meter telemetry"],
                telemetry_points=build_goodwe_hybrid_telemetry(),
                command_points=[],
            ),
        ]

    if protocol == "modbus_tcp" and transport == "tcp":
        grid_defaults = {
            **_base_tcp_defaults(),
            "test_register": 512,
            "test_function": "holding",
            "test_count": 8,
        }
        return [
            InverterModel(
                brand=GOODWE_BRAND,
                model=GOODWE_GRID_TIED_STANDARD_MODEL,
                protocol=protocol,
                transport=transport,
                defaults=grid_defaults,
                features=["modbus tcp", "grid-tied telemetry", "active power control"],
                telemetry_points=build_goodwe_grid_standard_telemetry(),
                command_points=build_goodwe_grid_commands(),
            ),
            InverterModel(
                brand=GOODWE_BRAND,
                model=GOODWE_GRID_TIED_MT_MODEL,
                protocol=protocol,
                transport=transport,
                defaults=grid_defaults,
                features=["modbus tcp", "grid-tied telemetry", "active power control", "multi-mppt"],
                telemetry_points=build_goodwe_grid_mt_telemetry(),
                command_points=build_goodwe_grid_commands(),
            ),
            InverterModel(
                brand=GOODWE_BRAND,
                model=GOODWE_HYBRID_ET_MODEL,
                protocol=protocol,
                transport=transport,
                defaults={
                    **_base_tcp_defaults(),
                    "test_register": 35000,
                    "test_function": "holding",
                    "test_count": 1,
                },
                features=["modbus tcp", "hybrid telemetry", "battery telemetry", "meter telemetry"],
                telemetry_points=build_goodwe_hybrid_telemetry(),
                command_points=[],
            )
        ]

    return []
