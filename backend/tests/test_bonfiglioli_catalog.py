import unittest

from app.catalog.bonfiglioli_catalog import (
    BONFIGLIOLI_PARAMETER_OFFSET,
    build_bonfiglioli_models,
)
from app.services.bonfiglioli_modbus_service import bonfiglioli_modbus_service


class BonfiglioliCatalogTests(unittest.TestCase):
    def test_catalog_reads_only_whitelisted_bonfiglioli_parameters(self) -> None:
        model = build_bonfiglioli_models("modbus_rtu", "serial")[0]
        actual_parameters = {point.address for point in model.telemetry_points}
        expected_parameters = {
            212,
            221,
            249,
            254,
            255,
            259,
            300,
            849,
            852,
            853,
            855,
            860,
            862,
            863,
            864,
            865,
            866,
            867,
            868,
            869,
            870,
            871,
            872,
            873,
            874,
            875,
            876,
            877,
            878,
            1090,
            1161,
        }

        self.assertEqual(actual_parameters, expected_parameters)
        self.assertEqual(len(model.telemetry_points), len(expected_parameters))

    def test_catalog_keeps_manual_parameters_and_driver_applies_field_offset(self) -> None:
        model = build_bonfiglioli_models("modbus_rtu", "serial")[0]

        self.assertEqual(model.defaults["parameter_offset"], BONFIGLIOLI_PARAMETER_OFFSET)
        self.assertEqual(model.defaults["test_register"], 223)
        self.assertEqual(model.defaults["test_register_manual"], 222)

        telemetry_point = next(
            point for point in model.telemetry_points if point.key == "dc_link_voltage_v"
        )
        self.assertEqual(telemetry_point.address, 221)
        self.assertEqual(
            telemetry_point.protocol_meta["address_offset"], BONFIGLIOLI_PARAMETER_OFFSET
        )
        self.assertEqual(
            bonfiglioli_modbus_service._parameter_address(
                telemetry_point, {"parameter_offset": BONFIGLIOLI_PARAMETER_OFFSET}
            ),
            222,
        )

    def test_active_power_limit_command_uses_manual_parameter_with_verified_field_offset(self) -> None:
        model = build_bonfiglioli_models("modbus_rtu", "serial")[0]

        command_point = next(
            point for point in model.command_points if point.key == "active_power_limit"
        )
        self.assertEqual(command_point.address, 1019)
        self.assertEqual(command_point.scale, 1.0)
        self.assertEqual(command_point.unit, "%")
        self.assertEqual(command_point.protocol_meta["dataset"], 0)
        self.assertEqual(command_point.protocol_meta["field_verified_parameter"], 1021)
        self.assertEqual(
            bonfiglioli_modbus_service._parameter_address(
                command_point, {"parameter_offset": BONFIGLIOLI_PARAMETER_OFFSET}
            ),
            1020,
        )
        self.assertEqual(bonfiglioli_modbus_service._encode_command_value(command_point, 40.0), 40)

    def test_key_telemetry_scaling_matches_manual_ranges(self) -> None:
        model = build_bonfiglioli_models("modbus_tcp", "tcp")[0]
        points = {point.key: point for point in model.telemetry_points}

        self.assertEqual(points["active_power_kw"].scale, 0.1)
        self.assertEqual(points["dc_link_voltage_v"].scale, 0.1)
        self.assertEqual(points["temperature_c"].scale, 0.1)
        self.assertEqual(points["inside_temperature_c"].scale, 0.1)
        self.assertEqual(points["mains_frequency_hz"].scale, 0.01)
        self.assertEqual(points["mains_voltage_v"].scale, 0.1)
        self.assertEqual(points["mains_voltage_a_v"].scale, 0.1)
        self.assertEqual(points["mains_voltage_b_v"].scale, 0.1)
        self.assertEqual(points["mains_voltage_c_v"].scale, 0.1)
        self.assertEqual(points["power_supply_current_a"].scale, 0.1)
        self.assertEqual(points["dc_link_power_kw"].scale, 0.1)
        self.assertEqual(points["dc_current_a"].scale, 0.1)
        self.assertEqual(points["active_power_a_kw"].scale, 0.1)
        self.assertEqual(points["active_power_b_kw"].scale, 0.1)
        self.assertEqual(points["active_power_c_kw"].scale, 0.1)
        self.assertEqual(points["reactive_power_a_kvar"].scale, 0.1)
        self.assertEqual(points["reactive_power_b_kvar"].scale, 0.1)
        self.assertEqual(points["reactive_power_c_kvar"].scale, 0.1)
        self.assertEqual(points["reactive_power_kvar"].scale, 0.1)
        self.assertEqual(points["apparent_power_a_kva"].scale, 0.1)
        self.assertEqual(points["apparent_power_b_kva"].scale, 0.1)
        self.assertEqual(points["apparent_power_c_kva"].scale, 0.1)
        self.assertEqual(points["apparent_power_kva"].scale, 0.1)
        self.assertEqual(points["reactive_power_reference_kvar"].scale, 0.1)

    def test_dashboard_priority_bonfiglioli_points_are_present(self) -> None:
        model = build_bonfiglioli_models("modbus_rtu", "serial")[0]
        points = {point.key: point for point in model.telemetry_points}

        self.assertEqual(points["active_power_kw"].address, 212)
        self.assertEqual(points["dc_link_voltage_v"].address, 221)
        self.assertEqual(points["temperature_c"].address, 254)
        self.assertEqual(points["inside_temperature_c"].address, 255)
        self.assertEqual(points["current_error_code"].address, 259)
        self.assertEqual(points["total_energy_kwh"].address, 300)
        self.assertEqual(points["mains_frequency_hz"].address, 849)
        self.assertEqual(points["power_supply_current_a"].address, 852)
        self.assertEqual(points["mains_voltage_v"].address, 853)
        self.assertEqual(points["dc_link_power_kw"].address, 855)
        self.assertEqual(points["dc_current_a"].address, 860)
        self.assertEqual(points["current_a_a"].address, 862)
        self.assertEqual(points["current_b_a"].address, 863)
        self.assertEqual(points["current_c_a"].address, 864)
        self.assertEqual(points["mains_voltage_a_v"].address, 865)
        self.assertEqual(points["mains_voltage_b_v"].address, 866)
        self.assertEqual(points["mains_voltage_c_v"].address, 867)
        self.assertEqual(points["active_power_a_kw"].address, 868)
        self.assertEqual(points["active_power_b_kw"].address, 869)
        self.assertEqual(points["active_power_c_kw"].address, 870)
        self.assertEqual(points["reactive_power_a_kvar"].address, 871)
        self.assertEqual(points["reactive_power_b_kvar"].address, 872)
        self.assertEqual(points["reactive_power_c_kvar"].address, 873)
        self.assertEqual(points["apparent_power_a_kva"].address, 874)
        self.assertEqual(points["apparent_power_b_kva"].address, 875)
        self.assertEqual(points["apparent_power_c_kva"].address, 876)
        self.assertEqual(points["reactive_power_kvar"].address, 877)
        self.assertEqual(points["apparent_power_kva"].address, 878)
        self.assertEqual(points["status"].address, 1090)
        self.assertEqual(points["reactive_power_reference_kvar"].address, 1161)


if __name__ == "__main__":
    unittest.main()
