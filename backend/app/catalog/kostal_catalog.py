from app.models.inverter_model import InverterModel, InverterPoint


KOSTAL_BRAND = "Kostal"

KOSTAL_MODEL_GROUPS: list[tuple[str, str, int, int]] = [
    ("PIKO CI 30", "ci_30_50_60", 30, 71),
    ("PIKO CI 50", "ci_30_50_60", 50, 71),
    ("PIKO CI 60", "ci_30_50_60", 60, 71),
    ("PIKO CI 100", "ci_100_g2", 100, 0),
    ("Plenticore Series (PLUS)", "plenticore_plus", 10, 71),
]

KOSTAL_BOOL_MAP = {
    0: "Disabled",
    1: "Enabled",
}

KOSTAL_POWER_DIRECTION_MAP = {
    0: "Positive",
    1: "Negative",
}

KOSTAL_ZERO_FEED_IN_MODE_MAP = {
    0: "Disable",
    1: "Power limit by external command",
    2: "Power limit by PVI external CT sensor",
    3: "Power limit by digital meter device",
}

KOSTAL_METER_POSITION_MAP = {
    0: "CT or meter on grid",
    1: "CT or meter on load",
}

KOSTAL_POWER_LIMIT_FUNCTION_MAP = {
    0: "Disable",
    1: "External device",
    2: "CT sensor",
    3: "Digital power meter",
}

KOSTAL_CT_RATIO_MAP = {
    1: "1000:1",
    2: "2000:1",
    3: "2500:1",
    4: "3000:1",
    5: "4000:1",
    6: "5000:1",
    7: "6000:1",
    8: "10000:1",
}

KOSTAL_PARK_CONTROLLER_CONFIGURATION_MAP = {
    0: "Disable",
    1: "High priority",
    2: "Low priority",
}

KOSTAL_COMMUNICATION_WAY_MAP = {
    0: "LAN",
    1: "RS485",
}

KOSTAL_REMOTE_OFF_STATUS_MAP = {
    0: "Non-active",
    1: "Active",
}

KOSTAL_INVERTER_STATE_MAP = {
    0: "Off",
    1: "Init",
    2: "IsoMeas",
    3: "GridCheck",
    4: "StartUp",
    6: "FeedIn",
    7: "Throttled",
    8: "ExtSwitchOff",
    9: "Update",
    10: "Standby",
    11: "GridSync",
    12: "GridPreCheck",
    13: "GridSwitchOff",
    14: "Overheating",
    15: "Shutdown",
    16: "ImproperDcVoltage",
    17: "ESB",
    18: "Unknown",
}

KOSTAL_SHADOW_MANAGEMENT_MAP = {
    0: "Disable",
    1: "Shadow manage",
    2: "I-V curve detect",
}

KOSTAL_ENERGY_MANAGER_STATE_MAP = {
    0: "Idle",
    2: "Emergency battery charge",
    8: "Winter mode step 1",
    16: "Winter mode step 2",
}

KOSTAL_PSSB_FUSE_STATE_MAP = {
    0: "Fuse fail",
    1: "Fuse OK",
    255: "Unchecked",
}

KOSTAL_BATTERY_READY_MAP = {
    0: "Not ready",
    1: "Ready",
}

KOSTAL_BATTERY_TYPE_MAP = {
    0: "No battery",
    2: "Li-Io battery SONY / MURATA",
    4: "Li-Io battery BYD / BBOX",
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
    scale_factor_key: str | None = None,
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
        scale_factor_key=scale_factor_key,
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
        length=2 if datatype in {"uint32", "int32", "float32"} else 1,
        datatype=datatype,
        scale=scale,
        unit=unit,
        writable=True,
        protocol_meta=protocol_meta,
    )


def build_kostal_base_telemetry() -> list[InverterPoint]:
    return [
        telemetry_point("inverter_article_number", "Inverter article number", 6, 8, "ascii_string", section="Identification"),
        telemetry_point("inverter_serial_number", "Inverter serial number", 14, 8, "ascii_string", section="Identification"),
        telemetry_point("bidirectional_converter_count", "Number of bidirectional converter", 30, 1, "uint16", section="Identification"),
        telemetry_point("ac_phase_count", "Number of AC phases", 32, 1, "uint16", section="Identification"),
        telemetry_point("pv_string_count", "Number of PV strings", 34, 1, "uint16", section="Identification"),
        telemetry_point("software_version_maincontroller", "Software version maincontroller", 38, 8, "ascii_string", section="Identification"),
        telemetry_point("software_version_ioc", "Software version IO controller", 46, 8, "ascii_string", section="Identification"),
        telemetry_point("inverter_state_raw", "Inverter state", 56, 1, "uint16", section="Identification", enum_map=KOSTAL_INVERTER_STATE_MAP),
        telemetry_point("total_dc_power_w", "Total DC power", 100, 2, "float32", scale=0.001, unit="kW", section="DC input"),
        telemetry_point("home_consumption_from_grid_w", "Home own consumption from grid", 108, 2, "float32", scale=0.001, unit="kW", section="Meter"),
        telemetry_point("total_home_consumption_grid_wh", "Total home consumption grid", 112, 2, "float32", scale=0.001, unit="kWh", section="Meter"),
        telemetry_point("total_home_consumption_pv_wh", "Total home consumption PV", 114, 2, "float32", scale=0.001, unit="kWh", section="Meter"),
        telemetry_point("home_consumption_from_pv_w", "Home own consumption from PV", 116, 2, "float32", scale=0.001, unit="kW", section="Meter"),
        telemetry_point("total_home_consumption_wh", "Total home consumption", 118, 2, "float32", scale=0.001, unit="kWh", section="Meter"),
        telemetry_point("power_limit_from_evu_percent", "Power limit from EVU", 122, 2, "float32", unit="%", section="Meter"),
        telemetry_point("total_home_consumption_rate_percent", "Total home consumption rate", 124, 2, "float32", unit="%", section="Meter"),
        telemetry_point("worktime_s", "Worktime", 144, 2, "float32", unit="s", section="Energy"),
        telemetry_point("actual_cosphi", "Actual cos phi", 150, 2, "float32", section="AC output"),
        telemetry_point("grid_frequency_hz", "Grid frequency", 152, 2, "float32", unit="Hz", section="AC output"),
        telemetry_point("current_phase_1_a", "Current phase 1", 154, 2, "float32", unit="A", section="AC output"),
        telemetry_point("active_power_phase_1_w", "Active power phase 1", 156, 2, "float32", scale=0.001, unit="kW", section="AC output"),
        telemetry_point("voltage_phase_1_v", "Voltage phase 1", 158, 2, "float32", unit="V", section="AC output"),
        telemetry_point("current_phase_2_a", "Current phase 2", 160, 2, "float32", unit="A", section="AC output"),
        telemetry_point("active_power_phase_2_w", "Active power phase 2", 162, 2, "float32", scale=0.001, unit="kW", section="AC output"),
        telemetry_point("voltage_phase_2_v", "Voltage phase 2", 164, 2, "float32", unit="V", section="AC output"),
        telemetry_point("current_phase_3_a", "Current phase 3", 166, 2, "float32", unit="A", section="AC output"),
        telemetry_point("active_power_phase_3_w", "Active power phase 3", 168, 2, "float32", scale=0.001, unit="kW", section="AC output"),
        telemetry_point("voltage_phase_3_v", "Voltage phase 3", 170, 2, "float32", unit="V", section="AC output"),
        telemetry_point("total_ac_active_power_w", "Total AC active power", 172, 2, "float32", scale=0.001, unit="kW", section="AC output", summary_metric="power_kw"),
        telemetry_point("total_ac_reactive_power_var", "Total AC reactive power", 174, 2, "float32", scale=0.001, unit="kVAr", section="AC output"),
        telemetry_point("total_ac_apparent_power_va", "Total AC apparent power", 178, 2, "float32", scale=0.001, unit="kVA", section="AC output"),
        telemetry_point("powermeter_cosphi", "Cos phi powermeter", 218, 2, "float32", section="Meter"),
        telemetry_point("powermeter_frequency_hz", "Frequency powermeter", 220, 2, "float32", unit="Hz", section="Meter"),
        telemetry_point("powermeter_current_phase_1_a", "Current phase 1 powermeter", 222, 2, "float32", unit="A", section="Meter"),
        telemetry_point("powermeter_active_power_phase_1_w", "Active power phase 1 powermeter", 224, 2, "float32", scale=0.001, unit="kW", section="Meter"),
        telemetry_point("powermeter_voltage_phase_1_v", "Voltage phase 1 powermeter", 230, 2, "float32", unit="V", section="Meter"),
        telemetry_point("powermeter_total_active_power_w", "Total active power powermeter", 252, 2, "float32", scale=0.001, unit="kW", section="Meter"),
        telemetry_point("current_dc1_a", "Current DC1", 258, 2, "float32", unit="A", section="DC input"),
        telemetry_point("power_dc1_w", "Power DC1", 260, 2, "float32", scale=0.001, unit="kW", section="DC input"),
        telemetry_point("voltage_dc1_v", "Voltage DC1", 266, 2, "float32", unit="V", section="DC input"),
        telemetry_point("current_dc2_a", "Current DC2", 268, 2, "float32", unit="A", section="DC input"),
        telemetry_point("power_dc2_w", "Power DC2", 270, 2, "float32", scale=0.001, unit="kW", section="DC input"),
        telemetry_point("voltage_dc2_v", "Voltage DC2", 276, 2, "float32", unit="V", section="DC input"),
        telemetry_point("current_dc3_a", "Current DC3", 278, 2, "float32", unit="A", section="DC input"),
        telemetry_point("power_dc3_w", "Power DC3", 280, 2, "float32", scale=0.001, unit="kW", section="DC input"),
        telemetry_point("voltage_dc3_v", "Voltage DC3", 286, 2, "float32", unit="V", section="DC input"),
        telemetry_point("current_dc4_a", "Current DC4", 300, 2, "float32", unit="A", section="DC input"),
        telemetry_point("power_dc4_w", "Power DC4", 302, 2, "float32", scale=0.001, unit="kW", section="DC input"),
        telemetry_point("voltage_dc4_v", "Voltage DC4", 308, 2, "float32", unit="V", section="DC input"),
        telemetry_point("total_yield_wh", "Total yield", 320, 2, "float32", scale=0.001, unit="kWh", section="Energy", summary_metric="total_energy_kwh"),
        telemetry_point("daily_yield_wh", "Daily yield", 322, 2, "float32", scale=0.001, unit="kWh", section="Energy", summary_metric="daily_energy_kwh"),
        telemetry_point("yearly_yield_wh", "Yearly yield", 324, 2, "float32", scale=0.001, unit="kWh", section="Energy"),
        telemetry_point("monthly_yield_wh", "Monthly yield", 326, 2, "float32", scale=0.001, unit="kWh", section="Energy"),
        telemetry_point("inverter_network_name", "Inverter network name", 384, 32, "ascii_string", section="Network"),
        telemetry_point("ip_enable", "IP enable", 416, 1, "uint16", section="Network", enum_map=KOSTAL_BOOL_MAP),
        telemetry_point("manual_ip_auto_ip", "Manual IP / Auto-IP", 418, 1, "uint16", section="Network"),
        telemetry_point("ip_address", "IP address", 420, 8, "ascii_string", section="Network"),
        telemetry_point("ip_subnetmask", "IP subnetmask", 428, 8, "ascii_string", section="Network"),
        telemetry_point("ip_gateway", "IP gateway", 436, 8, "ascii_string", section="Network"),
        telemetry_point("firmware_maincontroller_numeric", "Firmware maincontroller", 515, 2, "uint32", section="Identification"),
        telemetry_point("inverter_max_power_raw", "Inverter max power raw", 531, 1, "uint16", visible=False, section="Identification", scale_factor_key="power_scale_factor"),
        telemetry_point("power_scale_factor", "Power scale factor", 532, 1, "int16", visible=False, section="Identification"),
        telemetry_point("inverter_max_power_w", "Inverter max power", 531, 1, "uint16", unit="W", section="Identification", scale_factor_key="power_scale_factor"),
        telemetry_point("inverter_manufacturer", "Inverter manufacturer", 535, 16, "ascii_string", section="Identification"),
        telemetry_point("inverter_model_id", "Inverter model ID", 551, 8, "ascii_string", section="Identification"),
        telemetry_point("inverter_serial_number_ext", "Inverter serial number ext", 559, 16, "ascii_string", section="Identification"),
        telemetry_point("generation_power_actual_raw", "Generation power actual raw", 575, 1, "int16", visible=False, section="AC output", scale_factor_key="power_scale_factor_2"),
        telemetry_point("power_scale_factor_2", "Power scale factor 2", 576, 1, "int16", visible=False, section="AC output"),
        telemetry_point("generation_power_actual_w", "Generation power actual", 575, 1, "int16", unit="W", section="AC output", scale_factor_key="power_scale_factor_2"),
        telemetry_point("generation_energy_raw", "Generation energy raw", 577, 2, "uint32", visible=False, section="Energy", scale_factor_key="energy_scale_factor"),
        telemetry_point("energy_scale_factor", "Energy scale factor", 579, 1, "int16", visible=False, section="Energy"),
        telemetry_point("generation_energy_wh", "Generation energy", 577, 2, "uint32", unit="Wh", section="Energy", scale_factor_key="energy_scale_factor"),
        telemetry_point("digital_meter_modbus_address", "Modbus address for digital meter", 608, 1, "uint16", section="Meter"),
        telemetry_point("digital_meter_power_direction", "Digital meter power direction", 609, 1, "uint16", section="Meter", enum_map=KOSTAL_POWER_DIRECTION_MAP),
        telemetry_point("zero_feed_in_mode", "Zero feed-in mode", 610, 1, "uint16", section="Control", enum_map=KOSTAL_ZERO_FEED_IN_MODE_MAP),
        telemetry_point("power_limit_meter_position", "Power limit meter position", 611, 1, "uint16", section="Control", enum_map=KOSTAL_METER_POSITION_MAP),
        telemetry_point("max_feed_in_power_w", "Max feed-in power", 612, 2, "uint32", unit="W", section="Control"),
        telemetry_point("product_name", "Product name", 768, 32, "ascii_string", section="Identification"),
        telemetry_point("power_class", "Power class", 800, 32, "ascii_string", section="Identification"),
        telemetry_point("error_message_1", "Error message 1", 4126, 1, "uint16", section="Status and alarms", display_format="hex", display_width=4),
        telemetry_point("error_message_2", "Error message 2", 4127, 1, "uint16", section="Status and alarms", display_format="hex", display_width=4),
        telemetry_point("error_message_3", "Error message 3", 4128, 1, "uint16", section="Status and alarms", display_format="hex", display_width=4),
        telemetry_point("control_board_firmware_version", "Control board firmware version", 6684, 3, "ascii_string", section="Identification"),
        telemetry_point("communication_service_board_firmware_version", "Communication service board firmware version", 6752, 3, "ascii_string", section="Identification"),
        telemetry_point("output_power_derating_percent", "Output power de-rating percent", 12293, 1, "uint16", unit="%", section="Control"),
        telemetry_point("rcr_current_input_status", "RCR current input status", 12671, 1, "uint16", section="Control", display_format="hex", display_width=4),
        telemetry_point("remote_off_signal_status", "Remote off signal status", 21017, 1, "uint16", section="Status and alarms", enum_map=KOSTAL_REMOTE_OFF_STATUS_MAP),
    ]


def build_kostal_plenticore_telemetry() -> list[InverterPoint]:
    return build_kostal_base_telemetry() + [
        telemetry_point("energy_manager_state", "State of energy manager", 104, 2, "uint32", section="Battery and EMS", enum_map=KOSTAL_ENERGY_MANAGER_STATE_MAP, display_format="hex", display_width=4),
        telemetry_point("home_consumption_from_battery_w", "Home own consumption from battery", 106, 2, "float32", scale=0.001, unit="kW", section="Battery and EMS"),
        telemetry_point("total_home_consumption_battery_wh", "Total home consumption battery", 110, 2, "float32", scale=0.001, unit="kWh", section="Battery and EMS"),
        telemetry_point("isolation_resistance_ohm", "Isolation resistance", 120, 2, "float32", unit="Ohm", section="Battery and EMS"),
        telemetry_point("battery_charge_current_a", "Battery charge current", 190, 2, "float32", unit="A", section="Battery and EMS"),
        telemetry_point("battery_cycle_count", "Number of battery cycles", 194, 2, "float32", unit="cycles", section="Battery and EMS"),
        telemetry_point("battery_charge_discharge_current_a", "Actual battery charge/discharge current", 200, 2, "float32", unit="A", section="Battery and EMS"),
        telemetry_point("pssb_fuse_state", "PSSB fuse state", 202, 2, "float32", section="Battery and EMS", enum_map=KOSTAL_PSSB_FUSE_STATE_MAP),
        telemetry_point("battery_ready_flag", "Battery ready flag", 208, 2, "float32", section="Battery and EMS", enum_map=KOSTAL_BATTERY_READY_MAP),
        telemetry_point("battery_state_of_charge_percent", "Battery state of charge", 210, 2, "float32", unit="%", section="Battery and EMS"),
        telemetry_point("battery_temperature_c", "Battery temperature", 214, 2, "float32", unit="C", section="Battery and EMS"),
        telemetry_point("battery_voltage_v", "Battery voltage", 216, 2, "float32", unit="V", section="Battery and EMS"),
        telemetry_point("powermeter_total_reactive_power_var", "Total reactive power powermeter", 254, 2, "float32", scale=0.001, unit="kVAr", section="Meter"),
        telemetry_point("powermeter_total_apparent_power_va", "Total apparent power powermeter", 256, 2, "float32", scale=0.001, unit="kVA", section="Meter"),
        telemetry_point("battery_gross_capacity_ah", "Battery gross capacity", 512, 2, "uint32", unit="Ah", section="Battery and EMS"),
        telemetry_point("battery_actual_soc_percent", "Battery actual SOC", 514, 1, "uint16", unit="%", section="Battery and EMS"),
        telemetry_point("battery_manufacturer", "Battery manufacturer", 517, 8, "ascii_string", section="Battery and EMS"),
        telemetry_point("battery_model_id", "Battery model ID", 525, 2, "uint32", section="Battery and EMS"),
        telemetry_point("battery_serial_number_numeric", "Battery serial number", 527, 2, "uint32", section="Battery and EMS"),
        telemetry_point("battery_work_capacity_kwh", "Battery work capacity", 529, 2, "uint32", scale=0.001, unit="kWh", section="Battery and EMS"),
        telemetry_point("battery_charge_discharge_power_kw", "Actual battery charge/discharge power", 582, 1, "int16", scale=0.001, unit="kW", section="Battery and EMS"),
        telemetry_point("battery_type", "Battery type", 588, 1, "uint16", section="Battery and EMS", enum_map=KOSTAL_BATTERY_TYPE_MAP),
    ]


def build_kostal_telemetry(family: str) -> list[InverterPoint]:
    if family == "plenticore_plus":
        return build_kostal_plenticore_telemetry()
    return build_kostal_base_telemetry()


def build_kostal_features(family: str) -> list[str]:
    base_features = [
        "modbus tcp e rtu",
        "telemetria ac dc e contatore",
        "controllo immediato potenza attiva e reattiva",
        "power limiting e park controller",
    ]
    if family == "plenticore_plus":
        return base_features + [
            "telemetria batteria",
            "energy manager state",
        ]
    return base_features


def build_kostal_commands(max_power_kw: int) -> list[InverterPoint]:
    return [
        command_point("active_power_limit", "Active power setpoint", 533, "uint16", unit="%", section="Immediate control", min_value=1, max_value=100, step=1),
        command_point("reactive_power_setpoint_percent", "Reactive power setpoint", 583, "int16", unit="%", section="Immediate control", min_value=-100, max_value=100, step=1),
        command_point("delta_cosphi_setpoint", "Delta cos phi setpoint", 585, "int16", scale=1.0 / 32767.0, section="Immediate control", min_value=-0.8, max_value=0.8),
        command_point("digital_meter_modbus_address_set", "Digital meter Modbus address", 608, "uint16", section="Metering", min_value=1, max_value=247, step=1),
        command_point("digital_meter_power_direction_set", "Digital meter power direction", 609, "uint16", section="Metering", min_value=0, max_value=1, step=1, enum_map=KOSTAL_POWER_DIRECTION_MAP),
        command_point("zero_feed_in_mode_set", "Zero feed-in mode", 610, "uint16", section="Power limit", min_value=0, max_value=3, step=1, enum_map=KOSTAL_ZERO_FEED_IN_MODE_MAP),
        command_point("power_limit_meter_position_set", "Power limit meter position", 611, "uint16", section="Power limit", min_value=0, max_value=1, step=1, enum_map=KOSTAL_METER_POSITION_MAP),
        command_point("max_feed_in_power_w_set", "Max feed-in power", 612, "uint32", unit="W", section="Power limit", min_value=0, max_value=max_power_kw * 1000),
        command_point("output_power_derating_percent_set", "Output power de-rating percent", 12293, "uint16", unit="%", section="Power limit", min_value=0, max_value=100, step=1),
        command_point("rcr_enable_flag", "Ripple control receiver enable flag", 12299, "uint16", section="Power limit", min_value=0, max_value=1, step=1, enum_map=KOSTAL_BOOL_MAP),
        command_point("output_power_derating_modbus_w", "Output power de-rating by Modbus", 12421, "uint32", unit="W", section="Power limit", min_value=0, max_value=max_power_kw * 1000),
        command_point("power_limit_function", "Power limit function", 12467, "uint16", section="Power limit", min_value=0, max_value=3, step=1, enum_map=KOSTAL_POWER_LIMIT_FUNCTION_MAP),
        command_point("power_limit_ct_ratio", "Power limit CT ratio", 12468, "uint16", section="Power limit", min_value=1, max_value=8, step=1, enum_map=KOSTAL_CT_RATIO_MAP),
        command_point("device_location", "Device location", 12469, "uint16", section="Power limit", min_value=0, max_value=1, step=1, enum_map=KOSTAL_METER_POSITION_MAP),
        command_point("maximum_feed_in_grid_power_w", "Maximum feed in grid power", 12473, "uint32", unit="W", section="Power limit", min_value=0, max_value=max_power_kw * 1000),
        command_point("park_controller_loss_output_power_percent", "Park controller loss output power percent", 12475, "uint16", unit="%", section="Park controller", min_value=0, max_value=100, step=1),
        command_point("park_controller_configuration", "Park controller configuration", 12608, "uint16", section="Park controller", min_value=0, max_value=2, step=1, enum_map=KOSTAL_PARK_CONTROLLER_CONFIGURATION_MAP),
        command_point("park_controller_communication_way", "Park controller communication ways", 12609, "uint16", section="Park controller", min_value=0, max_value=1, step=1, enum_map=KOSTAL_COMMUNICATION_WAY_MAP),
        command_point("park_controller_loss_timeout_s", "Park controller communication loss timeout", 12610, "uint16", unit="s", section="Park controller", min_value=1, max_value=300, step=1),
        command_point("meter_communication_way", "Meter communication ways", 12611, "uint16", section="Metering", min_value=0, max_value=1, step=1, enum_map=KOSTAL_COMMUNICATION_WAY_MAP),
        command_point("remote_off_function", "Remote off function", 21018, "uint16", section="Control", min_value=0, max_value=1, step=1, enum_map=KOSTAL_BOOL_MAP),
        command_point("setting_output_power_factor", "Setting output power factor", 24591, "int16", scale=0.001, section="Reactive power", min_value=-1.0, max_value=1.0),
        command_point("setting_reactive_power_percent", "Setting reactive power percent", 24592, "int16", scale=0.01, unit="%", section="Reactive power", min_value=-100.0, max_value=100.0),
    ]


def build_kostal_defaults(protocol: str, *, tcp_unit_id: int, rtu_slave_id: int) -> dict[str, str | int | float | bool]:
    common_defaults: dict[str, str | int | float | bool] = {
        "timeout_seconds": 2,
        "retries": 1,
        "poll_interval_seconds": 15,
        "test_register": 172,
        "test_count": 2,
        "test_function": "holding",
        "max_registers_per_request": 120,
        "inter_request_delay_ms": 100,
    }
    if protocol == "modbus_rtu":
        return {
            "port": "COM1",
            "slave_id": rtu_slave_id,
            "baud_rate": 19200,
            "parity": "N",
            "stop_bits": 2,
            "byte_size": 8,
            **common_defaults,
        }
    return {
        "host": "192.168.1.100",
        "port": 1502,
        "unit_id": tcp_unit_id,
        **common_defaults,
    }


def build_kostal_models(protocol: str, transport: str) -> list[InverterModel]:
    models: list[InverterModel] = []
    for model_name, family, max_power_kw, tcp_unit_id in KOSTAL_MODEL_GROUPS:
        models.append(
            InverterModel(
                brand=KOSTAL_BRAND,
                model=model_name,
                protocol=protocol,
                transport=transport,
                defaults=build_kostal_defaults(
                    protocol,
                    tcp_unit_id=tcp_unit_id,
                    rtu_slave_id=1,
                ),
                features=build_kostal_features(family),
                telemetry_points=build_kostal_telemetry(family),
                command_points=build_kostal_commands(max_power_kw=max_power_kw),
            )
        )
    return models
